"""Rosstat Russia CPI collector with the official basket and bottom-up checks."""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import traceback
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.engine import Engine

from scripts.config import (
    DEFAULT_START_DATE,
    LOG_LEVEL,
    MAX_WAIT,
    MIN_VALIDATION_COVERAGE,
    POLL_INTERVAL,
    ROOT_DIR,
    START_DATE_LOOKBACK_MONTHS,
    missing_environment,
    unresolved_credentials,
)
from scripts.db import build_engine
from scripts.export_validation_xlsx import export_validation_xlsx
from scripts.extract import (
    TREE_PARENTS,
    RosstatPublication,
    collect_publication,
    get_hierarchy,
    get_last_publish_date,
    get_series_catalog,
)
from scripts.init_db import init_db
from scripts.metadata import upsert_metadata
from scripts.run_logs import insert_run_log
from scripts.time_series import get_max_reference_date, upsert_time_series
from scripts.validate import (
    Check,
    log_validation_summary,
    validate_index_base_stability,
    validate_index_bottom_up,
    validate_kipc_weight_sums,
    validate_panel_quality,
    validate_source_agreement,
    validate_weight_sums,
)
from scripts.weights import assert_percentage_basket, upsert_weights

logger = logging.getLogger("main")

DEFAULT_EXPORT_PATH = ROOT_DIR / "rosstat_cpi_validation.xlsx"
# Reconciliations that gate the run. The KIPC checks are diagnostics only: they
# grade Rosstat's own classification codes, which repeat a parent's code on a
# child in a documented handful of nodes, and nothing from that layer is written
# to the standardized tables.
GATED_CHECK_KINDS = frozenset(
    {
        "index_dec_based",
        "index_month_on_month",
        "weight_total",
        "weight_sum",
        "surface_agreement",
    }
)


def _setup_logging(level: str) -> io.StringIO:
    """Capture collector logs while suppressing noisy third-party INFO output."""
    buffer = io.StringIO()
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(formatter)
    buffer_handler = logging.StreamHandler(stream=buffer)
    buffer_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.ERROR)
    root.addHandler(stream_handler)
    root.addHandler(buffer_handler)
    for name in ("main", "scripts"):
        logging.getLogger(name).setLevel(level.upper())
    return buffer


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the command line this collector accepts."""
    parser = argparse.ArgumentParser(description="Collect Russia CPI from Rosstat")
    parser.add_argument("--start-date", type=date.fromisoformat, default=None)
    parser.add_argument("--log-level", default=LOG_LEVEL)
    parser.add_argument(
        "--watch",
        action="store_true",
        help="poll for the next monthly release instead of exiting when it is absent",
    )
    parser.add_argument(
        "--export-validation",
        nargs="?",
        const=str(DEFAULT_EXPORT_PATH),
        default=None,
        metavar="PATH",
        help="write the analyst audit workbook to PATH",
    )
    return parser.parse_args(argv)


def _shift_months(value: date, months: int) -> date:
    """Return the first day of the month ``months`` away from ``value``."""
    total = value.year * 12 + value.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)


def _rewind_start(latest: date | None) -> date:
    """Resolve the start date from the newest stored reference month."""
    if latest is None:
        return DEFAULT_START_DATE
    return max(DEFAULT_START_DATE, _shift_months(latest, -START_DATE_LOOKBACK_MONTHS))


def _preflight() -> None:
    """Report every missing environment variable before any network work."""
    missing = missing_environment()
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    unresolved = unresolved_credentials()
    if unresolved:
        logger.warning(
            "No Databricks credential configured (%s); a notebook/job context must supply it",
            ", ".join(unresolved),
        )


def _wait_for_release(latest: date, start_date: date) -> RosstatPublication:
    """Poll the official page until the next reference month is published.

    Rosstat publishes the monthly CPI on the sixth to tenth working day of the
    month after the reference month. A timeout without a new month is a normal,
    successful outcome; the run then persists whatever is already published.
    """
    expected = _shift_months(latest, 1)
    deadline = time.monotonic() + MAX_WAIT
    publication = collect_publication(start_date)
    while max(publication.observations, default=latest) < expected:
        if time.monotonic() >= deadline:
            logger.info(
                "Release watch timed out after %.0fs; %s is still the newest published month",
                MAX_WAIT,
                max(publication.observations, default=latest),
            )
            return publication
        logger.info("Waiting for %s; re-checking in %.0fs", expected, POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)
        publication = collect_publication(start_date)
    logger.info("Release detected: %s is now published", expected)
    return publication


def _expected_reconciliations(publication: RosstatPublication) -> tuple[int, int]:
    """Return how many December-based and month-on-month checks should run."""
    months = sorted(publication.detail_panel)
    parents = len(TREE_PARENTS)
    dec_based = len(months) * parents
    within_year = sum(
        1
        for index, month in enumerate(months)
        if index
        and months[index - 1] == _shift_months(month, -1)
        and months[index - 1].year == month.year
    )
    return dec_based, within_year * parents


def _assert_coverage(publication: RosstatPublication, gated: list[Check]) -> None:
    """Refuse a run whose reconciliations silently stopped covering the panel."""
    expected_dec, expected_mom = _expected_reconciliations(publication)
    actual_dec = sum(1 for check in gated if check.kind == "index_dec_based")
    actual_mom = sum(1 for check in gated if check.kind == "index_month_on_month")
    expected = expected_dec + expected_mom
    coverage = (actual_dec + actual_mom) / expected if expected else 1.0
    logger.info(
        "Bottom-up coverage: %.4f (December-based %d/%d, month-on-month %d/%d)",
        coverage,
        actual_dec,
        expected_dec,
        actual_mom,
        expected_mom,
    )
    if coverage < MIN_VALIDATION_COVERAGE:
        raise ValueError(f"Bottom-up coverage {coverage:.4f} is below the configured floor")


def _validate(
    publication: RosstatPublication, hierarchy: dict[str, dict[str, object]]
) -> list[Check]:
    """Run every reconciliation and refuse to ingest a structurally broken panel."""
    problems = validate_panel_quality(
        publication.observations, publication.weights, get_series_catalog()
    )
    problems += validate_index_base_stability(publication.observations, get_series_catalog())
    if problems:
        raise ValueError(f"{len(problems)} data-quality problems block ingestion: {problems[:5]}")
    checks = (
        validate_index_bottom_up(publication.observations, publication.weights, hierarchy)
        + validate_weight_sums(publication.weights, hierarchy)
        + validate_source_agreement(publication.detail_panel, publication.headline_panel)
        + validate_kipc_weight_sums(publication.kipc)
    )
    log_validation_summary(checks, GATED_CHECK_KINDS)
    gated = [check for check in checks if check.kind in GATED_CHECK_KINDS]
    failures = [check for check in gated if check.failed]
    if failures:
        raise ValueError(f"{len(failures)} bottom-up reconciliations failed, first: {failures[0]}")
    _assert_coverage(publication, gated)
    return checks


def _collect(args: argparse.Namespace, engine: Engine) -> int:
    """Run the full pipeline once and return the process exit status."""
    init_db(engine)
    assert_percentage_basket(engine)
    latest = get_max_reference_date(engine)
    start_date = args.start_date or _rewind_start(latest)
    logger.info("Collecting Rosstat CPI from %s (latest stored: %s)", start_date, latest)

    if args.watch and latest is not None:
        publication = _wait_for_release(latest, start_date)
    else:
        publication = collect_publication(start_date)

    hierarchy = get_hierarchy()
    checks = _validate(publication, hierarchy)

    collected_at = datetime.now(UTC)
    new_observations, new_vintages = upsert_time_series(
        engine, publication.observations, collected_at
    )
    new_weights, new_weight_vintages = upsert_weights(engine, publication.weights, collected_at)
    inserted, updated = upsert_metadata(
        engine, publication.observations, collected_at, get_series_catalog()
    )
    logger.info(
        "Run summary: series=%d months=%d observations(new=%d vintages=%d) "
        "weights(new=%d vintages=%d) metadata(inserted=%d updated=%d) published=%s",
        len(get_series_catalog()),
        len(publication.observations),
        new_observations,
        new_vintages,
        new_weights,
        new_weight_vintages,
        inserted,
        updated,
        get_last_publish_date(),
    )
    if args.export_validation:
        export_validation_xlsx(
            Path(args.export_validation),
            publication.observations,
            publication.weights,
            hierarchy,
            publication.kipc,
            checks,
        )
    return 0


def run(argv: list[str] | None = None) -> int:
    """Entry point that guarantees exactly one run-log row on every path."""
    args = _parse_args(argv)
    buffer = _setup_logging(args.log_level)
    started_at = datetime.now(UTC)
    status, trace = "success", None
    engine: Engine | None = None
    try:
        _preflight()
        engine = build_engine()
        return _collect(args, engine)
    except Exception:  # noqa: BLE001 - every failure path must still write a run log
        status, trace = "error", traceback.format_exc()
        logger.error("Collection failed:\n%s", trace)
        return 1
    finally:
        finished_at = datetime.now(UTC)
        if engine is None:
            try:
                engine = build_engine()
            except Exception:
                logger.exception("Could not build an engine to persist the run log")
        if engine is not None:
            insert_run_log(engine, started_at, finished_at, status, buffer.getvalue(), trace)
            engine.dispose()


if __name__ == "__main__":
    sys.exit(run())

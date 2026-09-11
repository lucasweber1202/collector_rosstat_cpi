"""Run official-source evidence acquisition or initialize fleet tables.

Statistical ingestion is not exposed until Rosstat workbook layouts and
methodology are verified. A research success is not a CPI pipeline success.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from scripts.config import DATABASE_URL, LOG_LEVEL, PROD, missing_environment
from scripts.db import build_engine
from scripts.init_db import init_db
from scripts.run_logs import insert_run_log
from scripts.source_research import research_sources

logger = logging.getLogger("main")


def _setup_logging(level: str) -> io.StringIO:
    """Capture application logs only, with fleet root/application separation."""
    buffer = io.StringIO()
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handlers = [logging.StreamHandler(sys.stdout), logging.StreamHandler(buffer)]
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.ERROR)
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    for name in ("main", "scripts"):
        logging.getLogger(name).setLevel(level)
    return buffer


def run(argv: list[str] | None = None) -> int:
    """Execute one explicit operation and write at most one database run log."""
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--research",
        action="store_true",
        help="Download and inspect source evidence; no CPI ingestion.",
    )
    actions.add_argument(
        "--init-db", action="store_true", help="Create the three standard fleet tables."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Evidence directory outside the checkout; required for --research.",
    )
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default=LOG_LEVEL
    )
    args = parser.parse_args(argv)
    if args.research and args.output is None:
        parser.error("--research requires --output")
    if args.output is not None and args.output.resolve().is_relative_to(
        Path(__file__).resolve().parent
    ):
        parser.error(
            "Use an evidence directory outside the repository; source binaries must not be committed"
        )
    buffer = _setup_logging(args.log_level)
    started = datetime.now(UTC)
    engine = None
    status, error, code = "success", None, 0
    try:
        if args.init_db or PROD or DATABASE_URL:
            missing = missing_environment()
            if missing:
                raise RuntimeError("Missing environment variables: " + ", ".join(missing))
            engine = build_engine()
            init_db(engine)
        if args.research:
            report = research_sources(args.output)
            logger.info(
                "Research result: documents=%d workbooks=%d errors=%d truncated=%s; no observations written",
                len(report["documents"]),
                report["downloaded_workbooks"],
                len(report["errors"]),
                report["truncated"],
            )
            if report["errors"] or report["truncated"] or not report["downloaded_workbooks"]:
                raise RuntimeError(
                    "Source research incomplete; see evidence manifest. CPI ingestion remains unavailable."
                )
        else:
            logger.info("Initialized standard fleet tables; no observations written")
    except Exception:
        status, code = "error", 1
        error = traceback.format_exc()
        logger.exception("Operation failed")
    finally:
        if engine is not None:
            try:
                insert_run_log(engine, started, datetime.now(UTC), status, buffer.getvalue(), error)
            finally:
                engine.dispose()
    return code


if __name__ == "__main__":
    raise SystemExit(run())

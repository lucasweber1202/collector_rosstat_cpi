"""Build and idempotently upsert standardized metadata after observation writes."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import TextClause, text
from sqlalchemy.engine import Engine

from scripts.config import METADATA_TABLE, SCHEMA_NAME
from scripts.extract import (
    COUNTRY_CURRENCY,
    ECO_GROUPS,
    FREQUENCIES,
    SDMX_BASE_PERIODS,
    UNITS,
    get_last_publish_date,
    parse_series_id,
)
from scripts.time_series import get_series_aggregates

logger = logging.getLogger(__name__)
_TABLE = f"{SCHEMA_NAME}.{METADATA_TABLE}"
BATCH_SIZE = 500
_COMPARABLE_COLUMNS = (
    "name",
    "description",
    "country",
    "frequency",
    "unit",
    "first_observation",
    "last_observation",
    "observation_count",
    "eco_group",
    "source_url",
    "last_publish_date",
)
_COLUMNS = ("series_id", *_COMPARABLE_COLUMNS, "collected_at")
_UPDATE_COLUMNS = tuple(column for column in _COLUMNS if column != "series_id")
# See scripts/time_series.py: MERGE keeps a batch of changed rows in one
# statement; the fallback is only reached by the SQLite engine used in tests.
_MERGE_DIALECTS = frozenset({"databricks", "postgresql"})

# How each published transformation must be read. Rosstat publishes no index
# level for the components, so the rawest available representation of a node is
# its month-on-month index; the two SDMX series are the only published levels.
_MEASURE_LABELS = {
    "MOM": "index, previous month = 100",
    "YTD": "index, December of the previous year = 100",
    "YOY": "index, same month of the previous year = 100",
    "IX2000": f"index level, {SDMX_BASE_PERIODS['IX2000']}",
    "IX2010": f"index level, {SDMX_BASE_PERIODS['IX2010']}",
}
_LEVEL_LABELS = {
    "HEADLINE": "headline all-items aggregate",
    "AGGREGATE": "published Rosstat aggregate",
    "GROUP": "group of goods and services",
    "ITEM": "representative good or service",
}
_CLASSIFICATION_LABELS = {
    "RSTG": "Rosstat CPI grouping of goods, services and representative items",
    "SDDS": "IMF SDDS SDMX headline series (IMF ECOFIN_DSD)",
}


def _batch_parameters(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Flatten a batch into named parameters suffixed by row position."""
    return {
        f"{column}_{index}": row[column] for index, row in enumerate(rows) for column in _COLUMNS
    }


def _insert_statement(count: int) -> TextClause:
    """Build one multi-row INSERT covering ``count`` rows."""
    values = ", ".join(
        "(" + ", ".join(f":{column}_{index}" for column in _COLUMNS) + ")" for index in range(count)
    )
    return text(f"INSERT INTO {_TABLE} ({', '.join(_COLUMNS)}) VALUES {values}")


def _merge_statement(count: int) -> TextClause:
    """Build one Databricks-compatible MERGE covering ``count`` rows."""
    source = " UNION ALL ".join(
        "SELECT " + ", ".join(f":{column}_{index} AS {column}" for column in _COLUMNS)
        for index in range(count)
    )
    assignments = ", ".join(f"{column} = source.{column}" for column in _UPDATE_COLUMNS)
    return text(
        f"MERGE INTO {_TABLE} AS target USING ({source}) AS source "
        "ON target.series_id = source.series_id "
        f"WHEN MATCHED THEN UPDATE SET {assignments}"
    )


_UPDATE_SQL = text(
    f"UPDATE {_TABLE} SET {', '.join(f'{column}=:{column}' for column in _UPDATE_COLUMNS)} "
    "WHERE series_id=:series_id"
)


def _write_batches(conn: Any, rows: list[dict[str, Any]], operation: str, merge: bool) -> None:
    """Apply rows in bounded statements, logging INFO progress per batch."""
    if not rows:
        return
    logger.info("Metadata %s: writing %d rows in batches of %d", operation, len(rows), BATCH_SIZE)
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        if merge:
            conn.execute(_merge_statement(len(batch)), _batch_parameters(batch))
        elif operation == "insert":
            conn.execute(_insert_statement(len(batch)), _batch_parameters(batch))
        else:
            conn.execute(_UPDATE_SQL, batch)
        logger.info(
            "Metadata %s progress: %d/%d rows",
            operation,
            min(start + BATCH_SIZE, len(rows)),
            len(rows),
        )


def _as_date(value: Any) -> date | None:
    """Normalize whatever a dialect returns for a DATE column into a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _series_descriptive_row(series_id: str, fields: dict[str, Any]) -> dict[str, object]:
    """Build the descriptive columns from verified upstream Rosstat fields.

    ``parse_series_id`` supplies structural identity only. The human-readable
    name is the title Rosstat prints next to the value in the workbook it came
    from, so a stored name is a published name rather than a reconstruction.
    """
    key = parse_series_id(series_id)
    if fields.get("classification") != key.classification or fields.get("measure") != key.measure:
        raise ValueError(f"Upstream catalog does not describe {series_id}: {fields}")
    name = str(fields.get("native_name", "")).strip()
    native_code = str(fields.get("native_code", "")).strip()
    if not name or not native_code:
        raise ValueError(f"Upstream catalog carries no official name/code for {series_id}")
    frequency, unit, eco_group = "monthly", "index", "consumer_prices"
    if frequency not in FREQUENCIES or unit not in UNITS or eco_group not in ECO_GROUPS:
        raise ValueError(f"Invalid controlled vocabulary for {series_id}")
    level = _LEVEL_LABELS[key.level]
    parent = str(fields.get("parent_code", "")).strip()
    kipc = str(fields.get("kipc_code", "")).strip()
    description = (
        f"Russian Federation, national. {_MEASURE_LABELS[key.measure]}. "
        f"{_CLASSIFICATION_LABELS[key.classification]}; {level}; "
        f"native Rosstat code {native_code}"
        + (f"; KIPC (COICOP) code {kipc}" if kipc else "")
        + (f"; aggregated into Rosstat code {parent}" if parent else "")
        + f". Published by {fields['release_name']}."
    )
    return {
        "series_id": series_id,
        "name": f"Russia CPI: {name} ({key.measure})",
        "description": description[:2000],
        "country": COUNTRY_CURRENCY,
        "frequency": frequency,
        "unit": unit,
        "eco_group": eco_group,
        "source_url": fields["source_url"],
    }


def build_metadata_rows(
    parsed_by_date: dict[date, dict[str, float | None]],
    aggregates: dict[str, dict[str, Any]],
    collected_at: datetime,
    catalog: dict[str, dict[str, Any]],
) -> list[dict[str, object]]:
    """Create one row for every extracted series present in the database."""
    series_ids = {series_id for values in parsed_by_date.values() for series_id in values}
    publish_date = get_last_publish_date()
    rows: list[dict[str, object]] = []
    for series_id in sorted(series_ids):
        aggregate = aggregates.get(series_id)
        if not aggregate:
            continue
        fields = catalog.get(series_id)
        if fields is None:
            raise ValueError(f"No upstream metadata was captured for {series_id}")
        row = _series_descriptive_row(series_id, fields)
        row.update(
            first_observation=_as_date(aggregate["first_observation"]),
            last_observation=_as_date(aggregate["last_observation"]),
            observation_count=int(aggregate["observation_count"]),
            last_publish_date=publish_date
            or _as_date(aggregate.get("last_collected_at"))
            or collected_at.date(),
            collected_at=collected_at,
        )
        rows.append(row)
    return rows


def upsert_metadata(
    engine: Engine,
    parsed_by_date: dict[date, dict[str, float | None]],
    collected_at: datetime,
    catalog: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    """Insert new metadata and update only genuinely changed rows."""
    desired = build_metadata_rows(
        parsed_by_date, get_series_aggregates(engine), collected_at, catalog
    )
    logger.info("Metadata upsert: evaluating %d series", len(desired))
    with engine.connect() as conn:
        current_rows = (
            conn.execute(text(f"SELECT {', '.join(_COLUMNS)} FROM {_TABLE}")).mappings().all()
        )
    current = {str(row["series_id"]): dict(row) for row in current_rows}
    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    for row in desired:
        existing = current.get(str(row["series_id"]))
        if existing is None:
            inserts.append(row)
        elif not all(
            _as_date(existing.get(column)) == row.get(column)
            if column.endswith("observation") or column == "last_publish_date"
            else existing.get(column) == row.get(column)
            for column in _COMPARABLE_COLUMNS
        ):
            updates.append(row)
    with engine.begin() as conn:
        merge = conn.dialect.name in _MERGE_DIALECTS
        _write_batches(conn, inserts, "insert", merge=False)
        _write_batches(conn, updates, "update", merge=merge)
    logger.info("Metadata upsert: inserted=%d updated=%d", len(inserts), len(updates))
    return len(inserts), len(updates)

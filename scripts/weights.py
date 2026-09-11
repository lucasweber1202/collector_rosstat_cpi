"""Persist the official Rosstat consumer-expenditure basket with vintage semantics."""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import TextClause, text
from sqlalchemy.engine import Connection, Engine

from scripts.config import SCHEMA_NAME, WEIGHTS_TABLE

logger = logging.getLogger(__name__)
_TABLE = f"{SCHEMA_NAME}.{WEIGHTS_TABLE}"


# Rosstat publishes the consumer-expenditure structure as a percentage of the
# national total, so every stored weight lies in [0, 100] and the headline node
# is exactly 100. A row outside that range means a different basket convention
# reached this table and would silently corrupt every reconstruction.
_RANGE_GUARD_SQL = text(f"SELECT COUNT(*) FROM {_TABLE} WHERE weight > 100.0 OR weight < 0.0")


def assert_percentage_basket(engine: Engine) -> None:
    """Refuse to mix a non-percentage basket convention into the weights table."""
    with engine.connect() as conn:
        outside = conn.execute(_RANGE_GUARD_SQL).scalar_one()
    if outside:
        raise ValueError(
            f"weights holds {outside} rows outside the published 0-100 percent range; "
            "Rosstat publishes the basket as a percentage of the national total"
        )


BATCH_SIZE = 500
ROUND_DECIMALS = 10

_COLUMNS = ("series_id", "reference_date", "vintage_date", "weight", "collected_at")
_KEY_COLUMNS = ("series_id", "reference_date", "vintage_date")
_UPDATE_COLUMNS = ("weight", "collected_at")
# See scripts/time_series.py: MERGE keeps a batch of same-day revisions in one
# statement; the fallback is only reached by the SQLite engine used in tests.
_MERGE_DIALECTS = frozenset({"databricks", "postgresql"})


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
    condition = " AND ".join(f"target.{column} = source.{column}" for column in _KEY_COLUMNS)
    assignments = ", ".join(f"{column} = source.{column}" for column in _UPDATE_COLUMNS)
    return text(
        f"MERGE INTO {_TABLE} AS target USING ({source}) AS source ON {condition} "
        f"WHEN MATCHED THEN UPDATE SET {assignments}"
    )


_UPDATE_SQL = text(
    f"UPDATE {_TABLE} SET {', '.join(f'{column}=:{column}' for column in _UPDATE_COLUMNS)} "
    f"WHERE {' AND '.join(f'{column}=:{column}' for column in _KEY_COLUMNS)}"
)


def _write_batches(
    conn: Connection, rows: list[dict[str, Any]], operation: str, merge: bool
) -> None:
    """Apply rows in bounded statements, logging INFO progress per batch."""
    if not rows:
        return
    logger.info("Weights %s: writing %d rows in batches of %d", operation, len(rows), BATCH_SIZE)
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        if merge:
            conn.execute(_merge_statement(len(batch)), _batch_parameters(batch))
        elif operation == "insert":
            conn.execute(_insert_statement(len(batch)), _batch_parameters(batch))
        else:
            conn.execute(_UPDATE_SQL, batch)
        logger.info(
            "Weights %s progress: %d/%d rows",
            operation,
            min(start + BATCH_SIZE, len(rows)),
            len(rows),
        )


_LATEST_SQL = text(
    f"""SELECT series_id, reference_date, vintage_date, weight, collected_at
    FROM (SELECT series_id, reference_date, vintage_date, weight, collected_at,
    ROW_NUMBER() OVER (PARTITION BY series_id, reference_date
    ORDER BY vintage_date DESC, collected_at DESC) AS rn
    FROM {_TABLE} WHERE reference_date >= :minimum_date) ranked WHERE rn = 1"""
)


def _as_date(value: Any) -> Any:
    """Normalize whatever a dialect returns for a DATE column into a date.

    PostgreSQL and Databricks return a ``date``; SQLite, which has no DATE type,
    returns the ISO string it stored. Comparing the two spellings as dictionary
    keys would silently miss every stored row and rewrite the whole panel, so the
    normalization happens here rather than at each call site.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value


def _latest(engine: Engine, minimum_date: date) -> dict[tuple[str, date], dict[str, Any]]:
    """Fetch the latest stored vintage per series and month."""
    with engine.connect() as conn:
        rows = conn.execute(_LATEST_SQL, {"minimum_date": minimum_date}).mappings().all()
    result: dict[tuple[str, date], dict[str, Any]] = {}
    for row in rows:
        result[(str(row["series_id"]), _as_date(row["reference_date"]))] = dict(row)
    return result


def upsert_weights(
    engine: Engine,
    weights_by_date: dict[date, dict[str, float]],
    collected_at: datetime | None = None,
) -> tuple[int, int]:
    """Write official basket weights idempotently and return ``(new, new_vintages)``."""
    collected_at = collected_at or datetime.now(UTC)
    today = collected_at.date()
    incoming: list[dict[str, Any]] = []
    for reference_date, weights in weights_by_date.items():
        for series_id, raw_weight in weights.items():
            weight = float(raw_weight)
            if math.isfinite(weight):
                incoming.append(
                    {
                        "series_id": series_id,
                        "reference_date": reference_date,
                        "weight": weight,
                        "collected_at": collected_at,
                    }
                )
    logger.info("Weights upsert: evaluating %d incoming weights", len(incoming))
    if not incoming:
        logger.info("No weight rows to upsert")
        return 0, 0
    existing = _latest(engine, min(row["reference_date"] for row in incoming))
    inserts: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []
    new_rows = 0
    new_vintages = 0
    for row in incoming:
        key = (row["series_id"], row["reference_date"])
        current = existing.get(key)
        if current is None:
            inserts.append({**row, "vintage_date": today})
            new_rows += 1
            continue
        if round(float(current["weight"]), ROUND_DECIMALS) == round(row["weight"], ROUND_DECIMALS):
            continue
        vintage = _as_date(current["vintage_date"])
        if vintage == today:
            updates.append({**row, "vintage_date": today})
        else:
            inserts.append({**row, "vintage_date": today})
            new_vintages += 1
    with engine.begin() as conn:
        merge = conn.dialect.name in _MERGE_DIALECTS
        _write_batches(conn, inserts, "insert", merge=False)
        _write_batches(conn, updates, "same-day update", merge=merge)
    logger.info(
        "Weights upsert: new=%d new_vintages=%d same_day_updates=%d",
        new_rows,
        new_vintages,
        len(updates),
    )
    return new_rows, new_vintages

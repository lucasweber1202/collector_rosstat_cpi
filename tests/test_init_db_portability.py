"""The production DDL must execute unchanged on PostgreSQL."""

from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import create_engine, inspect, text

from scripts.init_db import (
    CREATE_LOGS_TABLE,
    CREATE_METADATA_TABLE,
    CREATE_SCHEMA,
    CREATE_TIME_SERIES_TABLE,
    CREATE_WEIGHTS_TABLE,
    double_type,
)

POSTGRES_URL = os.getenv("COLLECTOR_TEST_PG_URL", os.getenv("COLLECTOR_DB_URL", ""))


def test_double_spelling_is_selected_per_dialect() -> None:
    """PostgreSQL rejects DOUBLE and Databricks rejects DOUBLE PRECISION."""
    assert double_type("postgresql") == "DOUBLE PRECISION"
    assert double_type("databricks") == "DOUBLE"


def test_ddl_uses_only_the_portable_type_vocabulary() -> None:
    """No statement may use a type spelling only one of the two dialects accepts."""
    joined = (
        f"{CREATE_METADATA_TABLE} {CREATE_TIME_SERIES_TABLE} "
        f"{CREATE_WEIGHTS_TABLE} {CREATE_LOGS_TABLE}"
    ).upper()
    for dialect_only in ("SERIAL", "JSONB", "AUTOINCREMENT", "NUMERIC", "FLOAT", "STRING"):
        assert not re.search(rf"\b{dialect_only}\b", joined), dialect_only


@pytest.mark.skipif(not POSTGRES_URL.startswith("postgresql"), reason="no PostgreSQL configured")
def test_real_ddl_runs_on_postgresql() -> None:
    engine = create_engine(POSTGRES_URL)
    schema = "collector_rosstat_cpi_ddl_probe"
    statements = [
        CREATE_SCHEMA.replace("collector_rosstat_cpi", schema),
        CREATE_METADATA_TABLE.replace("collector_rosstat_cpi", schema),
        CREATE_TIME_SERIES_TABLE.replace("collector_rosstat_cpi", schema).format(
            double=double_type("postgresql")
        ),
        CREATE_WEIGHTS_TABLE.replace("collector_rosstat_cpi", schema).format(
            double=double_type("postgresql")
        ),
        CREATE_LOGS_TABLE.replace("collector_rosstat_cpi", schema),
    ]
    try:
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
            # Running it twice proves every statement is IF NOT EXISTS safe.
            for statement in statements:
                conn.execute(text(statement))
        tables = set(inspect(engine).get_table_names(schema=schema))
        assert tables == {"metadata", "time_series", "weights", "logs"}
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        engine.dispose()

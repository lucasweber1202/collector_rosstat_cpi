"""Exercise fleet storage and run logging against isolated SQLite databases.

SQLite is a behavioral test backend, not PostgreSQL/Databricks certification.
Synthetic observations do not represent Rosstat CPI data.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

import main
from scripts import init_db
from scripts.run_logs import insert_run_log
from scripts.time_series import get_series_aggregates, upsert_time_series


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    sqlite3.register_converter("timestamp", lambda raw: datetime.fromisoformat(raw.decode()))
    engine = create_engine(
        "sqlite://", connect_args={"detect_types": sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES}
    )

    @event.listens_for(engine, "connect")
    def attach(connection, record) -> None:
        connection.execute(
            "ATTACH DATABASE ? AS collector_rosstat_cpi", (str(tmp_path / "store.db"),)
        )

    with engine.begin() as conn:
        conn.execute(text(init_db.CREATE_TIME_SERIES_TABLE.format(double="DOUBLE")))
        conn.execute(text(init_db.CREATE_METADATA_TABLE))
        conn.execute(
            text(
                init_db.CREATE_LOGS_TABLE.replace(
                    "id BIGINT GENERATED ALWAYS AS IDENTITY,",
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,",
                ).replace(",\n    CONSTRAINT pk_logs PRIMARY KEY (id)", "")
            )
        )
    yield engine
    engine.dispose()


def test_two_runs_and_revision_history(engine: Engine) -> None:
    month = date(2026, 1, 1)
    first = datetime(2026, 9, 10, tzinfo=UTC)
    later = datetime(2026, 9, 11, tzinfo=UTC)
    values = {month: {"SYNTHETIC_CPI_TEST": 100.0}}
    assert upsert_time_series(engine, values, first) == (1, 0)
    insert_run_log(engine, first, first, "success", "synthetic first write", None)
    assert upsert_time_series(engine, values, later) == (0, 0)
    insert_run_log(engine, later, later, "success", "synthetic unchanged write", None)
    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT COUNT(*) FROM collector_rosstat_cpi.time_series")).scalar()
            == 1
        )
        assert conn.execute(
            text("SELECT status FROM collector_rosstat_cpi.logs ORDER BY id")
        ).scalars().all() == ["success", "success"]
    assert upsert_time_series(engine, {month: {"SYNTHETIC_CPI_TEST": 101.0}}, later) == (0, 1)
    assert upsert_time_series(engine, {month: {"SYNTHETIC_CPI_TEST": 102.0}}, later) == (0, 0)
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT value FROM collector_rosstat_cpi.time_series ORDER BY vintage_date")
        ).scalars().all() == [100.0, 102.0]
    assert get_series_aggregates(engine)["SYNTHETIC_CPI_TEST"]["observation_count"] == 1


def test_clock_rollback_cannot_insert_backdated_revision(engine: Engine) -> None:
    data = {date(2026, 1, 1): {"SYNTHETIC_CPI_TEST": 100.0}}
    upsert_time_series(engine, data, datetime(2026, 9, 11, tzinfo=UTC))
    with pytest.raises(ValueError, match="earlier"):
        upsert_time_series(
            engine,
            {date(2026, 1, 1): {"SYNTHETIC_CPI_TEST": 101.0}},
            datetime(2026, 9, 10, tzinfo=UTC),
        )
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT value FROM collector_rosstat_cpi.time_series")
        ).scalars().all() == [100.0]


def test_failure_after_database_initialization_logs_once(
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "DATABASE_URL", "configured-for-test")
    monkeypatch.setattr(main, "missing_environment", list)
    monkeypatch.setattr(main, "build_engine", lambda: engine)
    monkeypatch.setattr(main, "init_db", lambda _: None)
    # Keep the test database alive after the orchestration releases its engine.
    monkeypatch.setattr(engine, "dispose", lambda: None)

    def fail(output: Path) -> dict:
        raise ValueError("controlled acquisition failure")

    monkeypatch.setattr(main, "research_sources", fail)
    assert main.run(["--research", "--output", str(tmp_path / "evidence")]) == 1
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT status, traceback FROM collector_rosstat_cpi.logs")).all()
        assert len(rows) == 1
        assert rows[0][0] == "error"
        assert "controlled acquisition failure" in rows[0][1]
        assert (
            conn.execute(text("SELECT COUNT(*) FROM collector_rosstat_cpi.time_series")).scalar()
            == 0
        )

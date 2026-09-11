"""The orchestrator must gate on validation and always write exactly one log row."""

from __future__ import annotations

import argparse
from datetime import date
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

import main as main_module
from scripts.extract import RosstatPublication


def _publication(headline_ytd: float = 104.67) -> RosstatPublication:
    """Return a minimal publication whose aggregation closes by construction."""
    jan, feb = date(2026, 1, 1), date(2026, 2, 1)
    weights = {
        "CPI_RU_RSTG_HEADLINE_1_MOM": 100.0,
        "CPI_RU_RSTG_AGGREGATE_2_MOM": 71.774,
        "CPI_RU_RSTG_AGGREGATE_6_MOM": 39.002,
        "CPI_RU_RSTG_AGGREGATE_7_MOM": 32.772,
        "CPI_RU_RSTG_AGGREGATE_9000_MOM": 28.226,
    }
    detail = {
        month: {
            "CPI_RU_RSTG_HEADLINE_1_MOM": 100.5,
            "CPI_RU_RSTG_AGGREGATE_2_MOM": 100.5,
            "CPI_RU_RSTG_AGGREGATE_6_MOM": 100.5,
            "CPI_RU_RSTG_AGGREGATE_7_MOM": 100.5,
            "CPI_RU_RSTG_AGGREGATE_9000_MOM": 100.5,
            "CPI_RU_RSTG_HEADLINE_1_YTD": 100.0 if month == jan else headline_ytd,
            "CPI_RU_RSTG_AGGREGATE_2_YTD": 100.0 if month == jan else 103.67,
            "CPI_RU_RSTG_AGGREGATE_6_YTD": 100.0 if month == jan else 102.8,
            "CPI_RU_RSTG_AGGREGATE_7_YTD": 100.0 if month == jan else 104.66,
            "CPI_RU_RSTG_AGGREGATE_9000_YTD": 100.0 if month == jan else 107.26,
        }
        for month in (jan, feb)
    }
    return RosstatPublication(
        observations={month: dict(values) for month, values in detail.items()},
        weights={jan: dict(weights), feb: dict(weights)},
        kipc={},
        files={},
        detail_panel=detail,
        headline_panel={},
    )


CATALOG = {
    series_id: {
        "classification": "RSTG",
        "measure": series_id.rsplit("_", 1)[1],
        "native_code": series_id.split("_")[4],
        "native_name": "Все товары и услуги",
        "level": series_id.split("_")[3],
        "source_url": "https://rosstat.gov.ru/storage/mediabank/ipc_spr_08-2026.xlsx",
        "release_name": "Rosstat, Consumer price indices",
        "parent_code": "",
    }
    for series_id in _publication().observations[date(2026, 1, 1)]
}
HIERARCHY = {
    code: {"level": level, "name": "n"}
    for code, level in (
        ("1", "HEADLINE"),
        ("2", "AGGREGATE"),
        ("6", "AGGREGATE"),
        ("7", "AGGREGATE"),
        ("9000", "AGGREGATE"),
    )
}


def _patch(
    monkeypatch: pytest.MonkeyPatch, engine: Engine, publication: RosstatPublication
) -> None:
    monkeypatch.setattr(main_module, "build_engine", lambda: engine)
    monkeypatch.setattr(main_module, "_preflight", lambda: None)
    monkeypatch.setattr(main_module, "collect_publication", lambda *_a, **_k: publication)
    monkeypatch.setattr(main_module, "get_series_catalog", lambda: CATALOG)
    monkeypatch.setattr(main_module, "get_hierarchy", lambda: HIERARCHY)
    monkeypatch.setattr(main_module, "get_last_publish_date", lambda: date(2026, 9, 11))
    monkeypatch.setattr(main_module, "init_db", lambda _engine: None)


def _logs(engine: Engine) -> list[tuple[Any, ...]]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT status, traceback FROM collector_rosstat_cpi.logs")).all()
    return [tuple(row) for row in rows]


def test_a_successful_run_writes_one_success_log(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, engine, _publication())
    assert main_module.run([]) == 0
    assert [status for status, _ in _logs(engine)] == ["success"]
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT COUNT(*) FROM collector_rosstat_cpi.time_series")
            ).scalar_one()
            > 0
        )


def test_a_failed_reconciliation_blocks_ingestion_and_logs_one_error(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, engine, _publication(headline_ytd=90.0))
    assert main_module.run([]) == 1
    logs = _logs(engine)
    assert [status for status, _ in logs] == ["error"]
    assert logs[0][1] and "bottom-up reconciliations failed" in logs[0][1]
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT COUNT(*) FROM collector_rosstat_cpi.time_series")
            ).scalar_one()
            == 0
        )


def test_a_mid_pipeline_failure_still_logs_one_error_row(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, engine, _publication())

    def explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("forced mid-pipeline failure")

    monkeypatch.setattr(main_module, "upsert_time_series", explode)
    assert main_module.run([]) == 1
    logs = _logs(engine)
    assert [status for status, _ in logs] == ["error"]
    assert "forced mid-pipeline failure" in logs[0][1]


def test_the_rewind_never_starts_before_the_configured_first_month() -> None:
    assert main_module._rewind_start(None) == main_module.DEFAULT_START_DATE
    assert main_module._rewind_start(date(2026, 8, 1)) == date(2026, 3, 1)
    assert main_module._rewind_start(date(1991, 2, 1)) == main_module.DEFAULT_START_DATE


def test_arguments_default_to_a_single_non_watching_run() -> None:
    args = main_module._parse_args([])
    assert isinstance(args, argparse.Namespace)
    assert args.watch is False
    assert args.export_validation is None
    assert args.start_date is None

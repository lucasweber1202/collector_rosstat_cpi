"""Standardized writes must be idempotent and keep vintages append-only."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from scripts.metadata import upsert_metadata
from scripts.time_series import upsert_time_series
from scripts.weights import assert_percentage_basket, upsert_weights

RUN_ONE = datetime(2026, 9, 11, 10, 0, tzinfo=UTC)
RUN_TWO = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(text(f"SELECT COUNT(*) FROM collector_rosstat_cpi.{table}")).scalar_one()
        )


def test_second_run_writes_nothing(
    engine: Engine,
    sample_panel: dict[date, dict[str, float | None]],
    sample_catalog: dict[str, dict[str, Any]],
) -> None:
    assert upsert_time_series(engine, sample_panel, RUN_ONE) == (4, 0)
    assert upsert_metadata(engine, sample_panel, RUN_ONE, sample_catalog) == (2, 0)
    before = (_count(engine, "time_series"), _count(engine, "metadata"))

    assert upsert_time_series(engine, sample_panel, RUN_TWO) == (0, 0)
    assert upsert_metadata(engine, sample_panel, RUN_TWO, sample_catalog) == (0, 0)
    assert (_count(engine, "time_series"), _count(engine, "metadata")) == before


def test_a_revision_adds_a_vintage_and_never_edits_the_old_one(
    engine: Engine, sample_panel: dict[date, dict[str, float | None]]
) -> None:
    upsert_time_series(engine, sample_panel, RUN_ONE)
    revised: dict[date, dict[str, float | None]] = {
        date(2026, 1, 1): {"CPI_RU_RSTG_HEADLINE_1_MOM": 101.70}
    }
    assert upsert_time_series(engine, revised, RUN_TWO) == (0, 1)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT vintage_date, value FROM collector_rosstat_cpi.time_series "
                "WHERE series_id='CPI_RU_RSTG_HEADLINE_1_MOM' AND reference_date='2026-01-01' "
                "ORDER BY vintage_date"
            )
        ).all()
    assert [float(value) for _, value in rows] == [101.62, 101.70]


def test_a_same_day_correction_updates_todays_row_only(
    engine: Engine, sample_panel: dict[date, dict[str, float | None]]
) -> None:
    upsert_time_series(engine, sample_panel, RUN_ONE)
    corrected: dict[date, dict[str, float | None]] = {
        date(2026, 1, 1): {"CPI_RU_RSTG_HEADLINE_1_MOM": 101.65}
    }
    later_same_day = RUN_ONE.replace(hour=18)
    upsert_time_series(engine, corrected, later_same_day)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT COUNT(*) FROM collector_rosstat_cpi.time_series "
                "WHERE series_id='CPI_RU_RSTG_HEADLINE_1_MOM' AND reference_date='2026-01-01'"
            )
        ).scalar_one()
    assert rows == 1


def test_weights_are_idempotent_and_percentage_checked(engine: Engine) -> None:
    basket = {date(2026, 1, 1): {"CPI_RU_RSTG_HEADLINE_1_MOM": 100.0}}
    assert upsert_weights(engine, basket, RUN_ONE) == (1, 0)
    assert upsert_weights(engine, basket, RUN_TWO) == (0, 0)
    assert_percentage_basket(engine)

    upsert_weights(engine, {date(2026, 2, 1): {"CPI_RU_RSTG_ITEM_111_MOM": 1000.0}}, RUN_ONE)
    with pytest.raises(ValueError, match="0-100 percent range"):
        assert_percentage_basket(engine)


def test_metadata_is_derived_from_the_database_not_the_collected_slice(
    engine: Engine,
    sample_panel: dict[date, dict[str, float | None]],
    sample_catalog: dict[str, dict[str, Any]],
) -> None:
    upsert_time_series(engine, sample_panel, RUN_ONE)
    upsert_metadata(engine, sample_panel, RUN_ONE, sample_catalog)
    rewound = {date(2026, 2, 1): sample_panel[date(2026, 2, 1)]}
    upsert_metadata(engine, rewound, RUN_TWO, sample_catalog)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT first_observation, observation_count, country, frequency, unit, eco_group "
                "FROM collector_rosstat_cpi.metadata WHERE series_id='CPI_RU_RSTG_HEADLINE_1_MOM'"
            )
        ).one()
    assert str(row[0]).startswith("2026-01-01")
    assert row[1] == 2
    assert (row[2], row[3], row[4], row[5]) == ("RUB", "monthly", "index", "consumer_prices")


def test_metadata_refuses_a_series_it_cannot_describe(
    engine: Engine, sample_panel: dict[date, dict[str, float | None]]
) -> None:
    upsert_time_series(engine, sample_panel, RUN_ONE)
    with pytest.raises(ValueError, match="No upstream metadata"):
        upsert_metadata(engine, sample_panel, RUN_ONE, {})


def test_non_finite_values_are_never_stored(engine: Engine) -> None:
    panel: dict[date, dict[str, float | None]] = {
        date(2026, 1, 1): {
            "CPI_RU_RSTG_HEADLINE_1_MOM": float("nan"),
            "CPI_RU_RSTG_ITEM_111_MOM": float("inf"),
            "CPI_RU_RSTG_AGGREGATE_6_MOM": None,
        }
    }
    assert upsert_time_series(engine, panel, RUN_ONE) == (0, 0)
    assert _count(engine, "time_series") == 0

"""Shared fixtures: an in-process SQLite database and synthetic Rosstat panels."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from scripts import init_db as init_db_module


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """Return a fresh file-backed database carrying the collector's real DDL.

    SQLite has no schemas, so the collector's ``schema.table`` names are mapped
    onto a second database file attached under that name on every new
    connection; the file (rather than ``:memory:``) keeps the data alive across
    the ``engine.dispose()`` that ``main.run`` performs. The DDL itself is the
    production statement - only its DOUBLE spelling differs by dialect, exactly
    as it does between PostgreSQL and Databricks.
    """
    attached = tmp_path / "collector_rosstat_cpi.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'main.sqlite'}")

    @event.listens_for(engine, "connect")
    def _attach(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.execute(f"ATTACH DATABASE '{attached}' AS collector_rosstat_cpi")

    monkeypatch.setattr(init_db_module, "CREATE_SCHEMA", "SELECT 1", raising=True)
    # SQLite spells identity columns differently; the production statement is
    # exercised on PostgreSQL by test_init_db_portability.
    monkeypatch.setattr(
        init_db_module,
        "CREATE_LOGS_TABLE",
        """
        CREATE TABLE IF NOT EXISTS collector_rosstat_cpi.logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP NOT NULL,
            status VARCHAR(20) NOT NULL,
            log_text VARCHAR(65535) NOT NULL,
            traceback VARCHAR(65535)
        )
        """,
        raising=True,
    )
    init_db_module.init_db(engine)
    yield engine
    engine.dispose()


def detail_workbook(months: dict[str, list[tuple[str, str, float, float, float, float]]]) -> bytes:
    """Build a workbook shaped like Rosstat's combined index/weights publication."""
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    contents = workbook.create_sheet("Содержание")
    contents["A1"] = "Содержание:"
    contents["A32"] = "Обновлено: "
    contents["A33"] = "11 сентября 2026 г."
    for title, rows in months.items():
        sheet = workbook.create_sheet(title.replace(" ", "")[:28])
        sheet["A1"] = "К содержанию"
        sheet["A3"] = f"Индексы потребительских цен по Российской Федерации за {title}"
        sheet["A5"] = "Наименование групп товаров (услуг) и товаров(услуг)-представителей"
        sheet["B5"] = "Локальный код группы / товара (услуги)-представителя"
        sheet["C5"] = "Структура потребительских расходов населения, в % к итогу"
        sheet["D5"] = "Индексы потребительских цен, в %"
        sheet["D6"] = "к предыдущему месяцу"
        sheet["E6"] = "к декабрю предыдущего года"
        sheet["F6"] = "к соответствующему  месяцу предыдущего года"
        for index, (name, code, weight, mom, ytd, yoy) in enumerate(rows, start=7):
            sheet.cell(index, 1, name)
            # Rosstat prints group rows in bold and representative items plain.
            sheet.cell(index, 1).font = Font(bold=not name.endswith(", кг"))
            sheet.cell(index, 2, code)
            sheet.cell(index, 3, weight)
            sheet.cell(index, 4, mom)
            sheet.cell(index, 5, ytd)
            sheet.cell(index, 6, yoy)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def headline_workbook(years: list[int], values: dict[int, list[float]]) -> bytes:
    """Build a workbook shaped like Rosstat's since-1991 headline publication."""
    months = [
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
    ]
    workbook = Workbook()
    workbook.remove(workbook.worksheets[0])
    contents = workbook.create_sheet("Содержание")
    contents["A16"] = "Обновлено: "
    contents["A17"] = "11 сентября 2026 г."
    sheet = workbook.create_sheet("01")
    sheet["A1"] = "Индексы потребительских цен на товары и услуги1) по Российской Федерации"
    sheet["A2"] = "К содержанию"
    for position, year in enumerate(years, start=2):
        sheet.cell(4, position, year)
    sheet.cell(5, 1, "к концу предыдущего месяца")
    for row, month in enumerate(months, start=6):
        sheet.cell(row, 1, month)
        for position, year in enumerate(years, start=2):
            sheet.cell(row, position, values[year][row - 6])
    sheet.cell(18, 1, "к декабрю предыдущего года")
    sheet.cell(19, 1, "декабрь")
    for position, year in enumerate(years, start=2):
        sheet.cell(19, position, 110.0)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


@pytest.fixture
def sample_panel() -> dict[date, dict[str, float | None]]:
    """Return a small two-month panel using real series identifiers."""
    return {
        date(2026, 1, 1): {
            "CPI_RU_RSTG_HEADLINE_1_MOM": 101.62,
            "CPI_RU_RSTG_ITEM_111_MOM": 100.4,
        },
        date(2026, 2, 1): {
            "CPI_RU_RSTG_HEADLINE_1_MOM": 100.73,
            "CPI_RU_RSTG_ITEM_111_MOM": 100.1,
        },
    }


@pytest.fixture
def sample_catalog() -> dict[str, dict[str, Any]]:
    """Return upstream descriptive rows matching ``sample_panel``."""
    common = {
        "classification": "RSTG",
        "measure": "MOM",
        "source_url": "https://rosstat.gov.ru/storage/mediabank/ipc_spr_08-2026.xlsx",
        "release_name": "Rosstat, Consumer price indices",
        "parent_code": "",
    }
    return {
        "CPI_RU_RSTG_HEADLINE_1_MOM": {
            **common,
            "native_code": "1",
            "native_name": "Все товары и услуги",
            "level": "HEADLINE",
        },
        "CPI_RU_RSTG_ITEM_111_MOM": {
            **common,
            "native_code": "111",
            "native_name": "Говядина (кроме бескостного мяса), кг",
            "level": "ITEM",
        },
    }

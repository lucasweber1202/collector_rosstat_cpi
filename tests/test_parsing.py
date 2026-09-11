"""Workbook and SDMX parsing must follow the published layouts, not guesses."""

from __future__ import annotations

from datetime import date

import pytest

from scripts.extract import (
    _month_day_year,
    _number,
    canonical_kipc,
    get_last_publish_date,
    kipc_parent,
    parse_monthly_detail,
    parse_monthly_headline,
    parse_sdmx,
)
from tests.conftest import detail_workbook, headline_workbook

SOURCE = "https://rosstat.gov.ru/storage/mediabank/ipc_spr_08-2026.xlsx"

ROWS = [
    ("Все товары и услуги", "1", 100.0, 99.92, 104.67, 106.33),
    ("Все товары", "2", 71.774, 100.11, 103.67, 105.77),
    ("Продовольственные товары", "6", 39.002, 99.74, 102.8, 105.08),
    ("Непродовольственные товары", "7", 32.772, 100.53, 104.66, 106.51),
    ("Услуги", "9000", 28.226, 99.46, 107.26, 107.85),
    ("Говядина (кроме бескостного мяса), кг", "111", 0.638, 100.51, 110.12, 114.29),
]


def test_detail_workbook_reads_every_published_measure_and_weight() -> None:
    payload = detail_workbook({"август 2026 г.": ROWS})
    observations, weights = parse_monthly_detail(payload, SOURCE)
    month = date(2026, 8, 1)
    assert set(observations) == {month}
    assert observations[month]["CPI_RU_RSTG_HEADLINE_1_MOM"] == 99.92
    assert observations[month]["CPI_RU_RSTG_HEADLINE_1_YTD"] == 104.67
    assert observations[month]["CPI_RU_RSTG_HEADLINE_1_YOY"] == 106.33
    assert observations[month]["CPI_RU_RSTG_ITEM_111_MOM"] == 100.51
    # Weights hang off the node's primary (month-on-month) series.
    assert weights[month]["CPI_RU_RSTG_HEADLINE_1_MOM"] == 100.0
    assert weights[month]["CPI_RU_RSTG_ITEM_111_MOM"] == 0.638


def test_detail_reference_month_comes_from_the_sheet_title() -> None:
    """Rosstat has shipped a mistyped sheet name; the printed title is authoritative."""
    payload = detail_workbook({"сентябрь 2025 г.": ROWS})
    observations, _ = parse_monthly_detail(payload, SOURCE)
    assert set(observations) == {date(2025, 9, 1)}


def test_detail_publication_stamp_is_read_from_the_contents_sheet() -> None:
    parse_monthly_detail(detail_workbook({"август 2026 г.": ROWS}), SOURCE)
    assert get_last_publish_date() == date(2026, 9, 11)


def test_headline_workbook_reads_only_the_month_on_month_block() -> None:
    years = [1991, 1992, 1993, 2024, 2025, 2026]
    payload = headline_workbook(
        years,
        {year: [{1992: 345.3, 2026: 101.62}.get(year, 100.0)] + [100.0] * 11 for year in years},
    )
    observations = parse_monthly_headline(payload, SOURCE)
    assert observations[date(1992, 1, 1)]["CPI_RU_RSTG_HEADLINE_1_MOM"] == 345.3
    assert observations[date(2026, 1, 1)]["CPI_RU_RSTG_HEADLINE_1_MOM"] == 101.62
    # The December-on-December block that follows must not become an observation.
    assert all(value != 110.0 for values in observations.values() for value in values.values())


SDMX = """<?xml version='1.0' encoding='UTF-8'?>
<message:StructureSpecificData xmlns:message="urn:m"><message:DataSet>
<Series DATA_DOMAIN="CPI" REF_AREA="RU" INDICATOR="PCPI_IX" FREQ="M" BASE_PER="2000=100">
<Obs TIME_PERIOD="2026-07" OBS_VALUE="981"/><Obs TIME_PERIOD="2026-06" OBS_VALUE="980.1"/>
</Series>
<Series DATA_DOMAIN="PPI" REF_AREA="RU" INDICATOR="PPPI_IX" FREQ="M" BASE_PER="2010=100">
<Obs TIME_PERIOD="2026-07" OBS_VALUE="329.8"/>
</Series>
</message:DataSet></message:StructureSpecificData>"""


def test_sdmx_reads_cpi_and_ignores_the_producer_price_series() -> None:
    observations = parse_sdmx(SDMX.encode(), "IX2000", SOURCE)
    assert observations[date(2026, 7, 1)] == {"CPI_RU_SDDS_HEADLINE_ALL_IX2000": 981.0}
    assert all("PPPI" not in series_id for values in observations.values() for series_id in values)


@pytest.mark.parametrize(
    ("raw", "expected"),
    # "104,672)" is Rosstat's spelling of 104.67 carrying footnote marker 2).
    [
        (104.67, 104.67),
        ("104,672)", 104.67),
        ("107,261)", 107.26),
        ("", None),
        ("…", None),
        (None, None),
    ],
)
def test_number_handles_the_published_cell_spellings(raw: object, expected: float | None) -> None:
    assert _number(raw) == expected


def test_publication_stamp_parsing() -> None:
    assert _month_day_year("11 сентября 2026 г.") == date(2026, 9, 11)
    assert _month_day_year("no date here") is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [("07.1.1.0.0", "07.1.1"), ("07.1.1.1", "07.1.1.1"), ("01.1.1.2.0.1", "01.1.1.2.0.1")],
)
def test_kipc_zero_segments_are_placeholders(code: str, expected: str) -> None:
    assert canonical_kipc(code) == expected


def test_kipc_parent_walks_up_to_the_nearest_published_ancestor() -> None:
    known = {"07", "07.1", "07.1.1", "07.1.1.1"}
    assert kipc_parent("07.1.1.1.0.1", known) == "07.1.1.1"
    assert kipc_parent("07.3.1.2.2", known) == "07"
    assert kipc_parent("07", known) is None

"""The structured identifier must round-trip and reject malformed input."""

from __future__ import annotations

import pytest

from scripts.extract import (
    LEVELS,
    MEASURES,
    build_series_id,
    normalise_node,
    parse_series_id,
)


@pytest.mark.parametrize(
    ("classification", "level", "code", "measure", "expected"),
    [
        ("RSTG", "HEADLINE", "1", "MOM", "CPI_RU_RSTG_HEADLINE_1_MOM"),
        ("RSTG", "AGGREGATE", "9000", "YOY", "CPI_RU_RSTG_AGGREGATE_9000_YOY"),
        ("RSTG", "ITEM", "111", "YTD", "CPI_RU_RSTG_ITEM_111_YTD"),
        ("RSTG", "GROUP", "8060.АГ", "MOM", "CPI_RU_RSTG_GROUP_8060-AG_MOM"),
        ("SDDS", "HEADLINE", "ALL", "IX2000", "CPI_RU_SDDS_HEADLINE_ALL_IX2000"),
    ],
)
def test_build_and_parse_round_trip(
    classification: str, level: str, code: str, measure: str, expected: str
) -> None:
    series_id = build_series_id(classification, level, code, measure)
    assert series_id == expected
    key = parse_series_id(series_id)
    assert (key.classification, key.level, key.measure) == (classification, level, measure)
    assert key.node == normalise_node(code)
    assert build_series_id(key.classification, key.level, key.node, key.measure) == series_id


def test_cyrillic_codes_do_not_collide_with_their_numeric_stem() -> None:
    """``8060`` and ``8060.АГ`` are different Rosstat codes and stay different."""
    assert normalise_node("8060") != normalise_node("8060.АГ")


@pytest.mark.parametrize(
    "series_id",
    [
        "CPI_RU_RSTG_HEADLINE_1",
        "CPI_RU_RSTG_HEADLINE_1_MOM_EXTRA",
        "CPI_GB_RSTG_HEADLINE_1_MOM",
        "CPI_RU_OTHER_HEADLINE_1_MOM",
        "CPI_RU_RSTG_SUBCLASS_1_MOM",
        "CPI_RU_RSTG_HEADLINE_1_LEVEL",
        "XPI_RU_RSTG_HEADLINE_1_MOM",
    ],
)
def test_parse_rejects_malformed_identifiers(series_id: str) -> None:
    with pytest.raises(ValueError):
        parse_series_id(series_id)


def test_build_rejects_unknown_vocabulary() -> None:
    with pytest.raises(ValueError):
        build_series_id("RSTG", "DIVISION", "1", "MOM")
    with pytest.raises(ValueError):
        build_series_id("RSTG", "HEADLINE", "1", "QOQ")


def test_every_level_and_measure_is_parseable() -> None:
    """No declared vocabulary value can produce an identifier the parser rejects."""
    for level in LEVELS:
        for measure in MEASURES:
            parse_series_id(build_series_id("RSTG", level, "1", measure))

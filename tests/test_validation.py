"""The bottom-up reconciliation must reproduce Rosstat's published aggregation."""

from __future__ import annotations

from datetime import date
from typing import Any

from scripts.validate import (
    FAIL,
    PASS,
    build_kipc_tree,
    validate_index_bottom_up,
    validate_kipc_weight_sums,
    validate_panel_quality,
    validate_source_agreement,
    validate_weight_sums,
)

HIERARCHY = {
    "1": {"level": "HEADLINE", "name": "Все товары и услуги"},
    "2": {"level": "AGGREGATE", "name": "Все товары"},
    "6": {"level": "AGGREGATE", "name": "Продовольственные товары"},
    "7": {"level": "AGGREGATE", "name": "Непродовольственные товары"},
    "9000": {"level": "AGGREGATE", "name": "Услуги"},
}
JAN, FEB = date(2026, 1, 1), date(2026, 2, 1)
# Published August 2026 figures; the December-based identity closes on them.
WEIGHTS = {
    "CPI_RU_RSTG_HEADLINE_1_MOM": 100.0,
    "CPI_RU_RSTG_AGGREGATE_2_MOM": 71.774,
    "CPI_RU_RSTG_AGGREGATE_6_MOM": 39.002,
    "CPI_RU_RSTG_AGGREGATE_7_MOM": 32.772,
    "CPI_RU_RSTG_AGGREGATE_9000_MOM": 28.226,
}


def _panel(headline_ytd: float) -> dict[date, dict[str, float | None]]:
    """Return a two-month panel whose children imply ``headline_ytd``."""
    return {
        JAN: {
            "CPI_RU_RSTG_HEADLINE_1_YTD": 100.0,
            "CPI_RU_RSTG_AGGREGATE_2_YTD": 100.0,
            "CPI_RU_RSTG_AGGREGATE_6_YTD": 100.0,
            "CPI_RU_RSTG_AGGREGATE_7_YTD": 100.0,
            "CPI_RU_RSTG_AGGREGATE_9000_YTD": 100.0,
        },
        FEB: {
            "CPI_RU_RSTG_HEADLINE_1_YTD": headline_ytd,
            "CPI_RU_RSTG_AGGREGATE_2_YTD": 103.67,
            "CPI_RU_RSTG_AGGREGATE_6_YTD": 102.8,
            "CPI_RU_RSTG_AGGREGATE_7_YTD": 104.66,
            "CPI_RU_RSTG_AGGREGATE_9000_YTD": 107.26,
        },
    }


def test_december_based_identity_reproduces_the_published_headline() -> None:
    """Rosstat's tree is 1 = {all goods, services} and all goods = {food, non-food}.

    (71.774 x 103.67 + 28.226 x 107.26) / 100 = 104.6833, within the published
    rounding of the official 104.67.
    """
    checks = validate_index_bottom_up(_panel(104.67), {JAN: WEIGHTS, FEB: WEIGHTS}, HIERARCHY)
    headline = [c for c in checks if c.node == "1" and c.reference == FEB.isoformat()]
    assert headline and all(check.result == PASS for check in headline)
    assert abs(headline[0].reconstructed - 104.6833) < 1e-3
    goods = [c for c in checks if c.node == "2" and c.kind == "index_dec_based"]
    # 39.002 x 102.80 + 32.772 x 104.66 over their 71.774 weight = 103.6497.
    assert goods and abs(goods[-1].reconstructed - 103.6497) < 1e-3


def test_a_broken_aggregate_is_reported_as_a_failure() -> None:
    checks = validate_index_bottom_up(_panel(101.00), {JAN: WEIGHTS, FEB: WEIGHTS}, HIERARCHY)
    failures = [check for check in checks if check.failed]
    assert failures and failures[0].node == "1"
    assert failures[0].result == FAIL


def test_weight_sums_follow_the_published_tree() -> None:
    checks = validate_weight_sums({FEB: WEIGHTS}, HIERARCHY)
    assert checks and all(check.result == PASS for check in checks)
    kinds = {check.kind for check in checks}
    assert kinds == {"weight_total", "weight_sum"}


def test_weight_total_detects_a_basket_that_is_not_a_percentage() -> None:
    broken = {**WEIGHTS, "CPI_RU_RSTG_HEADLINE_1_MOM": 1000.0}
    checks = validate_weight_sums({FEB: broken}, HIERARCHY)
    assert any(check.kind == "weight_total" and check.failed for check in checks)


def test_source_agreement_compares_the_two_headline_surfaces() -> None:
    detail = {FEB: {"CPI_RU_RSTG_HEADLINE_1_MOM": 100.73}}
    headline = {FEB: {"CPI_RU_RSTG_HEADLINE_1_MOM": 100.73}}
    assert all(check.result == PASS for check in validate_source_agreement(detail, headline))
    drifted = {FEB: {"CPI_RU_RSTG_HEADLINE_1_MOM": 105.0}}
    assert any(check.failed for check in validate_source_agreement(detail, drifted))


def test_kipc_tree_uses_placeholder_aware_parents() -> None:
    nodes = {
        "07": {"name": "ТРАНСПОРТ", "weight": 4.948},
        "07.1": {"name": "Покупка транспортных средств", "weight": 4.948},
        "07.1.1.0.0": {"name": "Автомобили", "weight": 4.811},
        "07.1.2": {"name": "Мотоциклы", "weight": 0.137},
    }
    tree = build_kipc_tree(nodes)
    assert tree["07.1.1"] == "07.1"
    assert tree["07.1.2"] == "07.1"
    assert tree["07"] is None
    checks = validate_kipc_weight_sums({2026: nodes})
    assert all(check.result == PASS for check in checks if check.kind == "kipc_weight_sum")


def test_panel_quality_rejects_structurally_broken_input() -> None:
    catalog: dict[str, dict[str, Any]] = {
        "CPI_RU_RSTG_HEADLINE_1_MOM": {},
        "CPI_RU_RSTG_ITEM_111_MOM": {},
    }
    observations: dict[date, dict[str, float | None]] = {
        date(2026, 2, 3): {"CPI_RU_RSTG_HEADLINE_1_MOM": -1.0}
    }
    problems = validate_panel_quality(observations, {FEB: {"CPI_RU_UNKNOWN": 1.0}}, catalog)
    assert any("not a month start" in problem for problem in problems)
    assert any("not a positive index" in problem for problem in problems)
    assert any("catalogued with no observation" in problem for problem in problems)
    assert any("weight but no series" in problem for problem in problems)


def test_clean_panel_reports_no_quality_problems() -> None:
    catalog: dict[str, dict[str, Any]] = {"CPI_RU_RSTG_HEADLINE_1_MOM": {}}
    observations: dict[date, dict[str, float | None]] = {
        FEB: {"CPI_RU_RSTG_HEADLINE_1_MOM": 100.73}
    }
    weights = {FEB: {"CPI_RU_RSTG_HEADLINE_1_MOM": 100.0}}
    assert validate_panel_quality(observations, weights, catalog) == []

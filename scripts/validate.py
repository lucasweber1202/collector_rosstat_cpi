"""Reconcile the collected panel against Rosstat's published aggregation.

Rosstat builds the CPI as a fixed-basket (Lowe/Laspeyres) index: the published
index against December of the previous year uses that year's consumer-expenditure
structure as fixed weights, so a parent's December-based index is the
weight-weighted arithmetic mean of its children's December-based indices. The
CPI manual Rosstat publishes at /storage/mediabank/cpi_ru(3).pdf states the same
identity ("сводный индекс ... может быть рассчитан исходя из ... промежуточных
индексов более высокого уровня").

The month-on-month index is the same aggregate expressed against the previous
month, so it is reconstructed with price-updated weights:

    phi_i(t) = w_i * I_i(t-1) / sum_j w_j * I_j(t-1)

where ``I_i(t-1)`` is the child's December-based index in the previous month.

Both reconstructions use only officially published values; nothing derived here
is written to the standardized tables.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date
from typing import Any, NamedTuple

from scripts.config import VALIDATION_TOLERANCE_PP, WEIGHT_TOLERANCE_PP
from scripts.extract import (
    HEADLINE_CODE,
    TREE_PARENTS,
    build_series_id,
    canonical_kipc,
    kipc_parent,
    normalise_node,
)

logger = logging.getLogger(__name__)

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


class Check(NamedTuple):
    """One reconciliation of a published aggregate against its components."""

    kind: str
    reference: str
    node: str
    measure: str
    official: float
    reconstructed: float
    difference: float
    tolerance: float
    result: str

    @property
    def failed(self) -> bool:
        """Whether this check breached its tolerance."""
        return self.result == FAIL


def _verdict(difference: float, tolerance: float) -> str:
    """Grade one residual against the tolerance, warning near the boundary."""
    magnitude = abs(difference)
    if magnitude <= tolerance / 2:
        return PASS
    if magnitude <= tolerance:
        return WARN
    return FAIL


def _series(level_of: dict[str, str], code: str, measure: str) -> str | None:
    """Return the series identifier of one local code, if it was collected."""
    level = level_of.get(normalise_node(code))
    return build_series_id("RSTG", level, code, measure) if level else None


def validate_index_bottom_up(
    observations: dict[date, dict[str, float | None]],
    weights: dict[date, dict[str, float]],
    hierarchy: dict[str, dict[str, Any]],
) -> list[Check]:
    """Rebuild every published parent from its children and grade the residual."""
    level_of = {node: row["level"] for node, row in hierarchy.items()}
    checks: list[Check] = []
    months = sorted(observations)
    previous = {month: months[index - 1] if index else None for index, month in enumerate(months)}
    for month in months:
        values = observations[month]
        basket = weights.get(month, {})
        for parent, children in TREE_PARENTS.items():
            checks.extend(_reconcile_dec_based(parent, children, level_of, values, basket, month))
            earlier = previous[month]
            if earlier is not None and earlier.year == month.year:
                checks.extend(
                    _reconcile_month_on_month(
                        parent, children, level_of, values, observations[earlier], basket, month
                    )
                )
    return checks


def _components(
    children: tuple[str, ...],
    level_of: dict[str, str],
    values: dict[str, float | None],
    basket: dict[str, float],
    measure: str,
) -> list[tuple[float, float]] | None:
    """Return ``[(weight, index)]`` for the children, or None when incomplete."""
    pairs: list[tuple[float, float]] = []
    for child in children:
        index_series = _series(level_of, child, measure)
        weight_series = _series(level_of, child, "MOM")
        if index_series is None or weight_series is None:
            return None
        index_value = values.get(index_series)
        weight = basket.get(weight_series)
        if index_value is None or weight is None:
            return None
        pairs.append((weight, index_value))
    return pairs


def _reconcile_dec_based(
    parent: str,
    children: tuple[str, ...],
    level_of: dict[str, str],
    values: dict[str, float | None],
    basket: dict[str, float],
    month: date,
) -> list[Check]:
    """Check the fixed-weight identity on the December-based index."""
    parent_series = _series(level_of, parent, "YTD")
    if parent_series is None:
        return []
    official = values.get(parent_series)
    pairs = _components(children, level_of, values, basket, "YTD")
    if official is None or not pairs:
        return []
    total = sum(weight for weight, _ in pairs)
    if total <= 0:
        return []
    rebuilt = sum(weight * index for weight, index in pairs) / total
    difference = rebuilt - official
    return [
        Check(
            "index_dec_based",
            month.isoformat(),
            parent,
            "YTD",
            official,
            rebuilt,
            difference,
            VALIDATION_TOLERANCE_PP,
            _verdict(difference, VALIDATION_TOLERANCE_PP),
        )
    ]


def _reconcile_month_on_month(
    parent: str,
    children: tuple[str, ...],
    level_of: dict[str, str],
    values: dict[str, float | None],
    earlier: dict[str, float | None],
    basket: dict[str, float],
    month: date,
) -> list[Check]:
    """Check the month-on-month index using price-updated basket weights."""
    parent_series = _series(level_of, parent, "MOM")
    if parent_series is None:
        return []
    official = values.get(parent_series)
    current = _components(children, level_of, values, basket, "MOM")
    carried = _components(children, level_of, earlier, basket, "YTD")
    if official is None or not current or not carried:
        return []
    updated = [weight * index for weight, index in carried]
    total = sum(updated)
    if total <= 0:
        return []
    rebuilt = sum(share * index for share, (_, index) in zip(updated, current, strict=True)) / total
    difference = rebuilt - official
    return [
        Check(
            "index_month_on_month",
            month.isoformat(),
            parent,
            "MOM",
            official,
            rebuilt,
            difference,
            VALIDATION_TOLERANCE_PP,
            _verdict(difference, VALIDATION_TOLERANCE_PP),
        )
    ]


def validate_weight_sums(
    weights: dict[date, dict[str, float]], hierarchy: dict[str, dict[str, Any]]
) -> list[Check]:
    """Check that the published basket adds up along the published tree."""
    level_of = {node: row["level"] for node, row in hierarchy.items()}
    checks: list[Check] = []
    for month in sorted(weights):
        basket = weights[month]
        headline = _series(level_of, HEADLINE_CODE, "MOM")
        if headline is not None and headline in basket:
            official = basket[headline]
            checks.append(
                Check(
                    "weight_total",
                    month.isoformat(),
                    HEADLINE_CODE,
                    "WEIGHT",
                    official,
                    100.0,
                    100.0 - official,
                    WEIGHT_TOLERANCE_PP,
                    _verdict(100.0 - official, WEIGHT_TOLERANCE_PP),
                )
            )
        for parent, children in TREE_PARENTS.items():
            parent_series = _series(level_of, parent, "MOM")
            if parent_series is None or parent_series not in basket:
                continue
            child_series = [_series(level_of, child, "MOM") for child in children]
            if any(series is None or series not in basket for series in child_series):
                continue
            official = basket[parent_series]
            rebuilt = sum(basket[series] for series in child_series if series)
            difference = rebuilt - official
            checks.append(
                Check(
                    "weight_sum",
                    month.isoformat(),
                    parent,
                    "WEIGHT",
                    official,
                    rebuilt,
                    difference,
                    WEIGHT_TOLERANCE_PP,
                    _verdict(difference, WEIGHT_TOLERANCE_PP),
                )
            )
    return checks


def build_kipc_tree(nodes: dict[str, dict[str, Any]]) -> dict[str, str | None]:
    """Return ``{kipc_code: parent_code}`` for one published KIPC year."""
    known = {canonical_kipc(code) for code in nodes}
    return {code: kipc_parent(code, known) for code in sorted(known)}


def validate_kipc_weight_sums(kipc: dict[int, dict[str, dict[str, Any]]]) -> list[Check]:
    """Check that each KIPC parent equals the sum of its published children.

    Rosstat's own KIPC workbook reuses a parent's code for one of its children in
    a handful of places, so a small number of nodes do not close. They are
    reported rather than silently repaired.
    """
    checks: list[Check] = []
    for year in sorted(kipc):
        # Callers may hold raw codes carrying Rosstat's zero placeholder
        # segments; the tree is defined over canonical codes, so fold first.
        nodes: dict[str, dict[str, Any]] = {}
        for code, node in kipc[year].items():
            nodes.setdefault(canonical_kipc(code), node)
        tree = build_kipc_tree(nodes)
        children: dict[str, list[str]] = defaultdict(list)
        for code, parent in tree.items():
            if parent is not None:
                children[parent].append(code)
        for parent, members in sorted(children.items()):
            official = nodes[parent]["weight"]
            rebuilt = sum(nodes[code]["weight"] for code in members)
            difference = rebuilt - official
            checks.append(
                Check(
                    "kipc_weight_sum",
                    str(year),
                    parent,
                    "WEIGHT",
                    official,
                    rebuilt,
                    difference,
                    WEIGHT_TOLERANCE_PP,
                    _verdict(difference, WEIGHT_TOLERANCE_PP),
                )
            )
        roots = [code for code, parent in tree.items() if parent is None]
        total = sum(nodes[code]["weight"] for code in roots)
        checks.append(
            Check(
                "kipc_division_total",
                str(year),
                "0",
                "WEIGHT",
                100.0,
                total,
                total - 100.0,
                WEIGHT_TOLERANCE_PP,
                _verdict(total - 100.0, WEIGHT_TOLERANCE_PP),
            )
        )
    return checks


def validate_source_agreement(
    detail_panel: dict[date, dict[str, float]],
    headline_panel: dict[date, dict[str, float]],
) -> list[Check]:
    """Compare the two Rosstat surfaces that publish the same headline index.

    ``ipc_mes`` and ``ipc_spr`` both publish the month-on-month index for the
    four headline aggregates over their overlap. A disagreement means one of the
    two parsers has drifted from its workbook layout, or that the two official
    files were refreshed at different times.
    """
    checks: list[Check] = []
    for month in sorted(set(detail_panel) & set(headline_panel)):
        detail, headline = detail_panel[month], headline_panel[month]
        for series_id, official in sorted(headline.items()):
            other = detail.get(series_id)
            if other is None:
                continue
            difference = other - official
            checks.append(
                Check(
                    "surface_agreement",
                    month.isoformat(),
                    series_id,
                    "MOM",
                    official,
                    other,
                    difference,
                    VALIDATION_TOLERANCE_PP,
                    _verdict(difference, VALIDATION_TOLERANCE_PP),
                )
            )
    return checks


def validate_panel_quality(
    observations: dict[date, dict[str, float | None]],
    weights: dict[date, dict[str, float]],
    catalog: dict[str, dict[str, Any]],
) -> list[str]:
    """Return every data-quality problem that must stop ingestion.

    These are structural guarantees the standardized tables depend on: a series
    with no usable observation, a value that is not a finite positive index, a
    reference date that is not the first day of a month, a weight without a
    series, or a duplicate identifier. Anything reported here is a hard error;
    softer anomalies are logged by the reconciliation checks instead.
    """
    problems: list[str] = []
    seen: dict[str, int] = defaultdict(int)
    for month, values in observations.items():
        if month.day != 1:
            problems.append(f"{month} is not a month start; the collector is monthly")
        for series_id, value in values.items():
            seen[series_id] += 1
            if value is None:
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                problems.append(f"{series_id}@{month} is not a finite number: {value!r}")
            elif value <= 0:
                problems.append(f"{series_id}@{month} is not a positive index: {value!r}")
    empty = sorted(series_id for series_id in catalog if seen.get(series_id, 0) == 0)
    problems.extend(f"{series_id} was catalogued with no observation" for series_id in empty)
    unknown = sorted(
        {series_id for values in observations.values() for series_id in values} - set(catalog)
    )
    problems.extend(
        f"{series_id} has observations but no upstream metadata" for series_id in unknown
    )
    orphan_weights = sorted(
        {series_id for values in weights.values() for series_id in values} - set(catalog)
    )
    problems.extend(f"{series_id} has a weight but no series" for series_id in orphan_weights)
    return problems


def validate_index_base_stability(
    observations: dict[date, dict[str, float | None]], catalog: dict[str, dict[str, Any]]
) -> list[str]:
    """Return every SDMX series whose published index reference period changed.

    The two SDMX messages carry different reference periods (2000=100 and
    2010=100) and are stored as separate series precisely so a rebasing can
    never be mixed into one history. This check asserts that the base period
    attribute the message declares still matches the identifier it was stored
    under.
    """
    from scripts.extract import SDMX_BASE_PERIODS

    problems: list[str] = []
    for series_id, row in catalog.items():
        expected = SDMX_BASE_PERIODS.get(str(row.get("measure")))
        if expected is None:
            continue
        published = str(row.get("base_period", expected))
        if published != expected:
            problems.append(
                f"{series_id} declares index reference {published!r}, expected {expected!r}"
            )
    return problems


def summarize(checks: list[Check]) -> dict[str, dict[str, int]]:
    """Return the PASS/WARN/FAIL tally per check kind."""
    tally: dict[str, dict[str, int]] = defaultdict(lambda: {PASS: 0, WARN: 0, FAIL: 0})
    for check in checks:
        tally[check.kind][check.result] += 1
    return dict(tally)


def log_validation_summary(
    checks: list[Check], gated_kinds: frozenset[str] | None = None
) -> dict[str, dict[str, int]]:
    """Log the reconciliation tally and the worst residual of each kind.

    A breach of a gating check stops the run and is logged as an error. A breach
    of a diagnostic check reports a defect in Rosstat's own published
    classification rather than in this collector, so it is logged as a warning
    and listed in the audit workbook.
    """
    gated_kinds = gated_kinds if gated_kinds is not None else frozenset()
    tally = summarize(checks)
    for kind, counts in sorted(tally.items()):
        worst = max(
            (check for check in checks if check.kind == kind),
            key=lambda check: abs(check.difference),
            default=None,
        )
        detail = (
            f" worst={worst.difference:+.4f} at {worst.node}@{worst.reference}" if worst else ""
        )
        logger.info(
            "Validation %s: pass=%d warn=%d fail=%d%s",
            kind,
            counts[PASS],
            counts[WARN],
            counts[FAIL],
            detail,
        )
    diagnostics = 0
    for check in checks:
        if not check.failed:
            continue
        if check.kind in gated_kinds:
            logger.error(
                "Bottom-up FAIL %s %s %s: official=%.4f reconstructed=%.4f diff=%+.4f (tol %.4f)",
                check.kind,
                check.node,
                check.reference,
                check.official,
                check.reconstructed,
                check.difference,
                check.tolerance,
            )
        else:
            diagnostics += 1
    if diagnostics:
        logger.warning(
            "%d diagnostic reconciliations do not close; they grade Rosstat's published "
            "classification codes and are listed in the audit workbook",
            diagnostics,
        )
    return tally

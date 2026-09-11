# Repository Instructions — collector_rosstat_cpi

Read `MASTER_MACRO_COLLECTOR_GUIDELINES.md` completely before planning or modifying collector files. It is the authoritative consolidated fleet contract and overrides stale examples in copied skills.

This repository is the standalone Russia CPI collector. It is not a governance hub and must not become a shared framework.

## Approved intake

- SOURCE: `ROSSTAT`
- DATASET: `CPI`
- SOURCE_NAME: Federal State Statistics Service (Rosstat)
- RELEASE_NAME: Consumer Price Index and Structure of Consumer Expenditures
- COUNTRY / fleet code: `RUB`
- COLLECTOR_KIND: `forecast-target`
- INTENDED_FREQUENCY: `monthly`
- AUTH: `none` unless current official documentation proves otherwise
- DOCS/source root: `https://rosstat.gov.ru/statistics/price`
- TARGET_SERIES: `CURATE` — national monthly CPI index levels plus the official KIPC hierarchy and consumer-expenditure weights required for auditable bottom-up reconstruction

The user has approved building this collector. A Work/Codex/Claude task that explicitly instructs implementation may present its plan and continue without pausing for another approval, unless a material schema deviation or unresolved source ambiguity would require changing the fleet contract.

## Mandatory references

Before source-specific implementation, inspect:

1. This repository's `MASTER_MACRO_COLLECTOR_GUIDELINES.md`.
2. `https://github.com/lucasweber1202/Coletores` for the current governance state and relevant `.github/skills/`.
3. `https://github.com/guimasuko/collector_template` for the live pilot/root `GUIDELINES.md` and `FORECAST_TARGET_GUIDELINES.md`.
4. `https://github.com/lucasweber1202/collector_ons_cpi` as a CPI forecast-target reference for weights, hierarchy, validation, and analyst export patterns — not as a source-specific template.
5. Current official Rosstat documentation and exact official files/endpoints. Never infer an endpoint, workbook layout, native series ID, unit, weight regime, publication date, revision rule, or hierarchy from memory.

## Scaffold status

The branch may already contain source-agnostic files copied from the UK collector (`scripts/databricks_engine.py`, `scripts/db.py`, `scripts/run_logs.py`, `scripts/time_series.py`) and fleet editor settings. Treat those as reusable baseline code, but reconcile them against the current pilot before final handoff.

Do not copy ONS-specific extraction, metadata mappings, weight transformations, validation tolerances, release dates, or hierarchy assumptions into Rosstat code unless official Rosstat evidence independently supports the same behavior.

## Release bar

Do not claim the collector is ready until source fidelity, structured IDs, official weights, hierarchy reconstruction, sampled official-value checks, vintage semantics, PostgreSQL/Databricks compatibility, failure logging, two-run idempotency, security review, diff review, and every applicable Phase 8 forecast-target check have been completed or explicitly documented as blocked by an external source limitation.

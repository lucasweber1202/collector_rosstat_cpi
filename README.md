# collector_rosstat_cpi

Russia national monthly Consumer Price Index collector for the Federal State Statistics Service (Rosstat).

> **Status: scaffold / source research required.** This repository is not production-ready yet. The source-specific Rosstat extraction, series curation, hierarchy, weights, validation, metadata, orchestration, and release behavior must be implemented and verified against current official Rosstat files and methodology before use.

## Approved scope

- Source: Federal State Statistics Service (Rosstat)
- Dataset: Consumer Price Index (CPI)
- Fleet code: `RUB`
- Collector kind: `forecast-target`
- Intended modelling frequency: monthly
- Geographic scope: Russian Federation / national
- Official source root: https://rosstat.gov.ru/statistics/price
- Target coverage: curated national monthly CPI index levels, KIPC hierarchy, and official consumer-expenditure weights required for auditable bottom-up reconstruction where supported by the official source

## Governance

Read `MASTER_MACRO_COLLECTOR_GUIDELINES.md` and `.github/copilot-instructions.md` before modifying the collector. The consolidated master guideline overrides stale examples in copied skills.

The UK CPI collector at `https://github.com/lucasweber1202/collector_ons_cpi` is a structural reference for forecast-target weights, hierarchy, validation, and analyst export patterns only. ONS-specific source assumptions must not be copied into Rosstat logic.

## Preloaded reusable scaffold

The current scaffold already contains source-agnostic database/runtime pieces that can be reconciled against the live pilot and reused:

- `scripts/databricks_engine.py`
- `scripts/db.py`
- `scripts/run_logs.py`
- `scripts/time_series.py`
- fleet `.gitignore` and VS Code settings
- collector build, series-selection, API-docs, and verification guidance

Source-specific modules are intentionally absent until official Rosstat research verifies their inputs and behavior.

# Instructions for Coding Agents

Read `MASTER_MACRO_COLLECTOR_GUIDELINES.md` completely before planning or modifying collector files, then read `.github/copilot-instructions.md`.

This is the standalone `collector_rosstat_cpi` repository. Keep it self-contained and deliberately boring: no shared core, base collector, plugin framework, ORM layer, migrations, or undocumented schema extensions.

The approved scope is Russia national monthly CPI from Rosstat as a `forecast-target`, including the official index hierarchy and official consumer-expenditure weights needed for bottom-up reconstruction when the source makes them available. Use `RUB` for the fleet country/currency code and `consumer_prices` for the economic group unless current fleet governance has changed.

Before writing source-specific code, verify the current official Rosstat files/endpoints and methodology. Do not guess native IDs, workbook layouts, units, frequency, weight regimes, publication dates, or revision behavior.

Use `collector_ons_cpi` only as a structural CPI/weights reference. Rosstat-specific extraction, hierarchy, transformations, tolerances, and metadata must be justified independently from Rosstat evidence.

Before declaring readiness, complete source verification, two-run idempotency, failure-path logging, security review, diff review, and every applicable forecast-target Phase 8 check in the master guideline.

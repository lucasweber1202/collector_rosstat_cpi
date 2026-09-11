# Claude Code / Work Instructions

Read `MASTER_MACRO_COLLECTOR_GUIDELINES.md` and `.github/copilot-instructions.md` completely before acting. The master guideline is authoritative when an older copied skill conflicts with it.

This repository is the standalone Russia CPI collector. The user has already approved implementation of the Rosstat CPI collector, so after producing an internal implementation plan continue executing it rather than stopping solely for another plan approval. Stop only if official-source research exposes a material ambiguity that would require changing the fleet schema/contract.

Research Rosstat first. Confirm exact official XLSX/API/document endpoints, native series identifiers, index representation, KIPC hierarchy, consumer-expenditure weights, historical weight regimes, methodology/rebasing, publication timing, revision behavior, and one or more sample observations before finalizing `extract.py` or weight logic.

Inspect `lucasweber1202/collector_ons_cpi` for reusable forecast-target patterns, but do not carry ONS-specific assumptions into Rosstat code. Preserve the generic scaffold already present unless reconciliation with the live pilot proves a change is required.

Do not declare completion until the full applicable Phase 8 checklist is evidenced, including bottom-up reconciliation, official-weight preservation, idempotency, failure logging, security, and diff review.

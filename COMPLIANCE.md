# Rosstat CPI — implementation status and verification record

Status: **source research blocked; scaffold only; not production-ready**.
Investigation date: 2026-09-11 UTC.
Existing branch: `agent/rosstat-scaffold`; existing draft PR: #1.
Baseline inspected: `ff32d147dad83aea7ef63c4ff93bdde74335bbf6`.

This document records incomplete work, not certification. No Rosstat parser,
series mapping, weight mathematics, or runnable ingestion pipeline has been
implemented in this investigation. No schema incompatibility has been established.

## Verified repository facts

- Local master guideline is byte-identical to the governance master at
  `lucasweber1202/Coletores` commit
  `d950ec6956b1d2aa0ac17c63efd5989ce89b8f0a`.
- Existing `scripts/databricks_engine.py`, `scripts/db.py`,
  `scripts/run_logs.py`, and `scripts/time_series.py` are byte-identical
  to UK commit `6511393ec11ed890c9bd1344036350c0858db425`.
  This comparison is not a runtime verification of these modules.
- Local master, copilot instructions, AGENTS.md, CLAUDE.md, build-collector,
  series-selection, get-api-docs, and verification-loop instructions were read.
- UK COMPLIANCE.md, init_db.py and config.py were inspected. A complete UK
  implementation/test review remains pending.
- The linked `guimasuko/collector_template` root listing contains
  .github/, .vscode/, GUIDELINES.md and FORECAST_TARGET_GUIDELINES.md,
  but no scripts/ or executable pilot. The requested
  scripts/databricks_engine.py returned 404.
  Its guidelines were retrieved through the GitHub connector; a full
  executable-pilot comparison remains pending.
- UK documents an approved original_weights key of
  (series_id, reference_date, vintage_date), retaining weight_base_year.
  Whether and how Rosstat needs that exception remains unverified.
- The UK implementation itself explicitly has remaining release gates.
  Reusing its code is not evidence of PostgreSQL/Databricks certification.

## Reproducible source-access failure

Direct HTTPS GET and HEAD requests to the official landing page returned
HTTP 502. The GET response body was:

```text
502 Bad Gateway
Certificate verify failed: unable to get local issuer certificate
```

The research service returned 502 for all five pages below. A separate
browser navigation to the landing page displayed the same certificate error.
This establishes an access limitation in this environment, not that Rosstat
is globally unavailable or that the source lacks the requested data.
TLS verification was not disabled.

| Official URL discovered | Search result label / purpose | Inspection result |
| --- | --- | --- |
| https://rosstat.gov.ru/statistics/price | Prices and inflation landing page | GET/HEAD/browser 502 |
| https://rosstat.gov.ru/free_doc/new_site/prices/bd/bd_1902003.htm | CPI in KIPC grouping | Research open 502 |
| https://rosstat.gov.ru/storage/mediabank/tab-KIPC.htm | Consumer expenditure structure in KIPC grouping | Research open 502 |
| https://rosstat.gov.ru/free_doc/new_site/prices/ipc_met.htm | CPI and average prices methodology links | Research open 502 |
| https://rosstat.gov.ru/bgd/free/B00_24/IssWWW.exe/Stg/d000/I000111R.HTM | Summary methodology | Research open 502 |

These are discovered official page URLs, **not verified workbook endpoints**.
Search snippets are insufficient evidence for workbook layout, index
representation, numerical values, hierarchy or methodology.
No source XLSX was successfully downloaded. No API/EMISS alternative has
been verified. No assumptions about fixed-base levels, MoM, normalization,
annual regimes or geographic aggregation have been incorporated into code.

Reproduce without weakening TLS:

```bash
curl --fail-with-body --connect-timeout 10 --max-time 25 https://rosstat.gov.ru/statistics/price
```

## Implementation plan to resume when source documents are accessible

1. Finish reading the reference guidelines and the complete UK implementation.
   Identify the executable fleet pilot referenced by governance.
2. Inspect and download actual Rosstat headline, KIPC indices, historical
   expenditure weights, post-2025 combined publications, classifier,
   methodology applicable in 2026, and release-calendar documents.
   Record exact URLs, sheet/header layouts, coverage and published precision.
3. Compare official downloads with API/EMISS/Data Showcase coverage. Choose
   verified acquisition endpoints; determine representation and native IDs.
4. Implement config/dependencies, extract.py and source-specific regression
   tests. Verify national scope, parseable IDs, dates, values and hierarchy.
5. Implement only the weight regime/storage semantics supported by evidence.
   Preserve originals and prove any operational transformation quantitatively.
6. Implement validation gates and audit export; then orchestrate canonical
   observation writes before metadata, logging and release monitoring.
7. Run real-source parsing and sampling, PostgreSQL and Databricks checks,
   two unchanged-source runs, revision/same-day vintage tests and a controlled
   failure. Complete security and diff reviews before changing draft status.

## Verification summary

| Gate / requested result | Status | Evidence / remaining work |
| --- | --- | --- |
| Branch/PR identity | PASS | Existing branch and draft PR #1 inspected |
| Master versus Coletores | PASS | Byte comparison |
| Four scaffold modules versus UK | PASS | Byte comparison |
| Executable live-pilot comparison | PENDING | Linked template has no executable scripts |
| Real-source download/parser | BLOCKED | HTTPS 502 certificate error |
| Chosen source files/API | UNVERIFIED | Page discovery only |
| Methodology / national scope / native IDs | UNVERIFIED | Source content inaccessible |
| Number of series / hierarchy coverage | NOT MEASURED | No parsed official data |
| First/last observation | NOT MEASURED | No parsed official data |
| Weight regimes / normalization | UNVERIFIED | No inspected official weights |
| Bottom-up / tolerance / maximum residual | NOT EXECUTED | Formula and precision unverified |
| Build/import, lint and source tests | NOT EXECUTED | No implementation added |
| PostgreSQL / Databricks pipeline | NOT EXECUTED | No runnable pipeline |
| First/second run counts / metadata no-op | NOT EXECUTED | No source/database replay |
| Controlled error and exactly one error log | NOT EXECUTED | No runnable pipeline |
| Security review | LIMITED | No executable changes; TLS retained; no credentials in this document |
| Diff review | DOCUMENTATION ONLY | This status record is the only intended file addition |

## Inspect current values after implementation

The following is the canonical query for a future populated database.
It has not been executed here; it does not imply that the table exists.
On Databricks select catalog `macrobond_inhouse` first.

```sql
SELECT series_id, reference_date, value, vintage_date, collected_at
FROM (
    SELECT series_id, reference_date, value, vintage_date, collected_at,
           ROW_NUMBER() OVER (
               PARTITION BY series_id, reference_date
               ORDER BY vintage_date DESC, collected_at DESC
           ) AS rn
    FROM collector_rosstat_cpi.time_series
) ranked
WHERE rn = 1
ORDER BY series_id, reference_date;
```

To unblock offline source inspection, original Rosstat workbooks plus the
applicable methodology/classifier documents can be supplied with their
official download URLs and download dates. Live discovery, release monitoring
and live acquisition must still be verified in an environment able to reach
Rosstat successfully with certificate verification enabled.

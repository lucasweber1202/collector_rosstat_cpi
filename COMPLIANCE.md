# Rosstat CPI — verification status

**Status: partial implementation; not ready for production or merge.**
Continue `agent/rosstat-scaffold`. PR #1 was already merged at the previous
head `3b558c15ca15781e2410c0282c1ea6fe401ae91d` when final verification ran.
The implementation commit `4b038bfc67d20fbe11116f417f2649c0d1b87605` is on this
branch but is not included in that merged PR or main. No replacement PR was
created because the task specified updating PR #1 only. The closed PR body was
updated with these facts; no merge was performed during this implementation. This replaces the earlier
research-only status record; the repository now includes working acquisition
and database initialization commands, but no CPI ingestion pipeline.

## Implemented and reused

- `.env.example`, `pyproject.toml`, `requirements.txt`: deployment dependencies,
  HTTP settings and explicit database configuration. No secrets or dotenv dependency.
- `scripts/config.py`: adapted from UK configuration; exact Rosstat schema name;
  no unverified start date, weight regime, tolerance or series mapping.
- `scripts/init_db.py`: standard three-table DDL from UK, including its 64-bit
  float spelling adaptation. No new standardized columns or additional tables.
- `scripts/source_research.py`: single-client official document acquisition,
  allowlisted HTTPS, manually validated redirects, bounded retries and sizes,
  candidate discovery, SHA-256 traceability, workbook inspection and manifest.
  This flat module is a development research command, not `extract.py` and not
  a substitute for the required official-layout parser.
- `main.py`: explicit `--research` and `--init-db` commands; one best-effort
  database run log when configured; research without DB requires no credentials.
- `scripts/time_series.py`: inherited writer plus one regression fix: reject
  a changed observation if the collection date predates its current vintage.
- `tests/test_source_research.py`, `tests/test_persistence.py`: 25 meaningful
  synthetic boundary/persistence tests. No synthetic values are deployed.

Master guideline still matches governance at Coletores commit
`d950ec6956b1d2aa0ac17c63efd5989ce89b8f0a`.
The original four generic modules matched UK commit
`6511393ec11ed890c9bd1344036350c0858db425`; only the documented time_series guard
now differs. db.py, databricks_engine.py and run_logs.py remain unchanged.
The linked guimasuko/collector_template root contains governance documents and
editor/agent settings, but no executable scripts. A live executable-pilot
comparison remains pending. The UK reference also has unresolved release gates;
copying its code does not certify this collector.

## Official-source investigation and measured live result

Official search located these documents. Labels identify search results, not
verified content. The current live acquisition used timeout 10 seconds and one
retry, with TLS verification and the environment's configured transport retained.

| Official URL | Purpose | Live result |
| --- | --- | --- |
| https://rosstat.gov.ru/statistics/price | Prices and inflation landing page | HTTP 502 |
| https://rosstat.gov.ru/free_doc/new_site/prices/bd/bd_1902003.htm | KIPC CPI page | HTTP 502 |
| https://rosstat.gov.ru/storage/mediabank/tab-KIPC.htm | KIPC expenditure weights page | HTTP 502 |
| https://rosstat.gov.ru/free_doc/new_site/prices/ipc_met.htm | CPI methodology links | HTTP 502 |
| https://rosstat.gov.ru/bgd/free/B00_24/IssWWW.exe/Stg/d000/I000111R.HTM | Summary methodology | HTTP 502 |
| https://55.rosstat.gov.ru/storage/mediabank/metod_ipc_2026.pdf | Published 2026 methodology document | HTTP 502 |

Additional direct requests to eng.rosstat.gov.ru and 52.rosstat.gov.ru also returned
502 with `Certificate verify failed: unable to get local issuer certificate`.
Earlier browser navigation confirmed the same certificate error. This is an
access failure in this environment, not proof that Rosstat is globally unavailable.
API/EMISS alternatives were searched but no usable official endpoint was verified.

Actual CLI result: **0 downloaded documents, 0 workbooks, 6 recorded errors,
exit code 1, no observations written**. The manifest preserves individual failures.
No successful official data acquisition, CPI representation, national series count,
first/last period, KIPC mapping, English terminology, weight regime, formula,
normalization, reconstruction tolerance or maximum residual can be reported.

## Verification summary

| Gate | Result | Scope |
| --- | --- | --- |
| Import/build | PASS | Compilation and CLI help |
| Lint/format | PASS | Modified Python modules and tests |
| Type check | SKIP | No mypy/pyright configuration |
| Tests | PASS | 25 tests with synthetic fixtures |
| Unchanged second write | PASS, LIMITED | Synthetic observation writer in SQLite: first (1,0), second (0,0); two success logs |
| Later/same-day revisions | PASS, LIMITED | Historical value preserved; new vintage and same-day update verified |
| Backdated revision rejection | PASS | Reproduced failure before fix; regression now passes |
| Controlled failure | PASS, LIMITED | Acquisition failure after DB initialization: exactly one error log with traceback, zero observations |
| Metadata idempotency | NOT EXECUTED | Source-specific metadata builder absent |
| PostgreSQL/Databricks | NOT EXECUTED | No configured Databricks; local PostgreSQL installation failed due runtime package-manager permissions |
| Live Rosstat data | BLOCKED | Six HTTP 502 failures; nonzero exit |
| Bottom-up / weights / hierarchy | NOT IMPLEMENTED | Source mathematics and layouts unverified |
| Security | PASS, LIMITED | HTTPS allowlist, redirect checks, byte/ZIP budgets, secure XML requirement, sanitized transport errors, no credentials in changes |
| Dependency vulnerability scan | SKIP | No automated vulnerability audit executed |
| Diff review | PASS | Intended source/test/documentation files only; no downloaded binaries, .env or generated reports committed |

Security-specific parser dependency `defusedxml` is required by the openpyxl
security guidance: https://openpyxl.readthedocs.io/en/stable/ . The collector
refuses XLSX inspection when secure XML support is disabled. HTTP behavior follows
https://www.python-httpx.org/advanced/clients/ .

## Remaining acceptance work

1. Obtain official documents with valid TLS in the execution environment; inspect
   their complete layouts, classification, representation and 2026 methodology.
2. Verify current governance in full and reconcile against the executable pilot.
3. Implement national series selection, structured-ID parsing, metadata generation,
   historical extraction and official weight preservation using actual source data.
4. Determine Rosstat-specific regimes and formula; apply the approved UK schema
   exception only if it actually matches Rosstat requirements. No schema blocker
   has yet been established.
5. Implement quantitative reconstruction and mandatory gates, analyst export,
   release monitoring, real-source sampling and historical revision behavior.
6. Run the complete source/database pipeline twice on PostgreSQL and Databricks,
   plus failure-path and final source/security verification. Keep the new code
   unmerged until these gates and a new review are completed.

## Canonical query after future ingestion

The query has not been run on Rosstat data. On Databricks select catalog
`macrobond_inhouse` first.

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

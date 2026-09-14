# Rosstat CPI — implementation status and verification record

**Governance status: `verification`.** The implemented code and recorded source,
PostgreSQL, idempotency, failure-path and quality evidence support promotion from
`building`. Mandatory external runtime evidence remains open, so this is not
`ready`.

Status: **implemented and verified against the live official source**.
Verification date: 2026-09-11 UTC. Source publication observed: 2026-09-11
("Обновлено: 11 сентября 2026 г.").

This record supersedes the 2026-09-11 entry that reported the source as
unreachable. The earlier block was an environment-level TLS failure, not an
upstream outage: `rosstat.gov.ru` is certified by the Russian national CA, which
no default trust store carries, and the server does not send its intermediate.
Adding those two public certificates to an otherwise standard verifying SSL
context resolved it without weakening TLS. See README.md for provenance and
fingerprints.

## Source research

| Surface investigated | Verdict | Evidence |
|---|---|---|
| Rosstat SDMX (SDDS, IMF `ECOFIN_DSD(1.0)`) | **Primary, headline only** | `SDDS_CPI 2000_2026.xml` and `SDDS_CPI_PPI_2026.xml` parsed; each carries exactly one CPI series (`PCPI_IX`, `REF_AREA=RU`, `FREQ=M`) at one index reference period. No dimensions for divisions, groups, items or weights exist in the message. |
| Rosstat official workbooks | **Primary** | Eight workbooks discovered from `/statistics/price` and parsed; they carry the full hierarchy, all three published transformations and the official basket. |
| Statistical Data Showcase (`showdata.rosstat.gov.ru`) | Not used | Reachable, but a client-rendered application; `/finder/...` paths all return the same SPA shell and no public API is documented. |
| EMISS / Fedstat (`fedstat.ru`) | Not used | TLS fine, but every request returns HTTP 403 to a non-browser client. |
| HTML scraping | Not needed | Only the two section pages are parsed, and only to discover official file names. |
| Third-party aggregators | **Not used at any point** | No FRED/IMF/OECD request is made by this collector. |

Methodology read: `Opredeleniya_IPC.pdf` (concepts, the four published base
periods, CPI observation since 1992, release on the 6th–10th working day), the
`/statistics/price/methodology` order index, and the CPI manual Rosstat hosts at
`cpi_ru(3).pdf`, which states the fixed-weight higher-level aggregation identity
this collector reconciles against.

## Verification summary

| Gate | Status | Evidence |
|---|---|---|
| Build / import | PASS | `python -m scripts.init_db` and `python main.py` run end to end |
| Type check | PASS | `python -m mypy` — no issues in 22 source files |
| Lint / format | PASS | `python -m ruff check .` — all checks passed; `ruff format --check .` — 22 files already formatted |
| Tests | PASS | `python -m pytest tests -q` — 66 passed, no network required |
| Live source parse | PASS | 2 400 series, 47 424 observations, 110 098 weight rows, 1991-01 → 2026-08 |
| Sampled official values | PASS | 13 of 13 values matched exactly (table below) |
| Bottom-up reconciliation | PASS | 40/40 December-based, 36/36 month-on-month, coverage 1.0000 |
| Weight reconciliation | PASS | 272/272 basket totals, 40/40 parent sums, residual 0.0000 |
| Cross-surface agreement | PASS | 80/80 exact between `ipc_mes` and `ipc_spr` |
| Fresh-database build | PASS | Empty database → 2 400 metadata, 47 424 observations, 110 098 weights, 1 success log |
| Two-run idempotency | PASS | Second run: 0 observations, 0 vintages, 0 weights, 0 metadata writes, 1 success log |
| Controlled failure | PASS | Forced gate breach wrote exactly one `error` row with a 691-character traceback and left both data tables unchanged |
| PostgreSQL DDL | PASS | Real DDL executed twice on PostgreSQL 16; `test_init_db_portability` |
| Databricks execution | SKIP — no approved workspace or credentials | No Databricks workspace is reachable from this environment. DDL uses only the portable subset, the `DOUBLE`/`DOUBLE PRECISION` spelling is selected per dialect, and every write path uses the Databricks `MERGE ... USING (SELECT ... UNION ALL ...)` form. |
| Security review | PASS | See below |
| Diff review | PASS | See below |

### Sampled official values

Every value below was read straight from the downloaded official file by a
script that does not import the collector, then compared with the stored row.

| Series | Month | Stored | Official | Source |
|---|---|---|---|---|
| `CPI_RU_RSTG_HEADLINE_1_MOM` | 2026-08 | 99.92 | 99.92 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_HEADLINE_1_YTD` | 2026-08 | 104.67 | 104.67 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_HEADLINE_1_YOY` | 2026-08 | 106.33 | 106.33 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_AGGREGATE_6_MOM` | 2026-08 | 99.74 | 99.74 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_AGGREGATE_7_YOY` | 2026-08 | 106.51 | 106.51 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_AGGREGATE_9000_MOM` | 2026-08 | 99.46 | 99.46 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_GROUP_10_YOY` | 2026-08 | 106.43 | 106.43 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_GROUP_100_YTD` | 2026-08 | 106.91 | 106.91 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_GROUP_8060-AG_MOM` | 2026-08 | 100.31 | 100.31 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_ITEM_111_MOM` | 2026-08 | 100.51 | 100.51 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_ITEM_7802_YOY` | 2026-08 | 125.17 | 125.17 | `ipc_spr_08-2026.xlsx` |
| `CPI_RU_RSTG_HEADLINE_1_MOM` | 1992-01 | 345.3 | 345.3 | `ipc_mes_08-2026.xlsx` |
| `CPI_RU_SDDS_HEADLINE_ALL_IX2000` | 2026-07 | 981.0 | 981.0 | `SDDS_CPI 2000_2026.xml` |

Weights (same method): headline `1` = 100 exactly, item `111` = 0.638 exactly,
services `9000` = 28.226 exactly, all for 2026-08.

### Bottom-up reconciliation, 2026-09-11 publication

| Check | Pass | Warn | Fail | Worst residual | Gates the run |
|---|---|---|---|---|---|
| `index_dec_based` | 40 | 0 | 0 | +0.0353 index points | yes |
| `index_month_on_month` | 36 | 0 | 0 | −0.0073 | yes |
| `weight_total` | 272 | 0 | 0 | 0.0000 | yes |
| `weight_sum` | 40 | 0 | 0 | 0.0000 | yes |
| `surface_agreement` | 80 | 0 | 0 | 0.0000 | yes |
| `kipc_division_total` | 15 | 0 | 0 | 0.0000 | no |
| `kipc_weight_sum` | 6 810 | 2 | 257 | +4.992 | no |

The KIPC weight-sum failures are defects in Rosstat's own published
classification codes, not in this collector: 2012–2020 close perfectly across
~475 parents per year, while 2023 — whose sheet publishes far fewer intermediate
levels — fails on 49%. Nothing from that layer reaches the standardized tables,
so it is reported, not repaired.

### Idempotency evidence

| | Run 1 (empty database) | Run 2 (unchanged) |
|---|---|---|
| `time_series` rows written | 47 424 new, 0 new vintages | 0 new, 0 new vintages, 0 same-day updates |
| `weights` rows written | 110 098 new, 0 new vintages | 0 new, 0 new vintages |
| `metadata` rows | 2 400 inserted, 0 updated | 0 inserted, 0 updated |
| `logs` rows | 1 `success` | 1 `success` |

Post-run table counts: `metadata` 2 400, `time_series` 47 424, `weights`
110 098. Duplicate `(series_id, reference_date, vintage_date)` triples: 0.
Metadata rows with `observation_count <= 0` or a missing required field: 0.
Non-finite or non-positive stored values: 0. Distinct `vintage_date`: one, the
collection date — no historical backfill was stamped with its reference date.

## Direct template comparison

**PASS — no blocker or minor drift.** Executed 2026-09-14 against
[`guimasuko/collector_template`](https://github.com/guimasuko/collector_template)
tree `8e4613b36c2808a7de234934a81bb26f7a22d367`, including
`GUIDELINES.md` blob `1bf3df07a9b81932d26571def6bf0e531b8c1464`,
`FORECAST_TARGET_GUIDELINES.md` blob
`7ac0663c7825443e1009a18481c0b73b0184b1cd`, layout and fleet skills.

| Area | Classification | Evidence |
|---|---|---|
| Repository/schema, root orchestrator and flat package | MATCH | `collector_rosstat_cpi` identity is consistent; no shared core or cross-collector runtime |
| Standard `metadata`, `time_series`, `logs` | MATCH | Fleet columns and semantics preserved |
| Currency/frequency/unit vocabulary | MATCH | `RUB`, monthly, canonical units validated before writes |
| Vintage and idempotency contract | MATCH | Unchanged rerun no-op; same-day correction and later-day revision covered; backfill uses collection date |
| Official `weights` table | SOURCE-SPECIFIC EXTENSION | Rosstat weights are already official percentage shares; there is no transformed layer requiring `original_weights` |
| Rosstat validation/export modules | SOURCE-SPECIFIC EXTENSION | Required for six distinct official surfaces, hierarchy reconciliation and analyst evidence |
| Rosstat CA bundle | SOURCE-SPECIFIC EXTENSION | Public trust-chain certificates only; hostname and certificate verification remain enabled |
| Large source extractor | SOURCE-SPECIFIC EXTENSION | Six incompatible official layouts are kept in one source-specific module as required by the flat/no-client-framework rule |
| Tests | SOURCE-SPECIFIC EXTENSION | Explicitly justified by parser, hierarchy, reconciliation and persistence complexity |
| Minor drift | MATCH | None found |
| Blocker | MATCH | None found in code or stored-data contract |

The forecast-target rules are satisfied by official weights, hierarchy-aware
reconciliation, full-coverage gates and analyst export. Rosstat-specific logic
was not rewritten to imitate ONS.

## Deviations from the base contract, and why

- **`weights` table.** Approved for a forecast-target collector with weights. It
  holds the official Rosstat basket verbatim, so no `original_weights` table is
  created — there is nothing transformed to preserve separately.
- **No standardized column was added.** `metadata`, `time_series` and `logs`
  match the fleet DDL.
- **`scripts/validate.py` and `scripts/export_validation_xlsx.py`** exist because
  the collector kind requires bottom-up reconstruction and an analyst-facing
  audit export; both mirror the reference forecast-target collector's layout.
- **`scripts/time_series.py` and `scripts/weights.py` gained `_as_date()`.** The
  copied fleet implementation compared a stored `reference_date` to an incoming
  `date` without normalizing what the dialect returns. PostgreSQL and Databricks
  return a `date` and are unaffected; a dialect returning the ISO string missed
  every stored row and rewrote the whole panel. `scripts/metadata.py` already
  carried the same normalizer, so this aligns the three modules.
- **`rosstat_ca_bundle.pem`** is committed. It holds two public government CA
  certificates, no secret, and is the only way to verify the official host's
  certificate at all.
- **`scripts/extract.py` is ~1 200 lines**, above the guideline's ~400-line
  guidance. The source forces it: six official surfaces with unrelated layouts
  (the combined monthly workbook, the since-1991 workbook, two annual basket
  workbooks with layouts that change by year, the KIPC classification, and an
  SDMX 2.1 message) plus discovery and bounded HTTP. Splitting it into a client
  and a parser is what the guideline explicitly discourages, so it stays one
  module organised by surface, with the identifier contract at the top.
- **`tests/` is present because the source-specific parser, the hierarchy
  derivation and the weight mathematics are complex enough to justify it under
  the guideline's own test rule.

## Security review

| Check | Result |
|---|---|
| Hardcoded secrets or credentials | None; `.env` is gitignored, `.env.example` holds placeholders only |
| SQL construction | All values are named `sqlalchemy.text` parameters; table and schema identifiers come only from module constants |
| `eval` / `exec` / pickle / unsafe YAML | None |
| `shell=True` with untrusted content | None; no subprocess is spawned |
| Server-side request forgery | `_assert_allowed()` rejects any URL whose host is not one of the two Rosstat hosts, including links discovered on a section page |
| Redirects | `follow_redirects=False` |
| TLS | Verification and hostname checking always on; the bundle only adds the CA that certifies the official host |
| Bounds | Request timeout, bounded exponential backoff with a delay ceiling, a download size ceiling, and schema validation on every parsed sheet |
| Credential logging | The database URL is rendered with `hide_password=True`; no token or auth header is ever logged |
| Resources | Every engine connection and workbook uses a context manager or is explicitly closed |
| Dependencies | Nine, all fleet-standard; no `requests`, `python-dotenv`, ORM, or migration framework |

No CRITICAL, HIGH, MEDIUM or LOW finding is outstanding.

## Diff review

Added: `main.py`, `scripts/config.py`, `scripts/extract.py`,
`scripts/init_db.py`, `scripts/metadata.py`, `scripts/validate.py`,
`scripts/weights.py`, `scripts/export_validation_xlsx.py`, `requirements.txt`,
`pyproject.toml`, `.env.example`, `rosstat_ca_bundle.pem`, `tests/`.
Modified: `scripts/time_series.py` (the `_as_date` normalizer above),
`README.md`, `COMPLIANCE.md`.
Unchanged: `MASTER_MACRO_COLLECTOR_GUIDELINES.md`, `AGENTS.md`, `CLAUDE.md`,
`.github/`, `.vscode/`, `.gitignore`, `scripts/db.py`,
`scripts/databricks_engine.py`, `scripts/run_logs.py`.

No token, password, `.env`, debug print, breakpoint or generated artifact is
committed; `rosstat_cpi_validation.xlsx` is produced on demand and gitignored.

## Remaining gates

- Databricks end-to-end execution against a real workspace.
- One live monthly release observed through `--watch`, and the first genuine
  upstream revision, to confirm the vintage path on real revised data rather
  than only on the synthetic revision covered by `tests/test_persistence.py`.

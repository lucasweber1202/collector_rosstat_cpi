# collector_rosstat_cpi

Russia national monthly Consumer Price Index collector for the Federal State
Statistics Service (Rosstat), including the official consumer-expenditure basket
and the reconciliation needed to reproduce the published aggregates.

- Source: Federal State Statistics Service (Rosstat)
- Release: Consumer price indices and the structure of consumer expenditures
- Fleet country code: `RUB` · economic group: `consumer_prices`
- Collector kind: `forecast-target` · native and modelling frequency: `monthly`
- Geographic scope: Russian Federation, national
- Schema: `collector_rosstat_cpi` (catalog `macrobond_inhouse` in production)

## Official sources

Every file below is linked from an official Rosstat section page. The monthly
workbook names embed their reference month, so the collector **discovers** the
current name from the section page on each run instead of pinning it.

| Role | Surface | What it provides | Coverage |
|---|---|---|---|
| Primary | `/storage/mediabank/ipc_spr_{MM}-{YYYY}.xlsx` | One sheet per reference month: local code, official name, basket weight, and the index against the previous month, against December of the previous year and against the same month of the previous year, for every published node | 2025-01 → latest |
| Primary | `/storage/mediabank/ipc_mes_{MM}-{YYYY}.xlsx` | Month-on-month index for the four headline aggregates; the only surface carrying the pre-2025 monthly history | 1991-01 → latest |
| Primary | `/storage/mediabank/CPR_tov_RF_2004-{YYYY}.xlsx` | Annual consumer-expenditure structure by representative good/service, keyed by local code | 2004 → latest |
| Primary | `/storage/mediabank/CPR_Gr-Tov-RF_2001-{YYYY}.xlsx` | Annual consumer-expenditure structure by group; only the latest sheet publishes local codes | codes: latest year only |
| Primary | `SDDS_CPI 2000_{YYYY}.xml`, `SDDS_CPI_PPI_{YYYY}.xml` | SDMX 2.1 `StructureSpecificData` against the IMF `ECOFIN_DSD(1.0)`; the only Rosstat surface publishing headline CPI as an **index level** | 2001-01 / 2011-01 → latest−1 |
| Reference | `/storage/mediabank/Vesa-tov-KIPC_2012-{YYYY}.xlsx` | The official KIPC (COICOP) classification with hierarchical codes and annual basket weights | 2012 → latest |
| Documentation | `/storage/mediabank/Opredeleniya_IPC.pdf`, `/statistics/price/methodology`, `/storage/mediabank/cpi_ru(3).pdf` | Concepts, release calendar, and the CPI manual Rosstat publishes | — |

Discovery pages: `https://rosstat.gov.ru/statistics/price` (workbooks) and
`https://eng.rosstat.gov.ru/folder/210404` (SDMX SDDS).

**Fallback.** Every `/storage/mediabank/` object is mirrored on
`eng.rosstat.gov.ru`. A file the primary host cannot serve after its bounded
retries is fetched from the mirror, which produces the identical data model.
Requests never leave those two hosts.

### Why SDMX is not the only primary source

Rosstat does publish CPI in SDMX, but the SDDS message carries **only the
headline all-items index** (indicator `PCPI_IX`) at two index reference periods.
It contains no divisions, groups, items or weights. It is therefore used as a
primary source for the headline index *level* — which no other Rosstat surface
publishes — while the hierarchy, components and basket come from the official
workbooks. EMISS/Fedstat and the Statistical Data Showcase expose the same
indicators, but Fedstat returns HTTP 403 to non-browser clients and the Showcase
is a client-rendered application with no documented public API, so neither is
used. No third-party aggregator (FRED, IMF, OECD) is used at any point.

### TLS: the Russian national CA

`rosstat.gov.ru` presents a certificate issued by `Russian Trusted Sub CA`
(Ministry of Digital Development), which no default trust store carries, and the
server does not send the issuing intermediate. `rosstat_ca_bundle.pem` therefore
ships the two **public** certificates that chain the official host, and
`build_ssl_context()` loads them **into** a normal `ssl.create_default_context()`.

Certificate verification and hostname checking stay on; nothing is disabled. The
added CA is reachable only from a client whose requests are restricted to the
two allowlisted Rosstat hosts.

| Certificate | SHA-256 | Obtained from |
|---|---|---|
| Russian Trusted Root CA | `D26D2D0231B7C39F92CC738512BA54103519E4405D68B5BD703E9788CA8ECF31` | `https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt` (GlobalSign-certified host) |
| Russian Trusted Sub CA (RSA 2024) | `2155785036C900DBB5F1BB2A1569C80C55595BD6BF94867A29BBDDBC7D88A3F2` | `http://nuc-cdp.digital.gov.ru/cdp/subca_ssl_rsa2024.crt`, the Authority Information Access URI of the live `rosstat.gov.ru` leaf; verified to chain to the root above before use |

Set `COLLECTOR_ROSSTAT_CA_BUNDLE` to point elsewhere if your deployment manages
that trust centrally.

## What is collected

2 400 monthly series, 47 424 observations and 110 098 weight rows on the
2026-09-11 publication.

| Classification | Level | Nodes | Measures |
|---|---|---|---|
| `RSTG` (Rosstat CPI grouping) | `HEADLINE` | 1 | `MOM`, `YTD`, `YOY` |
| `RSTG` | `AGGREGATE` | 11 | `MOM`, `YTD`, `YOY` |
| `RSTG` | `GROUP` | 215 | `MOM`, `YTD`, `YOY` |
| `RSTG` | `ITEM` (representative good/service) | 576 | `MOM`, `YTD`, `YOY` |
| `SDDS` (IMF SDDS SDMX) | `HEADLINE` | 1 | `IX2000`, `IX2010` |

- Observations: **1991-01 → 2026-08** (428 distinct months). The four headline
  aggregates run from 1991-01; the full hierarchy from 2025-01, which is when
  Rosstat began the combined index/expenditure publication.
- Weights: **2004-01 → 2026-08**.
- A node's `YOY` series starts one year after its `MOM`/`YTD` series, so a few
  nodes carry no `YOY` series at all; nothing is back-filled.

### Measures

Rosstat publishes no index *level* for the components, so the rawest available
representation of a node is its month-on-month index. All three officially
published transformations are stored rather than recomputed, because each is
published rounded to two decimals and chaining one into another accumulates
error an analyst cannot undo.

| Measure | Meaning |
|---|---|
| `MOM` | index, previous month = 100 |
| `YTD` | index, December of the previous year = 100 |
| `YOY` | index, same month of the previous year = 100 |
| `IX2000` / `IX2010` | index level, 2000=100 / 2010=100 (SDMX only) |

Index reference periods are never mixed: the two SDMX bases are separate series
and the run fails if a message declares a base other than the one its identifier
carries.

## `series_id`

```text
CPI_{GEO}_{CLASSIFICATION}_{LEVEL}_{NODE}_{MEASURE}
```

| Part | Values |
|---|---|
| `GEO` | `RU` — Russian Federation, national |
| `CLASSIFICATION` | `RSTG`, `SDDS` |
| `LEVEL` | `HEADLINE`, `AGGREGATE`, `GROUP`, `ITEM` |
| `NODE` | the native Rosstat code, uppercased, `.` → `-`, the Cyrillic `А`/`Г` of the pharmaceutical ATC codes transliterated to `A`/`G` |
| `MEASURE` | `MOM`, `YTD`, `YOY`, `IX2000`, `IX2010` |

```text
CPI_RU_RSTG_HEADLINE_1_MOM          all goods and services, previous month = 100
CPI_RU_RSTG_AGGREGATE_9000_YOY      services, same month a year earlier = 100
CPI_RU_RSTG_GROUP_10_YTD            meat products, December = 100
CPI_RU_RSTG_ITEM_111_MOM            beef excluding boneless, kg
CPI_RU_RSTG_GROUP_8060-AG_MOM       ATC C10 lipid-lowering agents (code 8060.АГ)
CPI_RU_SDDS_HEADLINE_ALL_IX2000     headline index level, 2000 = 100
```

`parse_series_id()` returns a `SeriesKey(measure_prefix, geo, classification,
level, node, measure)` and `build_series_id()` reverses it; the round trip is
exact and every malformed spelling raises `ValueError`.

Frequency is not encoded in the identifier: every stored series is monthly, and
`metadata.frequency` carries it.

## Weights

`weights` holds the official Rosstat consumer-expenditure structure (СПР)
**exactly as published** — a percentage of the national total, so the headline
node is 100 and no node ever exceeds it. Nothing is normalised, rescaled or
derived, which is why there is no `original_weights` table.

- Rosstat fixes one basket per calendar year (two in 2022, split at 1 April) and
  applies it to every month of that year, so each annual basket is written
  against the months it actually governs.
- 2025-01 onwards uses the weight printed next to the index in the monthly
  workbook; earlier months use the annual publications, keyed by local code.
- A weight is stored only for a node that has a collected series, so a basket
  position Rosstat retired before 2025 is skipped rather than stored against a
  series that does not exist (249 such codes on the current publication).
- Weights hang off the node's **primary** series, the `MOM` one. The same weight
  applies to that node's `YTD` and `YOY` series; substitute the measure suffix to
  move between them.
- `assert_percentage_basket()` refuses to run against a `weights` table holding
  a value outside `[0, 100]`, so a different basket convention can never be
  mixed in silently.

## Hierarchy

Two official classifications are published and both are represented explicitly.

**Rosstat CPI grouping** (`RSTG`) is what the monthly publication uses. Its
aggregation tree, verified against the published weights in every collected
month, is:

```text
1  Все товары и услуги            (all goods and services, weight 100)
├── 2     Все товары              (all goods)
│   ├── 6 Продовольственные       (food)
│   └── 7 Непродовольственные     (non-food)
└── 9000  Услуги                  (services)
```

Below that, Rosstat prints group and item rows but publishes **no machine-readable
parent code**, so no deeper parent-child relation is invented. The published
level (`GROUP` vs `ITEM`) is taken from the workbook and cross-checked against the
representative-goods publication, which matched exactly (551/551) on the current
release. `AGGREGATE` also covers the analytical cuts Rosstat publishes alongside
the tree (core CPI `3`, baskets excluding alcohol `4`/`5`, excluding vegetables
and fruit `70`/`71`/`72`, excluding regulated items `80`); these deliberately
overlap and are never summed.

**KIPC / COICOP** is the classification with explicit hierarchical codes
(`01` → `01.1` → `01.1.1` → … → `01.1.1.1.1.1`). Rosstat prints the
representative goods under identical names and identical weights in both
publications, so each such item carries its official KIPC code in
`metadata.description` (558 of 803 nodes on the current release). The full KIPC
tree, its annual weights and its parent map are exported to the audit workbook.
Rosstat pads a skipped classification level with a zero segment, so `07.1.1.0.0`
is the level-3 node `07.1.1`; the collector folds those placeholders before
deriving a parent.

## Bottom-up validation

Rosstat builds the CPI as a fixed-basket (Lowe/Laspeyres) index. With a December
price-reference period and that year's expenditure structure as fixed weights, a
parent's December-based index is the weighted arithmetic mean of its children's,
which is the identity the CPI manual Rosstat publishes states directly:

```text
I_parent(t | Dec) = Σ_i w_i · I_i(t | Dec) / Σ_i w_i
```

The month-on-month index is the same aggregate expressed against the previous
month, so it is rebuilt with price-updated weights:

```text
φ_i(t) = w_i · I_i(t-1 | Dec) / Σ_j w_j · I_j(t-1 | Dec)
I_parent(t | t-1) = Σ_i φ_i(t) · I_i(t | t-1)
```

Each check reports the aggregate, the official value, the reconstructed value,
the difference, the tolerance and `PASS`/`WARN`/`FAIL`. Results on the
2026-09-11 publication:

| Check | Result | Worst residual |
|---|---|---|
| `index_dec_based` — parent rebuilt from children, December base | 40/40 PASS | +0.0353 index points (node `1`, 2025-11) |
| `index_month_on_month` — parent rebuilt with price-updated weights | 36/36 PASS | −0.0073 (node `2`, 2026-08) |
| `weight_total` — headline basket equals 100 | 272/272 PASS | 0.0000 |
| `weight_sum` — children's weights equal the parent's | 40/40 PASS | 0.0000 |
| `surface_agreement` — `ipc_mes` vs `ipc_spr` on their overlap | 80/80 PASS | 0.0000 |
| `kipc_division_total` — KIPC divisions sum to 100 | 15/15 PASS | 0.0000 |
| `kipc_weight_sum` — KIPC parent equals its children (diagnostic) | 6 810 PASS / 2 WARN / 257 FAIL | +4.992 (`07.1.1`, 2023) |

Tolerance is 0.10 index points for indices and 0.005 for weights. Indices are
published to two decimals and weights to three, so a parent rebuilt from rounded
children cannot match exactly; the measured maximum is well inside the floor.

The first five checks **gate the run**: a breach raises before anything is
written. The KIPC checks are diagnostics — they grade Rosstat's own
classification codes, which in a documented minority of nodes reuse a parent's
code on one of its children. 2012–2020 close perfectly (0 failures across ~475
parents per year); 2021–2022 and 2024–2026 fail on 1–6% of parents; the 2023
sheet publishes far fewer intermediate levels and fails on 49%. Nothing from the
KIPC layer is written to the standardized tables, so these never block ingestion;
every failure is listed in the audit workbook.

`--export-validation[=PATH]` writes `rosstat_cpi_validation.xlsx` with sheets
*Time Series*, *Weights*, *Hierarchy*, *KIPC Basket* and *Validation*.

## Data quality gates

Ingestion is refused outright when the panel is structurally broken: a reference
date that is not a month start, a value that is not a finite positive index, a
catalogued series with no observation, an observation with no upstream metadata,
a weight for a series that does not exist, or an SDMX message whose declared
index reference period no longer matches its identifier. Duplicate identifiers
cannot arise — the code normaliser is injective over the published code set and
a collision is asserted in the tests.

## Vintages and revisions

Rosstat rewrites each workbook in place and publishes no vintage archive, so the
canonical realized-data rule applies:

- first sighting of `(series_id, reference_date)` → insert with
  `vintage_date = collection date`, never the reference date;
- an unchanged value → no write, `collected_at` untouched;
- a changed value on a later day → a new row with today's `vintage_date`;
- a changed value on the same day → only today's row is updated; older vintages
  are never edited;
- values are compared rounded to 10 decimals so serialization noise cannot forge
  a revision.

`metadata.last_publish_date` is the source-stamped "Обновлено" date the
workbook's contents sheet carries (2026-09-11 on the current release), not the
collection day. Rosstat publishes the monthly CPI on the sixth to tenth working
day of the month after the reference month; `--watch` polls for the next month
and treats a timeout as a normal successful outcome.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env            # then set COLLECTOR_DB_URL

python -m scripts.init_db       # create schema, metadata, time_series, weights, logs
python main.py                  # collect (rewinds 5 months when the database is populated)

python main.py --start-date 1991-01-01            # full historical rebuild
python main.py --export-validation                # also write the audit workbook
python main.py --watch                            # poll for the next monthly release
python -m pytest tests -q                          # 66 tests, no network required
```

### Verifying a run

```sql
-- current value of every series
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

```sql
-- headline inflation, and the basket that reproduces it
SELECT t.reference_date, t.value AS yoy_index
FROM collector_rosstat_cpi.time_series t
WHERE t.series_id = 'CPI_RU_RSTG_HEADLINE_1_YOY'
ORDER BY t.reference_date DESC LIMIT 12;

SELECT w.reference_date, m.name, w.weight
FROM collector_rosstat_cpi.weights w
JOIN collector_rosstat_cpi.metadata m USING (series_id)
WHERE w.reference_date = DATE '2026-08-01'
  AND w.series_id IN (
      'CPI_RU_RSTG_AGGREGATE_6_MOM',
      'CPI_RU_RSTG_AGGREGATE_7_MOM',
      'CPI_RU_RSTG_AGGREGATE_9000_MOM')
ORDER BY w.weight DESC;
```

On Databricks select catalog `macrobond_inhouse` first.

## Known limitations

- **Component history starts in 2025-01.** Rosstat only began the combined
  index/expenditure publication then. Before that, only the four headline
  aggregates have a monthly series (back to 1991-01). Earlier component detail
  exists in EMISS, which is unreachable from a non-browser client.
- **Group weight history is short.** `CPR_Gr-Tov-RF` publishes local codes only
  in its latest sheet, so pre-2025 weights are item-level only (from
  `CPR_tov_RF`, 2004 onwards). Matching the earlier group sheets by name would
  be a guess, so it is not done.
- **The deep Rosstat tree is not published.** Only the four-node top tree is
  asserted; group-to-item parentage is not published in machine-readable form.
  The KIPC codes carried in `metadata.description` give the COICOP tree for the
  representative items.
- **KIPC weight sums do not close everywhere** (see above) — a defect in
  Rosstat's published codes, reported rather than repaired.
- **No index level below the headline.** Rosstat publishes component indices only
  as percentage changes.
- **SDMX lags by one month** relative to the workbooks.
- **No vintage archive exists upstream**, so revision history begins the first
  time this collector observes a value.
- **Subnational data is not collected.** `ipc_RF_fo_sub_*.xlsx` carries federal
  districts and subjects; the approved scope is national.

## Governance

Read `MASTER_MACRO_COLLECTOR_GUIDELINES.md` and `.github/copilot-instructions.md`
before modifying the collector. `COMPLIANCE.md` records the verification evidence
for the current release.

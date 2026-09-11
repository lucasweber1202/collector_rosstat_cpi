# Master Guidelines for Macroeconomic Data Collectors

> Portable operating instructions for Claude Code, Codex, GitHub Copilot, or another coding agent working on the macroeconomic collector fleet.

## 0. Mission and operating principle

Build and maintain a fleet of small, deliberately boring, self-contained repositories. Each repository collects one source/dataset, standardizes it into a common database contract, and records every run.

**Standardization is the feature.** A reader familiar with one collector must be able to understand another without learning a framework, inheritance hierarchy, plugin system, or shared internal package.

Each collector normally does only three things:

1. Extract data from one authoritative external source.
2. Standardize observations and metadata into the fleet schema.
3. Persist an auditable run log.

When a rule is silent, prefer the smallest solution consistent with the pilot. Do not add infrastructure because it feels cleaner or may be useful later.

---

## 1. Authority and conflict resolution

Before changing or creating a collector, resolve instructions in this order:

1. The user's current explicit request.
2. The current checked-out pilot repository and its executable code.
3. The current root `GUIDELINES.md` and `FORECAST_TARGET_GUIDELINES.md`, when applicable.
4. `.github/copilot-instructions.md`.
5. Task-specific skills and prompts such as `build-collector`, `audit-collector`, and `series-selection`.
6. Generic development workflows such as planning, TDD, review, security, and verification.

If two documents disagree, do not silently choose an older embedded snippet. Inspect the live pilot and state the discrepancy. The live pilot plus the current root guidelines define the fleet contract.

The following conflict resolutions are mandatory:

- **Schema:** the current pilot DDL is authoritative. Never add, remove, or reinterpret standardized columns based on an older prompt.
- **Pipeline order:** write/upsert `time_series` first, then derive and upsert `metadata` from the post-write database state. This is required so `first_observation`, `last_observation`, and `observation_count` describe the full stored history rather than only the current extraction window.
- **Tests:** do not add a token or trivial `tests/` directory merely to satisfy a generic TDD checklist. Add committed tests only when source-specific logic is complex enough to justify them or the user explicitly asks. For a bug or complex numerical transformation, a failing regression test is required.
- **Reuse:** `research-first` means inspect and copy/extend the pilot pattern. It does not authorize a shared `core/`, `utils/`, or cross-collector package.
- **Secrets:** collector configuration parses `.env` manually. Generic advice to add `python-dotenv` does not apply.
- **Extra tables:** the ordinary collector uses only the standardized tables. Extra tables are allowed only for a documented, source-forced exception, especially a forecast-target collector with weights. Obtain user approval and document the deviation.
- **Tools:** if a named planning/review tool is unavailable, reproduce its outcome in plain text instead of skipping the workflow.

---

## 2. Mandatory intake before generating files

Do not generate a new repository until all inputs below are known:

| Input | Required content |
|---|---|
| `SOURCE` | Short agency identifier, e.g. `BANXICO`, `IBGE`, `FRED`, `ECB` |
| `DATASET` | Short dataset identifier, e.g. `ENCUESTA`, `SIDRA1737`, `CPI` |
| `SOURCE_NAME` | Human-readable agency name |
| `RELEASE_NAME` | Human-readable dataset/release name |
| `COUNTRY` | Fleet-approved 3-letter currency/country code for `metadata.country` |
| `DOCS_URL` | Official documentation URL |
| `TARGET_SERIES` | Curated series list and source-native IDs |
| `INTENDED_FREQUENCY` | Intended modelling cadence; mandatory when series must be curated |
| `AUTH` | None, API key with environment-variable name, OAuth, or other mechanism |
| `COLLECTOR_KIND` | Standard realized data, forecast/projection, or forecast target/Y-variable |

If anything material is missing, ask before creating files. Never guess source endpoints, native IDs, units, publication frequency, scope, or authentication.

---

## 3. Mandatory workflow for any non-trivial task

### 3.1 Plan before implementation

Before writing code or modifying files:

1. Restate the goal, constraints, acceptance criteria, and expected outputs.
2. Inspect the current repository, pilot, relevant guidelines, and recent diff.
3. Decompose the work into small, atomic tasks with named files, commands, checks, and expected outcomes.
4. Present the implementation plan and wait for approval when the task is non-trivial or when the instructions require approval.
5. If a major design issue appears during execution, pause and present an updated plan.

Recommended plan shape:

```markdown
# [Feature] Implementation Plan

Goal: ...
Architecture: ...
Tech stack: ...
Related specification: ...

## Phase 1 — MVP
### Task 1 — [Component]
- Create: ...
- Modify: ...
- Test/verify: ...
- Steps and expected result: ...
```

Size guidance:

- Small: 1–3 tasks, usually one phase.
- Medium: 4–10 tasks, usually MVP + core.
- Large: 11–20 tasks, split into 3–4 independently testable phases.
- More than 20 tasks: decompose into separate projects/plans.

Reconsider the plan when one task is likely to exceed ten minutes, more than ten files must change, task dependencies cycle, an API has not been verified, or the plan duplicates an existing solution.

### 3.2 Research first

Before custom code or a dependency:

1. Search the current repository and the pilot for the same or a similar implementation.
2. Inspect installed and declared dependencies.
3. Read current official API/library documentation.
4. Use a maintained external library only when it is necessary and proportionate.
5. Write custom code only when the existing patterns and dependencies cannot solve the requirement.

Within this fleet, “reuse” normally means copying the canonical pilot implementation into the self-contained collector, not importing a cross-repository shared package.

### 3.3 Fetch current API documentation

Before writing `extract.py`, obtain current official documentation. Prefer the project-provided `get-api-docs` workflow and `chub`:

```bash
chub search "<source or library>" --json
chub get <author/doc-id> --lang py
```

If `chub` has no relevant document, use the official API documentation URL supplied by the user. Do not infer endpoints or request/response shapes from model memory. Record concise, project-specific quirks with `chub annotate` when appropriate. Ask the user before sending `chub feedback`.

---

## 4. Canonical repository architecture

Repository and schema name:

```text
collector_<source>_<dataset>
```

Use lowercase snake_case. The repository name and `SCHEMA_NAME` must be identical.

The current pilot is the exact structural reference. The typical current layout is:

```text
collector_<source>_<dataset>/
├── .github/
├── .vscode/
├── .env.example
├── .gitignore
├── README.md
├── main.py
├── pyproject.toml
├── requirements.txt
└── scripts/
    ├── __init__.py
    ├── config.py
    ├── databricks_engine.py
    ├── db.py
    ├── extract.py
    ├── init_db.py
    ├── metadata.py
    ├── run_logs.py
    └── time_series.py
```

Rules:

- `main.py` is at the repository root.
- `scripts/` is flat: no subpackages, base classes, plugins, or dependency-injection framework.
- Copy fleet-wide files byte-for-byte from the current pilot when instructed.
- Each repository owns its `.env`, schema, scripts, source quirks, and deployment setup.
- Do not introduce `core/`, `lib/`, `utils/`, `common/`, or `helpers/`.
- Do not add a `Dockerfile`, `Makefile`, CI workflow, ADR, architecture diagram, CHANGELOG, cache layer, or migration framework unless explicitly requested.
- Do not split `extract.py` into client/parser modules while it remains reasonably readable and under approximately 400 lines. If the source truly forces additional modules, document why.
- Do not keep unused pilot stubs or dependencies.

The following are copied verbatim from the current pilot unless a current guideline explicitly says otherwise:

- `.gitignore`
- `.github/`
- `.vscode/`
- `scripts/databricks_engine.py`
- Standard DDL and generic upsert/run-log implementations

Template files permit only named substitutions: schema, source URL/name, required auth variables, start date, documented HTTP tuning, and source-required parser dependencies.

---

## 5. Standardized database contract

Production catalog: `macrobond_inhouse`.

Ordinary collectors write three mandatory tables: `metadata`, `time_series`, and `logs`. Use the current pilot's DDL byte-for-byte. The contract below reflects the consolidated current guideline and must be reconciled against the pilot before implementation.

### 5.1 `metadata`

One row per series:

```sql
CREATE TABLE IF NOT EXISTS <schema>.metadata (
    series_id            VARCHAR(200)  NOT NULL,
    name                 VARCHAR(500)  NOT NULL,
    description          VARCHAR(2000),
    country              VARCHAR(3)    NOT NULL,
    frequency            VARCHAR(20),
    unit                 VARCHAR(50),
    first_observation    DATE,
    last_observation     DATE,
    observation_count    INTEGER       NOT NULL,
    eco_group            VARCHAR(250),
    source_url           VARCHAR(1000) NOT NULL,
    last_publish_date    DATE,
    collected_at         TIMESTAMP     NOT NULL,
    CONSTRAINT pk_metadata PRIMARY KEY (series_id)
);
```

Mandatory semantics:

- `series_id`: structured, unique, parseable identifier.
- `name` and `description`: faithful English descriptions of the source series.
- `country`: approved three-letter fleet vocabulary. In the present fleet this is commonly the ISO 4217 currency code (e.g. `BRL`, `USD`, `MXN`); verify the live guideline before adding a new code.
- `frequency`: the source's native publication frequency, never the desired modelling frequency.
- `unit`: normalized fleet unit.
- `first_observation`, `last_observation`, `observation_count`: calculated from the post-write `time_series` table with `COUNT(DISTINCT reference_date)`.
- `eco_group`: approved fleet category; never invent a one-off spelling silently.
- `source_url`: the most traceable official series/table page, or the official source root when no series-specific page exists.
- `last_publish_date`: the source-stamped release date when trustworthy; otherwise the date of `MAX(time_series.collected_at)` for the series.
- `collected_at`: changes only when a metadata field genuinely changes. Identical metadata is a no-op.

Every field required by the DDL, including `source_url`, must appear in insert/update/comparison tuples as appropriate. Do not copy an older snippet that accidentally omits a required field.

Controlled vocabulary currently includes:

```text
frequency:
daily | weekly | biweekly | monthly | quarterly | semiannual |
annual | decennial | quinquennial | irregular

unit:
index | percent | ratio | persons | currency | count | tons |
hectares | cubic_meters | megawatt_hours | other

eco_group examples:
gdp | activity | industrial_production | production | retail_sales |
vehicles | tourism | mining | savings | leading_indicators |
consumer_prices | producer_prices | inflation | inflation_expectations |
labor | employment | unemployment | wages | trade | balance_of_payments |
exchange_rates | external_accounts | central_bank | monetary_aggregates |
interest_rates | financial_markets | financial_intermediaries |
government_securities | currency_in_circulation | payment_systems |
petroleum_fund | public_finance | surveys | consumer_confidence |
business_confidence | other
```

Each collector declares local `frozenset` vocabularies for the values it actually emits, and metadata creation validates against them. A genuinely new canonical value must first be added to the fleet guideline, then to the collector.

### 5.2 `time_series`

Append-only, vintage-tracked observations:

```sql
CREATE TABLE IF NOT EXISTS <schema>.time_series (
    series_id       VARCHAR(200) NOT NULL,
    reference_date  DATE         NOT NULL,
    vintage_date    DATE         NOT NULL,
    value           DOUBLE       NOT NULL,
    collected_at    TIMESTAMP    NOT NULL,
    CONSTRAINT pk_time_series
        PRIMARY KEY (series_id, reference_date, vintage_date)
);
```

Databricks treats key constraints as informational, so application logic must enforce uniqueness.

Definitions:

- `reference_date`: period to which the observation refers.
- `vintage_date`: publication/availability date for this stored version, subject to the rules below.
- `collected_at`: exact run timestamp and tie-breaker for defensive latest-vintage queries.

Canonical realized-data vintage behavior:

1. First sighting of `(series_id, reference_date)`: insert with `vintage_date = today`, not the historical reference date.
2. Later identical value: no-op; do not touch `collected_at`.
3. Changed value on a later date: insert a new row with `vintage_date = today`.
4. Changed value again on the same date: update only the existing `vintage_date = today` row. Never update an older vintage.
5. Compare floats rounded to 10 decimal places to avoid false revisions caused by serialization noise.
6. Drop `None`, NaN, and infinite values before insert.

Canonical latest-value query:

```sql
SELECT series_id, reference_date, value, vintage_date, collected_at
FROM (
    SELECT series_id, reference_date, value, vintage_date, collected_at,
           ROW_NUMBER() OVER (
               PARTITION BY series_id, reference_date
               ORDER BY vintage_date DESC, collected_at DESC
           ) AS rn
    FROM <schema>.time_series
) ranked
WHERE rn = 1;
```

For an end-of-day snapshot, add `WHERE vintage_date <= :as_of` inside the subquery. Intraday history, explicit retractions, and sub-day as-of semantics are outside this canonical table; such a source requires an approved, separate table designed for those semantics.

### 5.3 `logs`

One row per execution, including failures:

```sql
CREATE TABLE IF NOT EXISTS <schema>.logs (
    id           BIGINT GENERATED ALWAYS AS IDENTITY,
    started_at   TIMESTAMP      NOT NULL,
    finished_at  TIMESTAMP      NOT NULL,
    status       VARCHAR(20)    NOT NULL,
    log_text     VARCHAR(65535) NOT NULL,
    traceback    VARCHAR(65535),
    CONSTRAINT pk_logs PRIMARY KEY (id)
);
```

- `status` is `success` or `error`.
- Write the log in `main.py`'s `finally` block.
- Client-side truncate `log_text` and `traceback` with a visible `[..., truncated ...]` suffix.
- Log persistence is best-effort and must not conceal the original pipeline error.

### 5.4 Portability

DDL must run on both PostgreSQL and Databricks SQL. Use their common subset: `GENERATED ALWAYS AS IDENTITY`, `DOUBLE`, bounded `VARCHAR`, `DATE`, and `TIMESTAMP`. Avoid PostgreSQL-only `SERIAL`, `JSONB`, and dialect-specific conveniences. All queries use `sqlalchemy.text(...)` and named parameters.

---

## 6. Series selection and identification

### 6.1 Frequency gate

Only include a series whose native frequency matches the collector's intended use.

- For monthly modelling, monthly, biweekly, weekly, or daily inputs may be eligible; exclude quarterly and annual series.
- If a monthly proxy and quarterly aggregate represent the same concept, prefer the monthly proxy.
- If intended frequency is not specified, ask before curating.

### 6.2 Prefer the rawest representation

Rank representations:

1. Raw level or index.
2. Seasonally adjusted level.
3. MoM/QoQ change.
4. YoY change.
5. Cumulative/YTD.

Store an official level rather than a derived growth rate whenever possible. Downstream consumers can transform a level but cannot reliably reconstruct it from a truncated transformation.

### 6.3 Geographic scope

- Prefer national series.
- Include state, city, metro, or other subnational series only when explicitly requested or analytically justified.
- For international comparisons, prefer internationally standardized definitions.
- `country` follows the actual scope of the series, not merely the agency headquarters.

### 6.4 Structured IDs

Every `series_id` must be:

- uppercase;
- composed of underscore-separated parts ordered coarse to fine;
- unique within the collector;
- round-trippable through `parse_series_id()`;
- human-interpretable enough for metadata to be derived systematically.

Examples:

```text
HEADLINE_MEDIA_3
1737_VAR63_BR
CPI_LEVEL
```

Do not expose an opaque native ID as the whole `series_id`. Keep native IDs in an extraction mapping. Do not maintain a hand-written per-series metadata dictionary as the default. `metadata.py` should derive `name`, `description`, and `unit` from parsed components and verified upstream metadata.

Before including each series, confirm:

- frequency is eligible;
- the selected form is the rawest useful representation;
- scope is appropriate;
- the structured ID is unique and decodable;
- metadata generation produces sensible fields;
- at least one observation was checked against the official source;
- the series is live and has sufficient non-null history.

Reject duplicates, stale/discontinued series, one-point snapshots, unnecessarily transformed series, and unjustified subnational series.

Recency and minimum-history thresholds are collector-specific configuration constants. Evaluate recency at the end of the source period and only over non-null observations. Apply the filter at series level before writing either standardized table.

---

## 7. Module contracts

### 7.1 `scripts/config.py`

- Manually load `.env` from the repository root; do not add `python-dotenv`.
- Expose schema/catalog/table constants, `PROD`, local database URL, default start date, rewind window, logging level, HTTP timeout/delay/retry/backoff/user-agent settings, and Databricks/Key Vault settings.
- Add only genuinely required source-specific settings.
- Default rewind is five months unless the source has a documented longer revision window.
- Credentials are read once here, not ad hoc throughout the code.

### 7.2 `scripts/db.py`

- Expose `build_engine() -> Engine`.
- `PROD=True`: lazily use the fleet Databricks engine with catalog and schema.
- `PROD=False`: `create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)`.
- Redact credentials from logged URLs.
- No DDL in this module.

### 7.3 `scripts/databricks_engine.py`

Copy the current pilot file byte-for-byte. It resolves the token in this order:

1. Databricks notebook/job context.
2. `DATABRICKS_TOKEN`.
3. Azure Key Vault through `DefaultAzureCredential`.

Do not log tokens or authorization headers.

### 7.4 `scripts/init_db.py`

- Own all `CREATE SCHEMA/TABLE IF NOT EXISTS` statements.
- Be runnable with `python -m scripts.init_db`.
- Ordinary collector DDL is copied byte-for-byte from the pilot.
- Do not add a standardized column without an explicit fleet-wide decision.

### 7.5 `scripts/extract.py`

This is the principal source-specific module. Public contract:

```python
def parse_series_id(series_id: str) -> tuple: ...

def collect_raw_data(
    start_date: date | None = None,
) -> dict[date, dict[str, float | None]]: ...
```

Requirements:

- Define verified source constants, official URLs, parsing layouts, and code maps at the top.
- Use one context-managed `httpx.Client` per collection call.
- Set timeouts, user-agent, `trust_env=True`, and normally `follow_redirects=False`.
- Retry 429, 5xx, and transport errors with bounded exponential backoff.
- Keep documented source-specific rate-limit quirks local to this module.
- A bad date/file/schema instance is a soft failure: warn and skip it.
- Authentication failure or total network failure after retries is a hard failure: propagate.
- Log progress every roughly ten items or ten percent of work.
- Clear any permitted upstream-metadata cache on entry.
- Return exactly `{reference_date: {series_id: value | None}}`.

If data and metadata use separate endpoints, perform two batched passes inside the same client: metadata first, observations second.

### 7.6 `scripts/time_series.py`

- Fetch the latest stored vintage per `(series_id, reference_date)`.
- Compare incoming values after ten-decimal normalization.
- Separate new observations, later vintages, and same-day updates.
- Insert with multi-row `VALUES` batches, normally 500 rows per statement; do not rely on a per-row Databricks `executemany` path.
- Emit entry and per-batch INFO progress logs.
- Expose `get_max_reference_date(engine)`.
- Expose `get_series_aggregates(engine)` using `MIN(reference_date)`, `MAX(reference_date)`, `COUNT(DISTINCT reference_date)`, and `MAX(collected_at)` grouped by series.

### 7.7 `scripts/metadata.py`

- `_series_descriptive_row(series_id)` is the primary source-specific customization point.
- Use `parse_series_id()` and verified upstream fields to produce the complete standardized row.
- Upsert only series touched by the run and actually present in the database.
- Obtain history aggregates from `time_series` after observations have been written.
- Compare all semantically mutable fields except `collected_at`.
- Identical rows are no-ops; insert new rows and update only changed rows.
- Use batched multi-row INSERT and Databricks-compatible `MERGE ... USING (SELECT ... UNION ALL ...)`, not a loop of individual network round trips.

An `UPSTREAM_METADATA` module-level cache in `extract.py` is permitted only when the source exposes required descriptive fields separately. Clear it at each collection start and normalize values before `metadata.py` consumes them. Missing upstream metadata must use an accurate generic fallback or fail validation; never silently invent scope or units.

Curated human-readable name overrides are an accepted exception when official titles are unusable, but should be keyed by native ID and applied after verified source metadata is considered. They must not contradict source scope or units.

### 7.8 `scripts/run_logs.py`

- Expose a best-effort `insert_run_log(...)`.
- Truncate long text explicitly.
- Never replace or hide the primary exception if logging fails.

### 7.9 `main.py`

Keep business logic out of the orchestrator. Required order:

1. Parse `--start-date`, `--log-level`, and only necessary source flags.
2. Configure stdout plus an in-memory log buffer.
3. Pin the root logger to `ERROR`; elevate only `main` and `scripts` to the requested level so third-party chatter is excluded.
4. Run environment preflight before database/HTTP work.
5. `build_engine()` and `init_db(engine)`.
6. Resolve start date: explicit override, otherwise latest stored reference date minus rewind, otherwise default start date.
7. `collect_raw_data(start_date)`.
8. Upsert `time_series`.
9. Upsert `metadata` using post-write database aggregates.
10. In `finally`, write one `logs` row on success or failure.

The preflight must report all missing required variables at once. For authenticated sources, `.env.example` documents the required key, registration URL, and expected failure mode.

---

## 8. Dependencies and style

### 8.1 Dependencies

Keep the list minimal, but preserve current fleet-wide corporate deployment dependencies from the pilot. Typical common set:

```text
httpx>=0.27
sqlalchemy>=2.0
pandas>=2.0
azure-identity>=1.12
azure-keyvault-secrets>=4.4
databricks-sqlalchemy>=0.2.8
psycopg2-binary>=2.9
pyspark==4.1.1
```

Add only the parser the source actually requires, for example:

```text
beautifulsoup4>=4.12  # HTML only
openpyxl>=3.1         # Excel only
lxml>=5.0             # XML only
```

Do not add `requests`, `python-dotenv`, ORM frameworks, Pydantic/attrs merely for dict validation, Alembic, a logging framework, or `pytest` when the repository contains no justified tests. Mirror dependencies between `requirements.txt` and `pyproject.toml`.

### 8.2 Python style

- Python 3.11 or newer.
- `from __future__ import annotations` in every Python module.
- Type hints on every function signature using built-in generics and PEP 604 unions.
- Module docstring in every module; short behavioral function docstrings.
- Imports grouped stdlib, third-party, local.
- `logging.getLogger(__name__)`; no `print` outside a script's `__main__` block.
- Direct parameterized SQL only; no declarative ORM models.
- Comments explain why, not obvious mechanics.
- No silent broad exception handling. Warn and skip a defined soft failure, or re-raise.
- No unnecessary abstraction, speculative extensibility, or hidden mutation.

---

## 9. Idempotency, reruns, and operational behavior

Idempotency is a release criterion, not an optimization.

- `init_db()` is safe on every run.
- A normal rerun rewinds enough periods to detect late revisions.
- Identical metadata produces no insert or update.
- Identical observations produce no write.
- A changed realized value creates a new vintage, except for an allowed same-day update of today's row.
- Two consecutive runs against the same unchanged source/database must create zero metadata writes and zero observation/vintage writes on the second run.
- The second run still creates one successful `logs` row.

Do not calculate metadata coverage from the current in-memory slice. Do not disk-cache routine source responses merely to accelerate reruns.

---

## 10. Special case: forecast/projection collectors

Forecast collectors retain `metadata`, `time_series`, and `logs`; they normally do not need a separate forecast table.

Use structured IDs of the form:

```text
{SOURCE}_{FAMILY}_{COMPONENT}_{TRANSFORM}_H{n}
```

Rules:

- Horizon is encoded in trailing `H{n}` and parsed by one canonical builder/parser pair.
- For one publication, all horizons share the same `reference_date`: the nearest period still being projected (`H1`).
- Target period equals anchor plus `n - 1` native periods. For meeting paths, count meetings rather than months.
- `vintage_date` is the source's trustworthy publication date, not collection day. This is the sanctioned forecast-archive exception to the realized-data vintage rule.
- Keep historical vintages. Scale backfills with publication-date windows and bulk paths rather than discarding sticky vintages.
- Store projected cells only, never realized observations mixed into a forecast workbook.
- Detect the realized/forecast boundary as a sheet-wide consensus and enforce a publication-relative sanity floor; do not trust a single cell style blindly.
- Multiple scenarios/files on the same posting date may legitimately create nearby anchors; do not deduplicate them solely by posting date.
- Inventory broad archive feeds before declaring a gap; older and newer product families may need to be stitched together.
- When historical forecast publications are immutable, a committed typed Parquet history snapshot plus descriptive metadata CSV may be used for self-healing. Load it only when the database is empty or behind the live edge.
- `metadata.last_publish_date` is the latest source publication/vintage date.

The latest-vintage query must answer what the source forecast as of a given end-of-day date.

---

## 11. Special case: forecast-target/Y-variable collectors

These collectors produce the official indicator against which a model is evaluated. In addition to the base rules, prioritize independent reconstruction and auditability.

### 11.1 Outputs

- Store official index levels or quantities; use growth rates only when levels do not exist.
- When aggregation uses weights, store the weights required to reproduce published aggregates.
- If official weights are transformed, store the official untouched weights separately.
- Preserve parent-to-children aggregation maps and every transformation needed for a human analyst to reproduce the result.

### 11.2 Approved extra tables

Only for a collector explicitly classified as a forecast target and only when weights exist:

```sql
CREATE TABLE collector_<source>_<dataset>.weights (
    series_id       VARCHAR(200) NOT NULL,
    reference_date  DATE         NOT NULL,
    vintage_date    DATE         NOT NULL,
    weight           DOUBLE       NOT NULL,
    collected_at    TIMESTAMP    NOT NULL,
    CONSTRAINT pk_weights
        PRIMARY KEY (series_id, reference_date, vintage_date)
);
```

`weights` holds the weights actually used for reconstruction. Preserve vintages and make reruns idempotent. A top-level series that is not a component of another aggregate receives weight `1.0` for each applicable period.

When `weights` contains derived/transformed weights, also store the official weights exactly as published:

```sql
CREATE TABLE collector_<source>_<dataset>.original_weights (
    series_id         VARCHAR(200) NOT NULL,
    weight            DOUBLE       NOT NULL,
    weight_base_year  INTEGER      NOT NULL,
    collected_at      TIMESTAMP    NOT NULL,
    CONSTRAINT pk_original_weights PRIMARY KEY (series_id)
);
```

If multiple official regimes would collide under this key, do not improvise a silent schema change. Reconcile the live reference implementation and obtain approval for a regime-safe key/table design.

### 11.3 Weight validation

Verify:

- children sum to the documented normalization constant;
- weights reproduce official aggregates within justified tolerance;
- structural breaks coincide with known rebasing/methodology dates;
- official and derived systems remain distinguishable;
- transformations are documented mathematically and reproducible.

Derived weights are exceptional. Preserve official weights and prove that the derived system reproduces the intended metric. Never overwrite the official basket.

For a modified-Laspeyres variation weight, an accepted pattern is:

```text
phi_i(t) = w_i(t) * I_i(t-1) /
           sum_{j in children(parent)} w_j(t) * I_j(t-1)
```

### 11.4 Audit-friendly validation export

During development, generate an Excel workbook whose sheets correspond directly to stored datasets:

1. Time Series — official observations, dates as rows and series as columns.
2. Weights — weights used for reconstruction.
3. Original Weights — only when the operational weights are transformed.

The workbook is a validation aid, not a substitute for database output. An analyst must be able to reproduce every published aggregate with the stored observations, hierarchy, and weights.

### 11.5 Release monitoring

After historical population, a forecast-target collector can operate as a low-latency release ingestor:

- Empty database: run full historical build without waiting.
- Populated database: compute the next expected period from the latest observation and native frequency.
- If the source already has it, ingest immediately; otherwise poll.
- Poll at a configurable interval, with configurable maximum wait and a non-blocking disable flag.
- Timeout with no release is a normal successful outcome and must be logged.
- On detection, run the complete extraction, validation, transformation, and database pipeline.
- Require no source-code edit for each new release.

Expected ingestion latency near a scheduled release is approximately one to two minutes, not real-time streaming.

---

## 12. Systematic debugging

**No fix without root-cause investigation.**

For any bug, failed test, performance problem, integration issue, or unexpected value:

### Phase 1 — Root cause

1. Read the complete error, traceback, warnings, paths, and codes.
2. Reproduce with exact steps. If intermittent, gather evidence rather than guessing.
3. Inspect recent diffs, dependency/config/environment changes.
4. At each component boundary, inspect inputs, outputs, configuration propagation, and state without logging secrets.
5. Trace the bad value backward to its origin.

### Phase 2 — Pattern comparison

1. Find a working collector/example.
2. Read the reference implementation completely.
3. Enumerate every difference between working and failing cases.
4. Identify implicit dependencies and assumptions.

### Phase 3 — Hypothesis

1. State one precise hypothesis and the evidence supporting it.
2. Test it with the smallest possible change, one variable at a time.
3. If disproved, discard it and form a new hypothesis; do not stack speculative fixes.

### Phase 4 — Fix

1. Create the smallest failing regression test or reproducible check.
2. Implement one root-cause fix without unrelated refactoring.
3. Verify the reproduction and full relevant suite.
4. If three fixes fail, stop and discuss whether the architecture is wrong before attempting a fourth.

If the cause is external or timing-dependent, document the investigation and add proportionate timeout, retry, diagnostics, or monitoring.

---

## 13. Testing and quantitative correctness

Use RED → GREEN → REFACTOR for new behavior, bug fixes, and complex transformations when committed tests are justified.

1. Write one minimal behavior test.
2. Run it and confirm it fails for the expected missing behavior, not a test error.
3. Write only enough code to pass.
4. Run the focused and relevant existing tests.
5. Refactor only while green.

Tests should use real code; mock only unavoidable external boundaries. Cover errors and edge cases. Do not add untested production behavior.

For numerical/econometric work:

- Define a known data-generating process and ground-truth parameters.
- Generate reproducible synthetic data with a fixed seed.
- Assert recovered values, not merely non-null output or shape.
- Use tight absolute tolerances for deterministic math, justified approximate tolerances for estimates, and statistical bounds for stochastic algorithms.
- Never demand exact binary float equality when approximation is appropriate.

For simple collector scaffolding where the fleet explicitly excludes a `tests/` directory, use focused reproducible verification scripts/commands without committing a trivial test suite. A source-specific parser, hierarchy, boundary detector, or weight transformation is generally complex enough to warrant real tests.

---

## 14. Security review

Apply a focused security review whenever handling credentials, URLs, HTTP, SQL, files, user input, or production deployment.

Minimum collector checklist:

- No hardcoded secrets or credentials in code, examples, logs, or committed `.env`.
- `.env` is gitignored; `.env.example` contains names/placeholders only.
- SQL values use named parameters. Dynamic table/schema identifiers come only from trusted constants.
- Never use `eval`, `exec`, unsafe YAML loading, or untrusted pickle.
- Never use `shell=True` with untrusted content.
- Official source domains are fixed/allowlisted; user-controlled URLs do not become arbitrary server-side requests.
- Redirect behavior is disabled or each redirect is validated.
- Timeouts, bounded retries, response/file size expectations, and schema validation exist.
- TLS verification remains enabled.
- Auth headers/tokens, signed URLs, database credentials, and raw environment dumps are never logged.
- Database and file resources use context managers/transactions.
- Dependencies are minimal and scanned when tooling exists.
- Production debug output and client-facing tracebacks are disabled.

Classify findings as CRITICAL, HIGH, MEDIUM, or LOW. Any secret exposure, injection, unauthorized access, unsafe deserialization, or material data-loss risk blocks merge.

---

## 15. Audit an existing collector — report only

An audit verifies metadata correctness against the exact official source used by the collector. It is not permission to fix code.

### Phase 1 — Understand the claim

Read the repository instructions, `extract.py`, `parse_series_id()`, metadata construction, README, and project metadata. Write a 3–5-line hypothesis describing what the collector claims to collect.

### Phase 2 — Pull stored metadata

```sql
SELECT series_id, name, description, country, frequency, unit,
       first_observation, last_observation, observation_count
FROM <schema>.metadata
ORDER BY series_id;
```

Prepare a verification table containing stored fields, source ground truth, and match result.

### Phase 3 — Verify against the source

For every series, or a documented representative sample when there are hundreds:

1. Decode `series_id`.
2. Open the same official URL/API/file the collector uses.
3. Verify name/scope, unit, native frequency, country/currency, first/last dates, and plausibility.
4. Compare 2–3 recent stored values with the official published precision.
5. For Excel/PDF/HTML, inspect the exact artifact/parser input.

Never trust a catalog label without verification. Typical serious errors include national vs urban, headline vs core, raw vs seasonally adjusted, percent vs index points, and wrong native table ID.

### Phase 4 — Vintage behavior

For at least one revision-prone series, verify:

- every `(series_id, reference_date)` has a baseline;
- revisions add later vintages;
- only today's same-day row can be updated;
- no duplicate `(series_id, reference_date, vintage_date)` exists;
- forecast collectors use trustworthy source publication dates under their special rule.

### Phase 5 — Idempotency

Run twice against the same database. Second run must create:

- zero metadata inserts/updates;
- zero time-series inserts/new vintages;
- one successful log row.

### Phase 6 — Report

Report:

1. Summary: series audited, issue count, severity count.
2. Findings: series/structural location, stored claim, official truth, severity, suggested file/location.
3. Verified clean series.

Severity:

- **Blocker:** wrong values beyond rounding, wrong source/native ID, wrong country, wrong frequency, or broken vintage history.
- **Major:** wrong scope or unit.
- **Minor:** wording/capitalization/punctuation that does not alter meaning, or a slightly stale latest observation between runs.

Do not silently fix audit findings. Wait for separate authorization.

---

## 16. Code review

Review after a major feature, implementation plan, complex bug fix, and before merge. Report only issues supported with at least approximately 80% confidence.

Review for:

- Acceptance criteria and edge cases.
- Fidelity to official source and structured-ID contract.
- Idempotency and vintage correctness.
- Silent failures and error handling.
- Parameterized SQL and secret handling.
- Batched database performance and bounded memory.
- Unnecessary abstractions/dependencies/files.
- Test quality and quantitative assertions.
- Documentation and operational clarity.

Severity:

- **CRITICAL:** secret, injection, authorization bypass, unsafe deserialization, path traversal, wrong data, data loss, broken vintage semantics.
- **HIGH:** missing boundary validation, swallowed error, resource leak, N+1/per-row network calls, major untested logic.
- **MEDIUM:** deep nesting, unexplained constants, dead code, misleading names, missing type hints.
- **LOW:** debug artifact, untracked TODO, minor style inconsistency, optional optimization.

Verdict:

- Approve: no CRITICAL or HIGH findings.
- Approve with changes: no CRITICAL; narrowly bounded HIGH items are explicitly tracked and policy permits it.
- Request changes: any CRITICAL or multiple unresolved HIGH findings.

Review request format should include summary, files changed, tests/checks run, areas of concern, context/spec, open questions, and exact reproduction commands.

---

## 17. Verification loop before PR or handoff

Run gates in order and fix failures before continuing:

1. **Build/import:** modified modules import and entry points load.
2. **Type check:** run configured `mypy`/`pyright`; otherwise document skip.
3. **Lint/format:** use configured `ruff`/`flake8`; otherwise manual review.
4. **Tests/behavior:** run relevant suite plus collector-specific end-to-end checks.
5. **Security:** dependency scan if available and secret scan/manual review.
6. **Diff review:** inspect `git diff --stat`, full diff, and branch commits.

Minimum viable loop when optional tooling is absent: build/import → behavioral tests → diff review.

Diff review confirms:

- only intended files changed;
- no token, password, `.env`, raw sensitive data, debug print, breakpoint, temporary workaround, or large binary was committed accidentally;
- no generated validation artifact is included unless intentional;
- commit messages are descriptive.

Use this summary:

```markdown
## Verification Summary

| Gate | Status | Notes |
|---|---|---|
| Build/Import | PASS/FAIL/SKIP | ... |
| Type Check | PASS/FAIL/SKIP | ... |
| Lint/Format | PASS/FAIL/SKIP | ... |
| Tests/Behavior | PASS/FAIL/SKIP | ... |
| Security | PASS/FAIL/SKIP | ... |
| Diff Review | PASS/FAIL/SKIP | ... |

Result: Ready for PR / Not ready
```

A skipped gate requires a reason. An unrelated pre-existing failure is documented rather than misrepresented as passing.

---

## 18. New collector build sequence

### Phase 1 — Bootstrap

1. Confirm every intake input.
2. Read the current pilot and relevant guidelines completely.
3. Create `collector_<source>_<dataset>`.
4. Copy fleet-wide and template files from the pilot.
5. Remove only source-specific dependencies/files that are truly unused.
6. Confirm the tree matches the current pilot contract.

### Phase 2 — Configuration and database

1. Set `SCHEMA_NAME` equal to the repository name.
2. Set source-appropriate default start date, auth variables, and documented HTTP settings.
3. Copy database engine and DDL patterns from the pilot.
4. Verify local/production dependency surfaces and `.env.example`.

### Phase 3 — Series curation

1. Apply frequency, rawness, geography, liveness, and history gates.
2. Verify every native ID against the official source.
3. Define structured IDs and round-trip parser.
4. Record mappings locally in `extract.py`.

### Phase 4 — Extraction

1. Fetch current official docs.
2. Implement bounded HTTP behavior and source parsing.
3. Normalize dates, missing values, numbers, units, frequencies, and upstream descriptions.
4. Return the exact extraction contract.
5. Validate at least one observation for every target series or justified sample.

### Phase 5 — Standardized writes

1. Preserve canonical vintage/upsert logic.
2. Write observations before metadata.
3. Derive metadata coverage from the database.
4. Preserve batch write patterns and progress logging.

### Phase 6 — Orchestration and logging

1. Add preflight.
2. Preserve root/application logging separation.
3. Implement start-date rewind.
4. Guarantee a log row in success and failure paths.

### Phase 7 — Special behavior

Only when the declared collector kind requires it, implement forecast archive semantics, forecast-target weights, validation workbook, or release monitoring.

### Phase 8 — Complete verification

Every applicable box in Sections 19 and 20 must pass. Do not declare completion with an unchecked mandatory item.

---

## 19. Phase 8 collector checklist

### Layout

- [ ] Repository name is lowercase `collector_<source>_<dataset>`.
- [ ] `SCHEMA_NAME` exactly matches it.
- [ ] Tree matches the current pilot and contains no speculative directories/files.
- [ ] Fleet-wide verbatim files match the current pilot byte-for-byte.
- [ ] `main.py` is at root and `scripts/` is flat.

### Schema and SQL

- [ ] Ordinary standardized DDL matches the current pilot byte-for-byte.
- [ ] No unauthorized standardized columns or tables were added.
- [ ] All required metadata fields, including source traceability fields, are populated.
- [ ] SQL uses `sqlalchemy.text` with named value parameters.
- [ ] DDL/queries are PostgreSQL and Databricks compatible.
- [ ] Databricks uniqueness does not rely on unenforced PK metadata.

### Code and dependencies

- [ ] Every module has future annotations, type hints, and module docstring.
- [ ] No forbidden package, ORM, base collector, shared core, or unnecessary parser dependency.
- [ ] No `print` outside `__main__`; no silent broad exception.
- [ ] HTTP calls use one managed client, timeout, bounded retry/backoff, and safe logging.
- [ ] Batch writes use multi-row statements and log progress.

### Source fidelity

- [ ] Endpoints and response shapes came from current official documentation.
- [ ] Series were curated by frequency, rawness, scope, liveness, and history.
- [ ] IDs are structured, unique, uppercase, and round-trippable.
- [ ] Names, descriptions, units, frequencies, country/currency, and source URLs match the official source.
- [ ] Sample observations match official values within published rounding.

### Behavior

- [ ] `python -m scripts.init_db` succeeds on a fresh local database.
- [ ] A fresh end-to-end run populates `time_series`, `metadata`, and `logs`.
- [ ] Metadata is built after time-series writes and reflects the full DB history.
- [ ] A second unchanged run produces zero metadata and time-series writes.
- [ ] The second run produces one successful log row.
- [ ] A forced mid-pipeline failure produces one error log with traceback.
- [ ] Soft failures warn/skip; hard failures propagate.

### Output sanity

- [ ] Every metadata row has `observation_count > 0` and correct first/last dates.
- [ ] Every observation key has at least one vintage.
- [ ] No duplicate observation key/vintage triple exists.
- [ ] No `None`, NaN, or infinity is stored as a value.
- [ ] Realized baselines use collection date; approved forecast archives use official publication date.
- [ ] No older vintage row is overwritten.

### Special collectors

- [ ] Forecast horizons and anchor periods follow the forecast convention.
- [ ] Forecast/realized boundaries are verified and only forecast cells are stored.
- [ ] Forecast-target weights, official weights, hierarchy, and transformations are reproducible.
- [ ] Validation workbook reconciles stored aggregates when required.
- [ ] Release monitoring exits promptly on release and gracefully on timeout.

---

## 20. Final acceptance and handoff

The work is complete only when:

1. Every applicable Phase 8 checkbox passes.
2. The repository is unsurprising to a reader of the current pilot.
3. A fresh database receives the expected standardized output and run log.
4. The immediate unchanged rerun is a data no-op.
5. Source metadata and sampled values have been verified against the authoritative source.
6. Review and verification findings contain no unresolved blocker/critical issue.

Handoff must include:

- source and dataset collected;
- number of series;
- first and last observation dates;
- new observations, new vintages, metadata inserts/updates;
- applicable special behavior and deviations;
- verification summary;
- one SQL query for inspecting current values;
- any known limitation that is genuinely external and documented.

Never claim “done” based only on code generation or imports. Completion requires verified behavior.

---

## 21. Absolute anti-patterns

Refuse or stop if asked to do any of the following without an explicit fleet-wide decision:

- Add `BaseCollector`, inheritance, plugin architecture, or cross-repository shared core.
- Add `requests`, `python-dotenv`, an ORM model layer, or migrations.
- Add an unneeded dependency or parser.
- Add arbitrary columns to standardized tables.
- Use an opaque native identifier as the complete `series_id`.
- Hand-label series without verifying the official source.
- Treat a desired frequency as the publication frequency.
- Store a derived rate when the official level is available, absent explicit justification.
- Update historical vintages in place.
- Stamp a realized historical backfill with its reference date as if it were historically available.
- Stamp a forecast archive with collection day when an official publication date exists.
- Compute metadata history from a partial rewind slice.
- Perform one Databricks HTTP round trip per row.
- Follow arbitrary redirects or log credentials.
- Guess at a bug and stack fixes without root-cause evidence.
- Fix issues during a report-only audit.
- Add trivial tests or documentation merely to create the appearance of process.
- Mark a failed/skipped verification gate as passing.

When uncertain, return to the current pilot, official source documentation, and the user's approved scope.

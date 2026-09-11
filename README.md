# Rosstat CPI collector

Russia national monthly CPI forecast-target project. Fleet country code: `RUB`;
economic group: `consumer_prices`; schema: `collector_rosstat_cpi`.
Official starting point: https://rosstat.gov.ru/statistics/price.

**Status: acquisition and database foundation implemented; CPI ingestion is not
implemented or production-ready.** Official documents currently return HTTP 502
from the execution environment. No hierarchy, weight formula or workbook layout
is guessed. See [COMPLIANCE.md](COMPLIANCE.md) for measured results and pending gates.

## Setup

Python 3.11 or newer:

```bash
python -m pip install -e '.[dev]'
```

Copy `.env.example` to `.env` if database access or HTTP tuning is needed.
The manual loader preserves environment overrides. Credentials must stay out of git.

## Acquire the official evidence

```bash
python main.py --research --output ../rosstat-source-evidence
```

This command requires no database. It uses one verified HTTPX client for six
known official pages/documents, then inspects at most one additional layer of
relevant direct document links. It does not crawl regional statistics or select
a workbook by an arbitrary filename. Candidate discovery is deliberately an
inventory, not a verified selection of CPI series.

Downloads have size, redirect, retry and ZIP expansion limits. XLSX inspection
requires secure XML parsing. The output contains original files named by SHA-256
and `manifest.json` with source URLs, hashes, sizes, sheet names, sample cells,
and failures. Source cells are not converted into observations. Legacy XLS files
are preserved but not parsed. PDF files are preserved but not semantically read.
HTML uses the charset declared by its HTTP response; HTML-only charset declarations
have not yet been implemented. Query-string download endpoints are rejected until
verified and explicitly supported.

A failed source, truncated inventory, or absence of any workbook returns exit code
1. Successful acquisition still does not certify source scope or methodology.
Store evidence outside this checkout; generated files must not be committed.
This is a development acquisition operation, not a cache for production collection.

## Initialize the database foundation

Set `COLLECTOR_DB_URL` for PostgreSQL, or `PROD=true` and the Databricks settings:

```bash
python main.py --init-db
```

Creates only `metadata`, `time_series`, and `logs`, without observation writes.
The inherited float-type adaptation uses DOUBLE PRECISION for PostgreSQL and
DOUBLE for Databricks. No weights schema is created before its source semantics
are established. A configured database also receives one run log from research
operations; without a database, the evidence manifest and console capture results.
Log persistence is best-effort if the database itself is unavailable.

The observation writer retains collection-date vintages, unchanged-value no-ops,
same-day updates and later revisions. A changed observation submitted with a date
earlier than the latest stored vintage is rejected before any batch is written.

## Verification

```bash
python -m pytest -q -W ignore::DeprecationWarning
python -m ruff check main.py scripts tests
python -m ruff format --check main.py scripts tests
python -m compileall -q main.py scripts tests
```

25 tests passed. Fixtures are synthetic. Storage behavior was tested with SQLite;
PostgreSQL and Databricks execution has not been verified. The full Rosstat parser,
metadata generation, weights, bottom-up reconstruction, audit Excel and monthly
release monitoring remain pending official source inspection. There is no
`--no-watch` ingestion command yet.

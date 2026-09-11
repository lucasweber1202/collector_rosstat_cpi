"""Runtime settings loaded from environment variables and an optional .env."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = ROOT_DIR / ".env"

if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if value and key not in os.environ:
            os.environ[key] = value

SCHEMA_NAME = "collector_rosstat_cpi"
CATALOG_NAME = "macrobond_inhouse"
METADATA_TABLE = "metadata"
TIME_SERIES_TABLE = "time_series"
WEIGHTS_TABLE = "weights"
LOGS_TABLE = "logs"

# Rosstat revises a published month only exceptionally, but the current-year
# workbooks are rewritten on every monthly release, so a rerun re-reads the
# whole current and previous calendar year anyway. Five months keeps the
# fleet default for the incremental path.
START_DATE_LOOKBACK_MONTHS = 5
PROD = os.getenv("PROD", "false").lower() in ("1", "true", "yes")
DATABASE_URL = os.getenv("COLLECTOR_DB_URL", "")
# Rosstat's own methodology note states CPI observation started in 1992 and that
# 1991 carries only the four aggregate groups; ipc_mes publishes from 1991-01.
DEFAULT_START_DATE = date.fromisoformat(os.getenv("COLLECTOR_START_DATE", "1991-01-01"))

REQUEST_TIMEOUT = float(os.getenv("COLLECTOR_HTTP_TIMEOUT", "90"))
# A full historical build downloads about eight workbooks in a row from one
# host. The pause is politeness towards a single-origin government file server,
# not a documented published rate limit.
DOWNLOAD_DELAY = float(os.getenv("COLLECTOR_DOWNLOAD_DELAY", "1"))
MAX_RETRIES = int(os.getenv("COLLECTOR_MAX_RETRIES", "4"))
BACKOFF_FACTOR = float(os.getenv("COLLECTOR_BACKOFF_FACTOR", "2"))
RATE_LIMIT_BACKOFF = float(os.getenv("COLLECTOR_RATE_LIMIT_BACKOFF", "20"))
MAX_RETRY_DELAY = float(os.getenv("COLLECTOR_MAX_RETRY_DELAY", "120"))
# The largest workbook this collector reads is the ~1 MB combined index/weights
# publication; the ceiling is generous for it and still bounds memory.
MAX_DOWNLOAD_BYTES = int(os.getenv("COLLECTOR_MAX_DOWNLOAD_BYTES", str(64 * 1024 * 1024)))
USER_AGENT = os.getenv(
    "COLLECTOR_USER_AGENT",
    "collector_rosstat_cpi/0.1 (+https://github.com/lucasweber1202/collector_rosstat_cpi)",
)
LOG_LEVEL = os.getenv("COLLECTOR_LOG_LEVEL", "INFO")
POLL_INTERVAL = float(os.getenv("COLLECTOR_POLL_INTERVAL", "60"))
MAX_WAIT = float(os.getenv("COLLECTOR_MAX_WAIT", "900"))

# rosstat.gov.ru presents a certificate issued by the Russian national CA, which
# no default trust store carries. The collector adds that CA to an otherwise
# standard SSL context instead of weakening verification; see README.md for the
# provenance and fingerprints of the two certificates in this bundle.
CA_BUNDLE_PATH = Path(
    os.getenv("COLLECTOR_ROSSTAT_CA_BUNDLE", str(ROOT_DIR / "rosstat_ca_bundle.pem"))
)

# Published index values carry two decimals and published weights three, so a
# parent rebuilt from rounded children cannot match its published value exactly.
# The measured maximum residual over the full published panel is 0.024 index
# points; this floor leaves room for it without hiding a real aggregation break.
VALIDATION_TOLERANCE_PP = float(os.getenv("COLLECTOR_VALIDATION_TOLERANCE_PP", "0.10"))
# Weights are published to three decimals, so a parent's children sum to it
# within a few thousandths. Anything larger is a classification break.
WEIGHT_TOLERANCE_PP = float(os.getenv("COLLECTOR_WEIGHT_TOLERANCE_PP", "0.005"))
# Share of reconcilable bottom-up checks that must actually execute. Measured
# coverage on the current publication is 1.0 for every month of the panel.
MIN_VALIDATION_COVERAGE = float(os.getenv("COLLECTOR_MIN_VALIDATION_COVERAGE", "0.99"))

DBX_SERVER_HOSTNAME = os.getenv("DBX_SERVER_HOSTNAME", "")
DBX_HTTP_PATH = os.getenv("DBX_HTTP_PATH", "")
AKV_VAULT_URL = os.getenv("AKV_VAULT_URL", "")
AKV_SECRET_NAME = os.getenv("AKV_SECRET_NAME", "databricks-token")


def missing_environment(prod: bool = PROD) -> list[str]:
    """Return every required environment variable that is unset, not just the first.

    Reported before any database or HTTP work so one run surfaces the complete
    list. The Databricks token is deliberately absent: it may also come from a
    notebook/job context, so its absence is a warning rather than a hard failure.
    """
    if not prod:
        return [] if DATABASE_URL else ["COLLECTOR_DB_URL"]
    required = {"DBX_SERVER_HOSTNAME": DBX_SERVER_HOSTNAME, "DBX_HTTP_PATH": DBX_HTTP_PATH}
    return sorted(name for name, value in required.items() if not value)


def unresolved_credentials(prod: bool = PROD) -> list[str]:
    """Return credential sources that are unset but may still resolve at runtime."""
    if prod and not os.getenv("DATABRICKS_TOKEN") and not AKV_VAULT_URL:
        return ["DATABRICKS_TOKEN", "AKV_VAULT_URL"]
    return []

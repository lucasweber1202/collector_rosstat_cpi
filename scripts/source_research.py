"""Acquire and inspect official Rosstat documents without guessing statistical layouts.

This module inventories evidence. It never emits CPI observations or treats
successful downloads as proof of national scope, weights, or reconciliation.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import time
import zipfile
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from openpyxl import load_workbook
from openpyxl.xml import DEFUSEDXML

from scripts.config import BACKOFF_FACTOR, MAX_RETRIES, REQUEST_TIMEOUT, USER_AGENT

logger = logging.getLogger(__name__)
SOURCE_URL = "https://rosstat.gov.ru/statistics/price"
# Discovered in official search results; not asserted to be live workbook URLs.
SOURCE_PAGES = (
    SOURCE_URL,
    "https://rosstat.gov.ru/free_doc/new_site/prices/bd/bd_1902003.htm",
    "https://rosstat.gov.ru/storage/mediabank/tab-KIPC.htm",
    "https://rosstat.gov.ru/free_doc/new_site/prices/ipc_met.htm",
    "https://rosstat.gov.ru/bgd/free/B00_24/IssWWW.exe/Stg/d000/I000111R.HTM",
    "https://55.rosstat.gov.ru/storage/mediabank/metod_ipc_2026.pdf",
)
ALLOWED_HOSTS = frozenset({"rosstat.gov.ru", "55.rosstat.gov.ru"})
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_DOCUMENTS = 30
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def validate_url(url: str) -> str:
    """Allow only known official HTTPS hosts and paths, without credentials/query data."""
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname not in ALLOWED_HOSTS
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.query
        or any(ord(c) < 32 for c in url)
    ):
        raise ValueError("Refusing URL outside approved official HTTPS document paths")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _build_client() -> httpx.Client:
    """Use a single verified, environment-aware client per research invocation."""
    if not 0 < REQUEST_TIMEOUT <= 300 or not 0 <= MAX_RETRIES <= 5:
        raise ValueError("HTTP timeout must be in (0,300]; retries in [0,5]")
    if not 1 <= BACKOFF_FACTOR <= 10:
        raise ValueError("HTTP backoff factor must be in [1,10]")
    return httpx.Client(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=False,
        trust_env=True,
        verify=True,
        headers={"User-Agent": USER_AGENT},
    )


def fetch_document(client: httpx.Client, url: str) -> dict[str, Any]:
    """Bound bytes/retries/redirects and never log raw error bodies or headers."""
    current = validate_url(url)
    seen = {current}
    for hop in range(MAX_REDIRECTS + 1):
        redirect = None
        for attempt in range(MAX_RETRIES + 1):
            retry_after = 0.0
            try:
                with client.stream("GET", current, follow_redirects=False) as response:
                    status = response.status_code
                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Missing redirect destination")
                        redirect = validate_url(urljoin(current, location))
                        if redirect in seen or hop == MAX_REDIRECTS:
                            raise ValueError("Repeated or excessive redirect")
                        seen.add(redirect)
                        break
                    if status == 429 or 500 <= status <= 599:
                        raw_retry = response.headers.get("retry-after", "")
                        retry_after = min(float(raw_retry), 60.0) if raw_retry.isdigit() else 0.0
                        reason = f"HTTP {status}"
                    elif status != 200:
                        raise RuntimeError(f"Official document request failed: HTTP {status}")
                    else:
                        length = response.headers.get("content-length")
                        if length is not None and (
                            not length.isdigit() or int(length) > MAX_DOWNLOAD_BYTES
                        ):
                            raise ValueError("Invalid declared document size")
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            if len(body) + len(chunk) > MAX_DOWNLOAD_BYTES:
                                raise ValueError("Document size exceeds download budget")
                            body.extend(chunk)
                        if not body:
                            raise ValueError("Empty official document")
                        return {
                            "url": current,
                            "body": bytes(body),
                            "content_type": response.headers.get("content-type", "")
                            .split(";")[0]
                            .strip()
                            .lower(),
                            "encoding": response.encoding,
                        }
            except httpx.TransportError:
                # Exception strings can contain proxy credentials; expose only category.
                reason = "transport/TLS failure"
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Official document unavailable after {attempt + 1} attempts: {reason}"
                ) from None
            delay = min(60.0, max(retry_after, BACKOFF_FACTOR**attempt))
            logger.warning(
                "Official document %s; retry %d/%d in %.1fs",
                reason,
                attempt + 1,
                MAX_RETRIES,
                delay,
            )
            time.sleep(delay)
        if redirect is not None:
            current = redirect
    raise RuntimeError("Redirect budget exhausted")


class _Links(HTMLParser):
    """Retain anchor text including nested spans; this is document discovery only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.words: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            values = dict(attrs)
            self.href = values.get("href")
            self.words = [values.get("title") or ""]

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.words.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href is not None:
            self.links.append((self.href, " ".join(" ".join(self.words).split())))
            self.href = None


def discover_links(page: str, base_url: str) -> list[dict[str, str]]:
    """Return all relevant direct document candidates; never silently pick the first."""
    validate_url(base_url)
    parser = _Links()
    parser.feed(page)
    found: dict[str, dict[str, str]] = {}
    for href, title in parser.links:
        label = title.casefold()
        if not any(
            word in label
            for word in (
                "кипц",
                "потребительских цен",
                "потребительских расходов",
                "consumer price",
                "consumer expenditure",
            )
        ):
            continue
        if any(
            word in label
            for word in ("област", "район", "краю", "федеральным округ", "субъектам", "республике")
        ):
            continue
        try:
            url = validate_url(urljoin(base_url, href))
        except ValueError:
            continue
        if not urlsplit(url).path.lower().endswith((".xls", ".xlsx", ".pdf", ".htm", ".html")):
            continue
        found[url] = {"url": url, "title": title}
    return [found[url] for url in sorted(found)]


def inspect_document(body: bytes, content_type: str) -> dict[str, Any]:
    """Check file signatures/ZIP budget and expose workbook cells without interpreting CPI."""
    if content_type == XLSX_MIME and not body.startswith(b"PK\x03\x04"):
        raise ValueError("XLSX signature mismatch")
    if content_type == "application/pdf" and not body.startswith(b"%PDF-"):
        raise ValueError("PDF signature mismatch")
    if body.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(x.file_size for x in entries) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("ZIP uncompressed size exceeds inspection budget")
            names = {entry.filename for entry in entries}
            if not {"[Content_Types].xml", "xl/workbook.xml"} <= names:
                raise ValueError("ZIP is not an XLSX workbook")
        if not DEFUSEDXML:
            raise RuntimeError("Secure XLSX inspection requires defusedxml enabled")
        book = load_workbook(io.BytesIO(body), read_only=True, data_only=False, keep_links=False)
        try:
            sheets = []
            for sheet in book.worksheets:
                sample = [
                    [value.isoformat() if isinstance(value, datetime) else value for value in row]
                    for row in sheet.iter_rows(
                        max_row=min(sheet.max_row or 12, 12),
                        max_col=min(sheet.max_column or 12, 12),
                        values_only=True,
                    )
                ]
                sheets.append(
                    {
                        "name": sheet.title,
                        "rows": sheet.max_row,
                        "columns": sheet.max_column,
                        "sample_rows": sample,
                    }
                )
            return {"kind": "xlsx", "sheets": sheets}
        finally:
            book.close()
    if body.startswith(b"%PDF-"):
        return {"kind": "pdf"}
    if body.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return {"kind": "xls", "inspection": "Legacy workbook; layout/parser unverified"}
    if content_type in ("text/html", "application/xhtml+xml"):
        return {"kind": "html"}
    raise ValueError("Unsupported content type or file signature")


def research_sources(output: Path) -> dict[str, Any]:
    """Download seed documents and one layer of candidates, saving reproducible evidence.

    Source failures are recorded individually so one unavailable page does not
    prevent inspection of others. No success means a failed research run.
    """
    output.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "collected_at": datetime.now(UTC).isoformat(),
        "documents": [],
        "errors": [],
        "truncated": False,
        "statistical_validation": "NOT_PERFORMED",
    }
    queue = [(url, "official source seed", 0) for url in SOURCE_PAGES]
    seen: set[str] = set()
    with _build_client() as client:
        while queue and len(seen) < MAX_DOCUMENTS:
            url, title, depth = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                response = fetch_document(client, url)
                body = response["body"]
                info = inspect_document(body, response["content_type"])
                digest = hashlib.sha256(body).hexdigest()
                name = digest + "." + info["kind"]
                (output / name).write_bytes(body)
                report["documents"].append(
                    {
                        "requested_url": url,
                        "url": response["url"],
                        "title": title,
                        "sha256": digest,
                        "bytes": len(body),
                        "content_type": response["content_type"],
                        "file": name,
                        **info,
                    }
                )
                if info["kind"] == "html" and depth == 0:
                    # httpx applies the response's declared charset when available.
                    encoding = response["encoding"] or "utf-8"
                    for link in discover_links(
                        body.decode(encoding, errors="replace"), response["url"]
                    ):
                        queue.append((link["url"], link["title"], depth + 1))
            except (RuntimeError, ValueError, zipfile.BadZipFile, OSError) as exc:
                # Known messages from our boundaries contain no request headers.
                report["errors"].append(
                    {"url": url, "error_type": type(exc).__name__, "message": str(exc)[:500]}
                )
                logger.warning("Source inspection failed: %s (%s)", url, type(exc).__name__)
    report["truncated"] = any(url not in seen for url, _, _ in queue)
    report["downloaded_workbooks"] = sum(d["kind"] in ("xlsx", "xls") for d in report["documents"])
    (output / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report

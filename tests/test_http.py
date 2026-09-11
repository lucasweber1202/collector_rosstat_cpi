"""HTTP behaviour: host allowlist, bounded retries, mirror fallback, size ceiling."""

from __future__ import annotations

import ssl
from typing import Any

import httpx
import pytest

from scripts import extract
from scripts.extract import (
    ALLOWED_HOSTS,
    build_ssl_context,
    discover_files,
    fetch,
    fetch_from_any_host,
)


def _client(handler: object) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def test_requests_outside_the_official_hosts_are_refused() -> None:
    with (
        _client(lambda request: httpx.Response(200)) as client,
        pytest.raises(ValueError, match="allowlist"),
    ):
        fetch(client, "https://evil.example.com/storage/mediabank/ipc_spr_08-2026.xlsx")


def test_allowlist_covers_only_the_two_official_hosts() -> None:
    assert ALLOWED_HOSTS == {"rosstat.gov.ru", "eng.rosstat.gov.ru"}


def test_retryable_status_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract.time, "sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"payload")

    with _client(handler) as client:
        assert fetch(client, "https://rosstat.gov.ru/statistics/price") == b"payload"
    assert attempts["count"] == 3


def test_a_non_retryable_status_fails_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract.time, "sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404)

    with _client(handler) as client, pytest.raises(httpx.HTTPStatusError):
        fetch(client, "https://rosstat.gov.ru/statistics/price")
    assert attempts["count"] == 1


def test_an_oversized_body_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract, "MAX_DOWNLOAD_BYTES", 8)
    with (
        _client(lambda request: httpx.Response(200, content=b"x" * 64)) as client,
        pytest.raises(ValueError, match="above the ceiling"),
    ):
        fetch(client, "https://rosstat.gov.ru/statistics/price")


def test_the_english_mirror_serves_a_file_the_primary_host_cannot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(extract.time, "sleep", lambda _seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "rosstat.gov.ru":
            return httpx.Response(503)
        return httpx.Response(200, content=b"mirrored")

    with _client(handler) as client:
        payload, url = fetch_from_any_host(client, "/storage/mediabank/ipc_spr_08-2026.xlsx")
    assert payload == b"mirrored"
    assert url.startswith("https://eng.rosstat.gov.ru/")


PAGE = """
<a href="/storage/mediabank/ipc_spr_07-2026.xlsx">XLSX</a>
<a href="/storage/mediabank/ipc_spr_08-2026.xlsx">XLSX</a>
<a href="/storage/mediabank/ipc_mes_08-2026.xlsx">XLSX</a>
<a href="https://example.com/elsewhere/ipc_spr_12-2099.xlsx">not mediabank</a>
"""


def test_discovery_picks_the_newest_linked_month() -> None:
    with _client(lambda request: httpx.Response(200, content=PAGE.encode())) as client:
        found = discover_files(
            client,
            "https://rosstat.gov.ru/statistics/price",
            {
                "monthly_detail": extract._FILE_PATTERNS["monthly_detail"],
                "monthly_headline": extract._FILE_PATTERNS["monthly_headline"],
            },
        )
    assert found["monthly_detail"] == "/storage/mediabank/ipc_spr_08-2026.xlsx"
    assert found["monthly_headline"] == "/storage/mediabank/ipc_mes_08-2026.xlsx"


def test_the_ssl_context_verifies_and_carries_the_russian_state_ca() -> None:
    """Verification stays on; the bundle only adds the CA that certifies Rosstat."""
    context = build_ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    subjects: list[Any] = [entry.get("subject", ()) for entry in context.get_ca_certs()]
    common_names = {
        pair[1] for subject in subjects for relative_name in subject for pair in relative_name
    }
    assert "Russian Trusted Root CA" in common_names
    assert "Russian Trusted Sub CA" in common_names

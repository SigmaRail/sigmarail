from urllib.error import HTTPError

import pytest

from sigmarail_lab.runtime import ch_http
from sigmarail_lab.runtime.ch_http import ChHttpClient, ChHttpSettings


def test_strict_query_raises_instead_of_returning_an_empty_cache(monkeypatch):
    requested = []

    def reject(request, timeout):
        requested.append(request.full_url)
        raise HTTPError(request.full_url, 500, "query failed", {}, None)

    monkeypatch.setattr(ch_http, "urlopen", reject)
    client = ChHttpClient(ChHttpSettings("localhost", "8123", "sigmarail", "user", "pass"))

    with pytest.raises(RuntimeError, match="HTTP 500"):
        client.query_json_each_row("SELECT 1", fail_on_error=True)

    assert len(requested) == 1
    assert "result_overflow_mode=throw" in requested[0]


def test_legacy_query_keeps_empty_result_on_http_error(monkeypatch):
    def reject(request, timeout):
        raise HTTPError(request.full_url, 500, "query failed", {}, None)

    monkeypatch.setattr(ch_http, "urlopen", reject)
    client = ChHttpClient(ChHttpSettings("localhost", "8123", "sigmarail", "user", "pass"))

    assert client.query_json_each_row("SELECT 1") == []

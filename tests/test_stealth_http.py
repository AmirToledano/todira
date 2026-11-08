"""scraper/utils/stealth_http.py: proxy parsing and the close-and-reopen retry loop."""

import httpx
import pytest
from utils import stealth_http
from utils.stealth_http import StealthHTTPClient, _parse_proxies


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(stealth_http.time, "sleep", lambda _s: None)


def _scripted(monkeypatch, client: StealthHTTPClient, outcomes):
    """Make each new client answer with the next outcome; record the proxy it was opened with."""
    opened = []
    clients = []
    outcomes = list(outcomes)

    def new_client(proxy):
        opened.append(proxy)
        outcome = outcomes.pop(0)

        def handler(request):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        c = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(c)
        return c

    monkeypatch.setattr(client, "_new_client", new_client)
    return opened, clients


def test_parse_proxies_from_env(monkeypatch):
    monkeypatch.setenv("ROTATING_PROXY_URL", " http://a:1, http://b:2\nhttp://a:1 ,, ")
    assert _parse_proxies(None) == ["http://a:1", "http://b:2"]


def test_parse_proxies_empty(monkeypatch):
    monkeypatch.delenv("ROTATING_PROXY_URL", raising=False)
    assert _parse_proxies(None) == []
    assert _parse_proxies(["", "  "]) == []


def test_explicit_list_wins_over_env(monkeypatch):
    monkeypatch.setenv("ROTATING_PROXY_URL", "http://env:1")
    assert StealthHTTPClient(["http://x:1"]).proxies == ["http://x:1"]


def test_success_returns_json(monkeypatch):
    c = StealthHTTPClient([])
    opened, clients = _scripted(monkeypatch, c, [httpx.Response(200, json={"ok": 1})])
    assert c.fetch("https://example.test/api") == {"ok": 1}
    assert opened == [None] and all(c.is_closed for c in clients)


def test_blocked_then_ok_switches_proxy_and_closes_each_client(monkeypatch):
    c = StealthHTTPClient(["http://a:1", "http://b:2"])
    opened, clients = _scripted(
        monkeypatch, c,
        [httpx.Response(403), httpx.Response(429), httpx.Response(200, json=[1])],
    )
    assert c.fetch("https://example.test/api") == [1]
    assert len(opened) == 3
    assert opened[0] != opened[1] and opened[1] != opened[2]
    assert len(clients) == len(opened) and all(c.is_closed for c in clients)


def test_network_error_retries_on_new_proxy(monkeypatch):
    c = StealthHTTPClient(["http://a:1", "http://b:2"])
    opened, clients = _scripted(
        monkeypatch, c,
        [httpx.ConnectError("boom"), httpx.Response(200, json={"ok": 2})],
    )
    assert c.fetch("https://example.test/api") == {"ok": 2}
    assert opened[0] != opened[1]
    assert len(clients) == len(opened) and all(c.is_closed for c in clients)


def test_all_blocked_returns_empty(monkeypatch):
    c = StealthHTTPClient(["http://a:1"])
    _scripted(monkeypatch, c, [httpx.Response(429)] * 3)
    assert c.fetch("https://example.test/api") == {}


def test_all_network_errors_reraise(monkeypatch):
    c = StealthHTTPClient([])
    _scripted(monkeypatch, c, [httpx.ReadTimeout("slow")] * 3)
    with pytest.raises(httpx.ReadTimeout):
        c.fetch("https://example.test/api")


def test_other_status_raises_without_retry(monkeypatch):
    c = StealthHTTPClient([])
    opened, _ = _scripted(monkeypatch, c, [httpx.Response(500)])
    with pytest.raises(httpx.HTTPStatusError):
        c.fetch("https://example.test/api")
    assert len(opened) == 1


def test_real_client_builds_with_proxy():
    c = StealthHTTPClient(["http://127.0.0.1:9"])
    with c._new_client("http://127.0.0.1:9") as client:
        assert client.headers["User-Agent"]


# --- drop-in httpx interface (get/post/request) ---


def test_get_accepts_httpx_kwargs_and_returns_real_response(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["ua"] = request.headers.get("User-Agent")
        seen["accept"] = request.headers.get("Accept")
        seen["timeout"] = request.extensions.get("timeout")
        return httpx.Response(200, text="<html>ok</html>")

    c = StealthHTTPClient(proxy_list=[])
    monkeypatch.setattr(c, "_new_client", lambda proxy: httpx.Client(
        transport=httpx.MockTransport(handler), headers=c._get_random_headers()))
    resp = c.get("https://example.test/p", params={"a": "1"}, timeout=90, headers={"Accept": "text/html"})
    assert isinstance(resp, httpx.Response)
    assert resp.status_code == 200
    assert resp.text == "<html>ok</html>"
    assert seen["url"] == "https://example.test/p?a=1"
    assert seen["ua"].startswith("Mozilla/5.0")
    assert seen["accept"] == "text/html"
    assert seen["timeout"]["read"] == 90


def test_get_returns_other_status_without_raising_or_retrying(monkeypatch):
    c = StealthHTTPClient(proxy_list=["http://p1:1", "http://p2:2"])
    opened, _ = _scripted(monkeypatch, c, [httpx.Response(500, text="err")])
    resp = c.get("https://x")
    assert resp.status_code == 500
    assert resp.text == "err"
    assert len(opened) == 1


def test_get_all_blocked_returns_last_blocked_response(monkeypatch):
    c = StealthHTTPClient(proxy_list=["http://p1:1", "http://p2:2"])
    opened, _ = _scripted(monkeypatch, c, [httpx.Response(429), httpx.Response(403), httpx.Response(429)])
    resp = c.get("https://x")
    assert resp.status_code == 429
    assert len(opened) == 3


def test_get_blocked_then_ok_rotates_proxy(monkeypatch):
    c = StealthHTTPClient(proxy_list=["http://p1:1", "http://p2:2"])
    opened, _ = _scripted(monkeypatch, c, [httpx.Response(403), httpx.Response(200, json={"k": 2})])
    resp = c.get("https://x")
    assert resp.json() == {"k": 2}
    assert opened[0] != opened[1]


def test_get_all_network_errors_reraise_as_httpx_error(monkeypatch):
    c = StealthHTTPClient(proxy_list=["http://p1:1"])
    _scripted(monkeypatch, c, [httpx.ConnectTimeout("t")] * 3)
    with pytest.raises(httpx.HTTPError):
        c.get("https://x", timeout=5)


def test_post_sends_body(monkeypatch):
    seen = {}

    def handler(request):
        seen["method"] = request.method
        seen["body"] = request.content
        return httpx.Response(201, json={"id": 7})

    c = StealthHTTPClient(proxy_list=[])
    monkeypatch.setattr(c, "_new_client", lambda proxy: httpx.Client(transport=httpx.MockTransport(handler)))
    resp = c.post("https://x", json={"q": 1})
    assert resp.status_code == 201
    assert resp.json() == {"id": 7}
    assert seen["method"] == "POST"
    assert seen["body"] == b'{"q":1}'

"""2026-09-24 real owner report: several deploys in one night each rewrote style.css heavily, and
the owner's own real mobile browser kept showing stale/broken layouts a fresh Playwright browser
(no prior cache) never reproduced — /static/style.css was linked with no cache-busting query
string at all, unlike todira-brand.webp's own ?v=4, so a browser could keep serving an old cached
copy across deploys. website/main.py now injects GIT_SHA (the same git commit already used as the
deploy's own image tag) as `static_version` into every template, and base.html appends it to the
stylesheet link — this test locks that down against the ACTUAL rendered page, not a mock.

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment) — website/main.py shares a basename with scraper/main.py so it can't go through a
bare `import main`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))


def test_stylesheet_link_carries_a_cache_busting_version(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123realcommit")
    spec = importlib.util.spec_from_file_location(
        "website_main_cache_busting", _WEBSITE_DIR / "main.py"
    )
    website_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(website_main)

    from fastapi.testclient import TestClient

    client = TestClient(website_main.app, raise_server_exceptions=True)
    resp = client.get("/")

    assert resp.status_code == 200
    assert 'href="/static/style.css?v=abc123realcommit"' in resp.text
    # Never the bare, un-versioned URL — that's exactly the stale-cache gap this fixes.
    assert 'href="/static/style.css"' not in resp.text


def test_stylesheet_link_falls_back_to_a_stable_dev_version_when_git_sha_is_unset(monkeypatch):
    monkeypatch.delenv("GIT_SHA", raising=False)
    spec = importlib.util.spec_from_file_location(
        "website_main_cache_busting_fallback", _WEBSITE_DIR / "main.py"
    )
    website_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(website_main)

    from fastapi.testclient import TestClient

    client = TestClient(website_main.app, raise_server_exceptions=True)
    resp = client.get("/")

    assert resp.status_code == 200
    assert 'href="/static/style.css?v=dev"' in resp.text

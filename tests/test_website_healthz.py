"""Tests for /healthz (website/main.py) — added 2026-09-08 as part of a pre-launch reliability
pass. Before this, no Deployment in charts/todira had any liveness/readiness probe at all, so a
hung-but-still-running process (an event loop deadlock, a lost DB connection that never recovers)
would sit "Running" forever with zero automatic recovery. This checks a real DB round-trip, not
just "the process is up" — a website that's running but can't reach Postgres is not healthy.

Same importlib-loading approach as the other website test files (see test_website_paid_access.py's
own comment).
"""
from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_healthz", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


class _FakeSession:
    def __init__(self, raise_on_execute=False):
        self._raise = raise_on_execute

    def execute(self, stmt):
        if self._raise:
            raise RuntimeError("simulated DB outage")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_healthz_returns_200_when_db_reachable(client):
    @contextmanager
    def fake_get_session():
        yield _FakeSession(raise_on_execute=False)

    with patch.object(website_main, "get_session", fake_get_session):
        resp = client.get("/healthz")

    assert resp.status_code == 200


def test_healthz_returns_503_when_db_unreachable(client):
    @contextmanager
    def fake_get_session():
        yield _FakeSession(raise_on_execute=True)

    with patch.object(website_main, "get_session", fake_get_session):
        resp = client.get("/healthz")

    assert resp.status_code == 503

"""Apple Pay domain verification (2026-10-16): Apple fetches the file the owner downloaded from Takbull from
/.well-known/apple-developer-merchantid-domain-association. It must come back 200, unchanged, with no redirect."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_apple_pay", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


def test_apple_pay_domain_association_file_is_served_byte_for_byte():
    client = TestClient(website_main.app, follow_redirects=False)
    resp = client.get("/.well-known/apple-developer-merchantid-domain-association")

    assert resp.status_code == 200
    assert resp.content == (_WEBSITE_DIR / "apple-pay" / "apple-developer-merchantid-domain-association").read_bytes()
    assert b'"pspId"' in resp.content

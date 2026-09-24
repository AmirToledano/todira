"""2026-09-24 real production bug, confirmed via a real headless-browser diagnostic against the
live site (not guessed): StaticFiles guesses each served file's Content-Type from Python's own
mimetypes module, which reads its registry from the underlying OS's /etc/mime.types — the
production container's own copy didn't know .webp at all, so /static/todira-brand.webp (the
site's own logo, referenced on every page via base.html) was served as generic
application/octet-stream instead of image/webp. A browser that can't recognize a response's
content-type falls back to offering it as a raw file download instead of rendering it — the real
mechanism behind a real owner screenshot of a phone Safari download prompt for a todira.app
resource. website/main.py now registers image/webp explicitly via mimetypes.add_type() at import
time, so this can't silently regress on a future base-image/OS change again — this test locks that
down against the ACTUAL StaticFiles-mounted app and a real file on disk, not a mock.

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

_spec = importlib.util.spec_from_file_location("website_main_static_mime", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


def test_webp_static_asset_serves_with_the_real_image_content_type():
    client = TestClient(website_main.app, raise_server_exceptions=True)

    resp = client.get("/static/todira-brand.webp")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert resp.headers["content-type"] != "application/octet-stream"


def test_webmanifest_static_asset_serves_with_the_real_manifest_content_type():
    client = TestClient(website_main.app, raise_server_exceptions=True)

    resp = client.get("/static/site.webmanifest")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/manifest+json"
    assert resp.headers["content-type"] != "application/octet-stream"

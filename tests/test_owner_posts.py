"""2026-10-31 (owner-approved): free posting for flat owners (website/owner_posts.py)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import io
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_owner_posts", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

import owner_posts  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TODAY = dt.date(2026, 10, 31)
GOOD = {
    "city": "חיפה", "street": "הנביאים 12", "rooms": "3.5", "price": "4,200", "size": "72", "floor": "2",
    "move_in": "2026-11-15", "description": "דירה מוארת עם מרפסת, קרובה לתחבורה ציבורית.", "name": "דנה",
    "phone": "050-123 4567", "confirm": "1",
}


@pytest.mark.parametrize(("raw", "expected"), [
    ("050-1234567", "0501234567"), ("+972 50 123 4567", "0501234567"), ("02-6543210", "026543210"),
    ("0771234567", "0771234567"), ("12345", None), ("", None), ("0501234", None),
])
def test_phone(raw, expected):
    assert owner_posts.normalize_phone(raw) == expected


def test_a_good_form():
    fields, errors = owner_posts.parse(GOOD, {"חיפה"}, TODAY)
    assert errors == []
    assert fields["rooms"] == Decimal("3.5") and fields["price"] == 4200 and fields["contact_phone"] == "0501234567"
    assert fields["move_in_date"] == dt.date(2026, 11, 15)


@pytest.mark.parametrize(("field", "value"), [
    ("city", "עיר שלא קיימת"), ("rooms", "3.3"), ("rooms", "0"), ("price", "50"), ("size", "abc"),
    ("move_in", "2026-10-01"), ("description", "קצר"), ("name", "א"), ("phone", "123"), ("confirm", ""),
])
def test_each_wrong_field_is_named(field, value):
    _fields, errors = owner_posts.parse({**GOOD, field: value}, {"חיפה"}, TODAY)
    assert field in errors


def test_optional_fields_may_be_empty():
    fields, errors = owner_posts.parse({**GOOD, "street": "", "size": "", "floor": "", "move_in": ""}, {"חיפה"}, TODAY)
    assert errors == []
    assert fields["street"] is None and fields["size_sqm"] is None and fields["move_in_date"] is None


def test_photos_are_resized_to_a_jpeg_and_junk_is_refused():
    from PIL import Image

    raw = io.BytesIO()
    Image.new("RGB", (4000, 3000), (120, 140, 160)).save(raw, "PNG")
    jpeg = owner_posts.resize_photo(raw.getvalue())
    with Image.open(io.BytesIO(jpeg)) as image:
        assert image.format == "JPEG" and max(image.size) == owner_posts.PHOTO_MAX_SIDE
    assert owner_posts.resize_photo(b"not a picture") is None


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_the_form_page_and_its_approved_wording(client):
    resp = client.get("/post?lang=he")
    assert resp.status_code == 200
    assert "יש לך דירה להשכרה? מפרסמים כאן בחינם" in resp.text
    assert 'name="website"' in resp.text  # the field only scripts fill


def test_a_wrong_form_comes_back_marked_and_saves_nothing(client, monkeypatch):
    monkeypatch.setattr(owner_posts, "create", lambda *a, **k: pytest.fail("saved a wrong form"))
    resp = client.post("/post?lang=he", data={**GOOD, "phone": "1"})
    assert resp.status_code == 400
    assert "has-error" in resp.text and "יש שדות שצריך לתקן" in resp.text


def test_a_script_filling_the_hidden_field_gets_a_thank_you_and_nothing_is_saved(client, monkeypatch):
    monkeypatch.setattr(owner_posts, "create", lambda *a, **k: pytest.fail("saved a bot post"))
    resp = client.post("/post", data={**GOOD, "website": "http://spam"})
    assert resp.status_code == 200


class _NoDatabase:
    """Stands in for get_session(): CI has no database driver, and nobody here is signed in."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, model, key):
        return None


def test_the_contact_page_needs_access(client, monkeypatch):
    monkeypatch.setattr(website_main, "get_session", _NoDatabase)
    resp = client.get("/owner-ad/1")
    assert resp.status_code == 303 and resp.headers["location"] == "/upgrade"


def test_admin_posts_is_hidden_from_everyone_else(client, monkeypatch):
    monkeypatch.setattr(website_main, "get_session", _NoDatabase)
    assert client.get("/admin/posts").status_code == 404
    assert client.post("/admin/posts/1/approve").status_code == 404

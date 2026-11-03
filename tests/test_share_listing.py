"""Sharing a flat (2026-10-22 owner request): signed /s/<token> links, the public page they open, the share button
in the detail view, and the bot card's share button (off until the owner approves its wording)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_share", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

from todira_common import cards, share  # noqa: E402

_NOW = dt.datetime.now(dt.timezone.utc)


def _listing(**overrides):
    values = {
        "id": 7, "source": "komo", "url": "https://www.komo.co.il/secret-source-url", "deal_type": "rent",
        "property_type": "apartment", "price": 4200, "rooms": Decimal("3.0"), "floor": 2, "floor_total": 5,
        "size_sqm": 75, "city": "פתח תקווה", "neighborhood": None, "street": "ארטור רופין",
        "has_parking": True, "has_elevator": False, "has_balcony": None, "safe_room_type": None,
        "description": "דירה יפה ומוארת", "image_urls": ["https://img.example/1.jpg"], "is_delisted": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeSession:
    def __init__(self, listing):
        self._listing = listing

    def get(self, model, pk):
        return self._listing if self._listing is not None and self._listing.id == pk else None

    def expunge(self, obj):
        pass

    def scalar(self, stmt):
        return None

    def execute(self, stmt):
        return SimpleNamespace(first=lambda: None)


@contextmanager
def _patched(listing):
    session = _FakeSession(listing)

    @contextmanager
    def _get_session():
        yield session

    with (
        patch.object(website_main, "get_session", _get_session),
        patch.object(website_main.activity, "record", lambda *a, **k: None),
    ):
        yield


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_token_round_trip_and_forgery():
    token = share.share_token(7)
    assert share.listing_id_from_token(token) == 7
    assert share.listing_id_from_token("8-" + token.split("-")[1]) is None
    assert share.listing_id_from_token("7") is None
    assert share.listing_id_from_token("abc-def") is None


def test_shared_page_shows_the_flat_without_the_original_ad(client):
    with _patched(_listing()):
        resp = client.get(share.share_path(7))
    assert resp.status_code == 200
    html = resp.text
    assert "דירה בפתח תקווה, 3 חדרים, 4,200 ₪" in html
    assert "דירה יפה ומוארת" in html
    assert "secret-source-url" not in html
    assert "/go/7" not in html
    assert "https://t.me/AmirDirotBot?start=site_share" in html
    assert '<meta property="og:image" content="https://img.example/1.jpg">' in html
    assert resp.headers["X-Robots-Tag"] == "noindex"


def test_unsigned_link_does_not_open_the_flat(client):
    with _patched(_listing()):
        resp = client.get("/s/7-0000000000")
    assert resp.status_code == 404
    assert "דירה יפה ומוארת" not in resp.text
    assert "הדירה כבר לא זמינה" in resp.text


def test_taken_down_flat_says_so(client):
    with _patched(_listing(is_delisted=True)):
        resp = client.get(share.share_path(7))
    assert resp.status_code == 404
    assert "הדירה כבר לא זמינה" in resp.text
    assert "דירה יפה ומוארת" not in resp.text


def test_flat_without_photos_shows_todi_and_the_caption(client):
    with _patched(_listing(image_urls=[], rooms=None)):
        resp = client.get(share.share_path(7))
    assert "todi_detective.jpg" in resp.text
    assert "הדירה עלתה בלי תמונות" in resp.text
    assert "דירה בפתח תקווה, 4,200 ₪" in resp.text


def test_bot_share_button_only_when_turned_on(monkeypatch):
    monkeypatch.delenv("BOT_SHARE_BUTTON", raising=False)
    assert len(cards.listing_keyboard(7, "he").inline_keyboard) == 1
    monkeypatch.setenv("BOT_SHARE_BUTTON", "1")
    rows = cards.listing_keyboard(7, "he").inline_keyboard
    assert len(rows) == 2
    url = rows[1][0].url
    assert url.startswith("https://t.me/share/url?")
    assert "todira.app%2Fs%2F7-" in url


def test_monthly_pass_shows_the_real_saving():
    by_plan = {card["plan"]: card for card in website_main._pass_plan_cards()}
    assert by_plan["pass_7"]["saving"] is None
    assert by_plan["pass_14"]["saving"] == 10
    assert by_plan["pass_30"]["saving"] == 35


def test_home_shows_why_i_built_todira_and_approved_testimonials(client):
    quote = SimpleNamespace(message="מצאתי דירה בזכות הבוט", name="דנה")
    with (
        patch.object(website_main, "_home_testimonials", lambda: [quote]),
        patch.object(website_main, "_home_map_data", lambda: {"by_city": {}, "latest": None, "points": [], "count": 0}),
    ):
        resp = client.get("/")
    assert resp.status_code == 200
    assert "למה הקמתי את טודירה" in resp.text
    assert "מה אומרים עלינו" in resp.text and "מצאתי דירה בזכות הבוט" in resp.text


def test_home_without_testimonials_has_no_empty_section(client):
    with patch.object(website_main, "_home_testimonials", lambda: []):
        resp = client.get("/")
    assert "מה אומרים עלינו" not in resp.text


def test_reviews_page_lists_every_approved_testimonial(client):
    quotes = [SimpleNamespace(message=f"המלצה {i}", name=f"שם {i}") for i in range(9)]
    with patch.object(website_main, "_home_testimonials", lambda limit=6: quotes if limit is None else quotes[:limit]):
        resp = client.get("/reviews?lang=he")
    assert resp.status_code == 200
    assert "מה אומרים על טודירה" in resp.text and "המלצה 8" in resp.text
    assert 'href="/reviews"' in resp.text  # in the menu
    with patch.object(website_main, "_home_testimonials", lambda limit=6: []):
        assert "עוד אין כאן המלצות" in client.get("/reviews?lang=he").text


def test_site_feedback_can_be_offered_for_the_site_only_with_the_tick(monkeypatch):
    import asyncio
    from contextlib import contextmanager

    saved, marked, notes = [], [], []

    class _Session:
        def add(self, row):
            row.id = 41
            saved.append(row)

        def commit(self):
            pass

        def get(self, model, pk):
            return None

    @contextmanager
    def _session():
        yield _Session()

    monkeypatch.setattr(website_main, "get_session", _session)
    monkeypatch.setattr(website_main.testimonials, "mark_public_ok", lambda session, mid: marked.append(mid))
    monkeypatch.setattr(website_main, "_notify_owner_sync", lambda *a: notes.append(a) or False)
    run = website_main._process_contact_message
    asyncio.run(run("רני", "", "מצאתי דירה", "", True, "feedback", True))
    asyncio.run(run("רני", "", "שאלה", "", True, "", True))  # not feedback: the tick means nothing
    asyncio.run(run("רני", "", "מצאתי", "", True, "feedback", False))
    assert marked == [41]
    assert [a[-1] for a in notes] == [True, False, False]

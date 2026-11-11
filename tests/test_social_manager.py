"""2026-11-11 (owner: "build a social media manager"): the daily post on our own Facebook Page and Instagram, and the
instant answer with the link to whoever comments "דירה" there."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))
_spec = importlib.util.spec_from_file_location("website_main_social", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

import social_poster
from fastapi.testclient import TestClient
from todira_common import meta_api, social_replies

UTC = dt.timezone.utc


def _keys(monkeypatch, **extra):
    values = {"META_PAGE_ID": "111", "META_PAGE_TOKEN": "page-token", "META_APP_SECRET": "app-secret",
              "META_VERIFY_TOKEN": "verify-me", **extra}
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _signed(body: bytes) -> dict:
    return {"X-Hub-Signature-256": "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest(),
            "Content-Type": "application/json"}


def test_comments_asking_for_the_link_are_recognised():
    for text in ("דירה", "דירה!", "אני חולון", "מעוניינת", "אשמח לקישור", "דירות ברמת גן?"):
        assert social_replies.asks_for_link(text), text
    for text in ("איזה יופי", "מחירים מטורפים", "", None):
        assert not social_replies.asks_for_link(text), text


def test_the_reply_carries_the_link_the_city_and_no_dash():
    replies = {social_replies.reply_text(str(n), "אני חולון", "fb_comment") for n in range(40)}
    assert len(replies) > 5
    for reply in replies:
        assert reply.endswith("https://todira.app/?src=fb_comment") and " בחולון" in reply
        assert "—" not in reply and "–" not in reply and "@" not in reply


def test_the_webhook_subscription_is_confirmed_only_with_our_token(monkeypatch):
    _keys(monkeypatch)
    client = TestClient(website_main.app)
    ok = client.get("/meta/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/meta/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_an_unsigned_call_is_refused(monkeypatch):
    _keys(monkeypatch)
    client = TestClient(website_main.app)
    assert client.post("/meta/webhook", content=b"{}", headers={"X-Hub-Signature-256": "sha256=00"}).status_code == 403


def test_a_page_comment_asking_for_the_link_is_answered_once(monkeypatch):
    _keys(monkeypatch)
    flags: dict = {}
    sent = []

    @contextmanager
    def fake_session():
        yield SimpleNamespace()

    monkeypatch.setattr(website_main, "get_session", fake_session)
    monkeypatch.setattr(social_replies, "get_flag", lambda _s, key: flags.get(key))
    monkeypatch.setattr(social_replies, "set_flag", lambda _s, key, value: flags.__setitem__(key, value))
    monkeypatch.setattr(meta_api, "reply_to_page_comment", lambda cid, text: sent.append((cid, text)))
    payload = {"object": "page", "entry": [{"changes": [
        {"field": "feed", "value": {"item": "comment", "verb": "add", "comment_id": "c1", "message": "דירה בבת ים",
                                    "from": {"id": "999"}}},
        {"field": "feed", "value": {"item": "comment", "verb": "add", "comment_id": "c2", "message": "יפה",
                                    "from": {"id": "998"}}},
        {"field": "feed", "value": {"item": "comment", "verb": "add", "comment_id": "c3", "message": "דירה",
                                    "from": {"id": "111"}}},  # our own Page: never answered
    ]}]}
    body = json.dumps(payload).encode()
    client = TestClient(website_main.app)
    assert client.post("/meta/webhook", content=body, headers=_signed(body)).status_code == 200
    assert client.post("/meta/webhook", content=body, headers=_signed(body)).status_code == 200  # Meta retries
    assert [cid for cid, _ in sent] == ["c1"]
    assert "בבת ים" in sent[0][1] and sent[0][1].endswith("?src=fb_comment")


def test_nothing_is_answered_or_posted_without_the_keys(monkeypatch):
    for name in ("META_PAGE_ID", "META_PAGE_TOKEN", "META_IG_USER_ID"):
        monkeypatch.delenv(name, raising=False)
    assert not meta_api.page_enabled() and not meta_api.instagram_enabled()
    assert social_poster.run_social_poster(SimpleNamespace(), dt.datetime(2026, 11, 11, 8, 30, tzinfo=UTC)) == {}


def test_the_daily_post_goes_out_once_in_the_morning():
    morning = dt.datetime(2026, 11, 11, 8, 30, tzinfo=UTC)  # 10:30 in Israel
    assert social_poster.due(None, morning) == "2026-11-11"
    assert social_poster.due("2026-11-11", morning) is None
    assert social_poster.due(None, dt.datetime(2026, 11, 11, 12, 0, tzinfo=UTC)) is None  # 14:00 in Israel


def test_the_daily_post_reaches_the_page_then_instagram(monkeypatch):
    _keys(monkeypatch, META_IG_USER_ID="222")
    flags: dict = {}
    monkeypatch.setattr(social_poster.app_flags, "get_flag", lambda _s, key: flags.get(key))
    monkeypatch.setattr(social_poster.app_flags, "set_flag", lambda _s, key, value: flags.__setitem__(key, value))
    monkeypatch.setattr(social_poster, "todays_post", lambda _s, _now: ([b"png"], "כתבו \"דירה\" בתגובות"))
    posted = []
    monkeypatch.setattr(meta_api, "publish_page_photos", lambda pngs, caption: posted.append("fb") or ("p1", ["https://x/1.jpg"]))
    monkeypatch.setattr(meta_api, "publish_instagram", lambda urls, caption: posted.append(("ig", urls)) or "m1")
    morning = dt.datetime(2026, 11, 11, 8, 30, tzinfo=UTC)
    result = social_poster.run_social_poster(SimpleNamespace(), morning)
    assert result == {"social_post": "2026-11-11", "social_facebook": "ok", "social_instagram": "ok"}
    assert posted == ["fb", ("ig", ["https://x/1.jpg"])]
    assert social_poster.run_social_poster(SimpleNamespace(), morning) == {}  # once a day


def test_every_caption_asks_for_a_comment_and_names_no_source():
    assert "דירה" in social_poster.ASK
    for text in (social_poster.ASK, social_poster.HASHTAGS):
        assert "—" not in text and "–" not in text and "פייסבוק" not in text

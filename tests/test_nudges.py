"""2026-11-08: the occasional Telegram messages (scraper/nudges.py)."""
from __future__ import annotations

import datetime as dt
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import nudges
from todira_common import alert_hours
from todira_common.bot_strings import bot_text


def _israel(day: str, hour: int) -> dt.datetime:
    return dt.datetime.fromisoformat(f"{day}T{hour:02d}:10").replace(tzinfo=alert_hours.ISRAEL).astimezone(dt.timezone.utc)


def _user(now, **kw):
    base = {
        "id": 7, "telegram_user_id": 70, "created_at": now - dt.timedelta(days=3),
        "trial_ends_at": now + dt.timedelta(days=7), "paid_until": None, "free_access_granted": False,
        "alert_from_hour": None, "alert_to_hour": None, "language": "he", "is_active": True, "notifications_enabled": True,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _counts(monkeypatch, new, drops=0):
    monkeypatch.setattr(nudges, "_counts", lambda session, uid, since: (new, drops))


SUNDAY, MONDAY = "2026-11-08", "2026-11-09"


def test_trial_day_three_gets_one_tip_about_hours_first(monkeypatch):
    now = _israel(MONDAY, 10)
    _counts(monkeypatch, 10)
    assert nudges.pick(None, _user(now), {}, now) == ("tip_hours", {})
    assert nudges.pick(None, _user(now, alert_from_hour=9, alert_to_hour=20), {}, now) == ("tip_invite", {})
    assert nudges.pick(None, _user(now), {"7": {"done": ["tip"]}}, now) is None


def test_no_tip_before_the_third_day(monkeypatch):
    now = _israel(MONDAY, 10)
    _counts(monkeypatch, 10)
    assert nudges.pick(None, _user(now, created_at=now - dt.timedelta(days=1)), {}, now) is None


def test_price_two_days_before_the_trial_ends(monkeypatch):
    now = _israel(MONDAY, 10)
    _counts(monkeypatch, 12)
    kind, args = nudges.pick(None, _user(now, trial_ends_at=now + dt.timedelta(hours=40)), {}, now)
    assert kind == "price" and args["count"] == 12 and args["per_day"] == "1.66"
    _counts(monkeypatch, 1)  # got almost nothing: no price message, the tip instead
    assert nudges.pick(None, _user(now, trial_ends_at=now + dt.timedelta(hours=40)), {}, now)[0] == "tip_hours"


def test_one_a_week_and_off_means_never(monkeypatch):
    now = _israel(MONDAY, 10)
    _counts(monkeypatch, 10)
    recent = {"7": {"last": (now - dt.timedelta(days=3)).isoformat()}}
    assert nudges.pick(None, _user(now), recent, now) is None
    assert nudges.pick(None, _user(now), {"7": {"off": True}}, now) is None


def test_weekly_on_sunday_for_paying_people_only_with_enough_flats(monkeypatch):
    now = _israel(SUNDAY, 10)
    paying = _user(now, trial_ends_at=now - dt.timedelta(days=20), paid_until=now + dt.timedelta(days=10))
    _counts(monkeypatch, 23, 4)
    kind, args = nudges.pick(None, paying, {}, now)
    assert kind == "weekly" and args["count"] == 23 and args["drops"] == 4
    assert nudges.pick(None, paying, {"7": {"done": [f"weekly:{args['week']}"]}}, now) is None
    _counts(monkeypatch, 2)
    assert nudges.pick(None, paying, {}, now) is None
    assert nudges.pick(None, paying, {}, _israel(MONDAY, 10)) is None


def test_texts_in_every_language_without_dashes():
    now = _israel(MONDAY, 10)
    user = _user(now)
    for lang in ("he", "en", "ru", "fr", "ar", "es", "pt", "hi", "fil", "th", "zh"):
        for kind, args in (("weekly", {"count": 5, "drops": 0}), ("weekly", {"count": 5, "drops": 2}),
                           ("price", {"count": 9, "price": "49.90", "per_day": "1.66"}), ("tip_hours", {}),
                           ("tip_invite", {})):
            body = nudges.text(kind, user, args, lang)
            assert body and "{" not in body and "—" not in body and "–" not in body
        assert bot_text("nudge.less_btn", lang) and bot_text("nudge.less_done", lang)

"""2026-11-03: one morning message to people whose access ended (scraper/winback.py)."""
from __future__ import annotations

import datetime as dt
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import winback  # noqa: E402

NOW = dt.datetime(2026, 11, 3, 8, tzinfo=dt.timezone.utc)  # 10:00 Israel


def _user(uid, trial_days_ago=5, paid_until=None, active=True, comp=False):
    return SimpleNamespace(
        id=uid, telegram_user_id=1000 + uid, is_active=active, free_access_granted=comp, language="he",
        trial_ends_at=NOW - dt.timedelta(days=trial_days_ago), paid_until=paid_until,
    )


class _Session:
    def __init__(self, users, flats):
        self.users, self.flats = users, flats

    def scalars(self, query):
        return iter(self.users)

    def execute(self, query):
        uid = query.compile().params["user_id_1"]
        return SimpleNamespace(scalar=lambda: self.flats.get(uid, 0))


def test_who_gets_the_message(monkeypatch):
    monkeypatch.setattr(winback, "has_full_access", lambda user: user.trial_ends_at > NOW or bool(
        user.paid_until and user.paid_until > NOW))
    monkeypatch.setattr(winback.alert_hours, "in_window", lambda user, now: user.id != 7)
    monkeypatch.setattr(winback, "_asked_found_lately", lambda session, uid, now: uid == 8)
    users = [
        _user(1),  # ended 5 days ago, 7 flats since: yes
        _user(2, trial_days_ago=3),  # ended 3 days ago: not yet
        _user(3),  # only 2 flats: no
        _user(4, trial_days_ago=-3),  # still on trial
        _user(5, paid_until=NOW + dt.timedelta(days=9)),  # paid
        _user(6),  # already sent for this end
        _user(7),  # outside their own alert hours
        _user(8),  # was just asked "did you find a flat?"
    ]
    flats = {1: 7, 2: 9, 3: 2, 6: 8, 7: 9, 8: 9}
    sent = {"6": users[5].trial_ends_at.isoformat()}
    due = winback.due_users(_Session(users, flats), NOW, sent)
    assert [(u.id, n) for u, _, n in due] == [(1, 7)]


def test_the_message_counts_and_links_the_upgrade_page(monkeypatch):
    monkeypatch.setattr(winback, "signed_login_query", lambda tid: "t=x")
    text = winback.message(_user(1), NOW - dt.timedelta(days=5), 7)
    assert "29.10" in text and "7 דירות" in text and "https://todira.app/upgrade?t=x" in text
    assert "—" not in text and "–" not in text


def test_access_end_is_the_later_of_trial_and_paid():
    user = _user(1, paid_until=NOW - dt.timedelta(days=1))
    assert winback.access_end(user) == NOW - dt.timedelta(days=1)

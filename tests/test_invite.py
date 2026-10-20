"""2026-10-20 (owner): whoever brings a friend gets 5 more days of full access."""
from __future__ import annotations

import datetime as dt
import os
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from todira_common import invite  # noqa: E402

NOW = dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.timezone.utc)


class _Session:
    def __init__(self, users):
        self.users, self.flags = {u.id: u for u in users}, {}

    def get(self, model, key):
        return self.users.get(key)


def _user(uid, **kw):
    values = dict(id=uid, created_at=NOW - dt.timedelta(days=3), trial_ends_at=NOW + dt.timedelta(days=2), paid_until=None)
    values.update(kw)
    return SimpleNamespace(**values)


def _patch_flags(monkeypatch, session):
    monkeypatch.setattr(invite, "get_flag", lambda s, key: session.flags.get(key))
    monkeypatch.setattr(invite, "set_flag", lambda s, key, value: session.flags.__setitem__(key, value))


def test_a_link_names_its_owner_and_cannot_be_forged():
    code = invite.invite_code(42)
    assert code.startswith("inv_42_") and len(code) <= 64
    assert invite.inviter_id(code) == 42
    assert invite.inviter_id("inv_43_" + code.split("_")[2]) is None  # someone else's id with this signature
    assert invite.inviter_id("inv_42_nope") is None and invite.inviter_id("ref_abc") is None and invite.inviter_id(None) is None


def test_a_new_friend_adds_five_days_to_the_trial(monkeypatch):
    inviter, friend = _user(1), _user(2, created_at=NOW - dt.timedelta(seconds=5))
    session = _Session([inviter, friend])
    _patch_flags(monkeypatch, session)
    assert invite.apply_invite(session, friend, invite.invite_code(1), NOW) is inviter
    assert inviter.trial_ends_at == NOW + dt.timedelta(days=7)
    assert invite.apply_invite(session, friend, invite.invite_code(1), NOW) is None  # once per friend
    assert inviter.trial_ends_at == NOW + dt.timedelta(days=7)


def test_a_paying_inviter_gets_the_days_on_the_paid_period(monkeypatch):
    inviter = _user(1, paid_until=NOW + dt.timedelta(days=20))
    friend = _user(2, created_at=NOW)
    session = _Session([inviter, friend])
    _patch_flags(monkeypatch, session)
    invite.apply_invite(session, friend, invite.invite_code(1), NOW)
    assert inviter.paid_until == NOW + dt.timedelta(days=25)


def test_an_ended_trial_gets_five_days_from_today(monkeypatch):
    inviter = _user(1, trial_ends_at=NOW - dt.timedelta(days=10))
    friend = _user(2, created_at=NOW)
    session = _Session([inviter, friend])
    _patch_flags(monkeypatch, session)
    invite.apply_invite(session, friend, invite.invite_code(1), NOW)
    assert inviter.trial_ends_at == NOW + dt.timedelta(days=5)


def test_an_existing_user_or_yourself_earns_nothing(monkeypatch):
    inviter = _user(1)
    old_friend = _user(2)  # registered days ago
    session = _Session([inviter, old_friend])
    _patch_flags(monkeypatch, session)
    assert invite.apply_invite(session, old_friend, invite.invite_code(1), NOW) is None
    me = _user(3, created_at=NOW)
    assert invite.apply_invite(_Session([me]), me, invite.invite_code(3), NOW) is None
    assert inviter.trial_ends_at == NOW + dt.timedelta(days=2)

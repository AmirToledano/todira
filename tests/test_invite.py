"""2026-10-20 (owner): whoever brings a friend gets 5 more days of full access; since 2026-10-21 only once the\nfriend pays (the friend keeps the regular free trial)."""
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


def _invited(monkeypatch, inviter, friend):
    session = _Session([inviter, friend])
    _patch_flags(monkeypatch, session)
    assert invite.record_invite(session, friend, invite.invite_code(inviter.id), NOW) == inviter.id
    return session


def test_joining_through_a_link_gives_the_inviter_nothing_yet(monkeypatch):
    inviter, friend = _user(1), _user(2, created_at=NOW - dt.timedelta(seconds=5))
    session = _invited(monkeypatch, inviter, friend)
    assert inviter.trial_ends_at == NOW + dt.timedelta(days=2)
    assert invite.record_invite(session, friend, invite.invite_code(1), NOW) is None  # once per friend


def test_the_friends_first_payment_adds_five_days_once(monkeypatch):
    inviter, friend = _user(1), _user(2, created_at=NOW)
    session = _invited(monkeypatch, inviter, friend)
    assert invite.reward_for_payment(session, friend, NOW) is inviter
    assert inviter.trial_ends_at == NOW + dt.timedelta(days=7)
    assert invite.reward_for_payment(session, friend, NOW) is None  # a renewal earns nothing more
    assert inviter.trial_ends_at == NOW + dt.timedelta(days=7)


def test_a_paying_inviter_gets_the_days_on_the_paid_period(monkeypatch):
    inviter, friend = _user(1, paid_until=NOW + dt.timedelta(days=20)), _user(2, created_at=NOW)
    session = _invited(monkeypatch, inviter, friend)
    invite.reward_for_payment(session, friend, NOW)
    assert inviter.paid_until == NOW + dt.timedelta(days=25)


def test_an_ended_trial_gets_five_days_from_today(monkeypatch):
    inviter, friend = _user(1, trial_ends_at=NOW - dt.timedelta(days=10)), _user(2, created_at=NOW)
    session = _invited(monkeypatch, inviter, friend)
    invite.reward_for_payment(session, friend, NOW)
    assert inviter.trial_ends_at == NOW + dt.timedelta(days=5)


def test_a_payer_nobody_invited_earns_nobody_anything(monkeypatch):
    payer = _user(2)
    session = _Session([payer])
    _patch_flags(monkeypatch, session)
    assert invite.reward_for_payment(session, payer, NOW) is None


def test_an_existing_user_or_yourself_is_not_a_new_friend(monkeypatch):
    inviter, old_friend = _user(1), _user(2)  # registered days ago
    session = _Session([inviter, old_friend])
    _patch_flags(monkeypatch, session)
    assert invite.record_invite(session, old_friend, invite.invite_code(1), NOW) is None
    me = _user(3, created_at=NOW)
    assert invite.record_invite(_Session([me]), me, invite.invite_code(3), NOW) is None


def test_the_website_tells_the_inviter_after_the_friends_payment(monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "website"))
    spec = importlib.util.spec_from_file_location("website_main_invite", root / "website" / "main.py")
    site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(site)

    inviter = _user(1, telegram_user_id=111, language="he")
    sent = []
    monkeypatch.setattr(site, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(site.invite, "reward_for_payment", lambda session, payer, now: inviter)
    monkeypatch.setattr(site.httpx, "post", lambda url, json, timeout: sent.append(json))
    site._reward_inviter_after_payment(object(), _user(2))
    assert sent and sent[0]["chat_id"] == 111 and "5" in sent[0]["text"]

    monkeypatch.setattr(site.invite, "reward_for_payment", lambda session, payer, now: None)
    site._reward_inviter_after_payment(object(), _user(3))
    assert len(sent) == 1

"""Tests for the website's real login (website/main.py): the Telegram Login Widget callback,
its HMAC signature verification, the session-vs-?uid= resolution order, and /auth/logout.

Same importlib-loading approach as test_website_contact.py (see that file's comment) — website/
main.py shares a basename with scraper/main.py so it can't go through a bare `import main`.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_auth", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_BOT_TOKEN = "test-bot-token"


def _signed_params(**overrides) -> dict:
    params = {
        "id": "123456",
        "first_name": "Amir",
        "username": "amirt",
        "auth_date": str(int(time.time())),
    }
    params.update(overrides)
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hashlib.sha256(_BOT_TOKEN.encode()).digest()
    params["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return params


class _FakeUser:
    def __init__(self, id: int, telegram_user_id: int):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.filter = None
        self.first_name = "Amir"
        self.telegram_username = "amirt"
        # has_full_access() reads these — /apartments computes has_access for the listing cards.
        self.free_access_granted = False
        self.trial_ends_at = None
        self.paid_until = None
        self.language = None


class _FakeSession:
    def __init__(self, users_by_telegram_id=None, users_by_pk=None):
        self._by_telegram_id = users_by_telegram_id or {}
        self._by_pk = users_by_pk or {}

    def scalar(self, stmt):
        for user in self._by_telegram_id.values():
            return user
        return None

    def scalars(self, stmt):
        class _Scalars:
            def all(self):
                return []

        return _Scalars()

    def execute(self, stmt):
        class _Result:
            def first(self):
                return None

        return _Result()

    def get(self, model, pk):
        return self._by_pk.get(pk)


@pytest.fixture
def client():
    with patch.object(website_main, "TELEGRAM_BOT_TOKEN", _BOT_TOKEN):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_verify_telegram_auth_accepts_valid_signature():
    params = _signed_params()
    assert website_main._verify_telegram_auth(params, _BOT_TOKEN) is True


def test_verify_telegram_auth_rejects_tampered_field():
    params = _signed_params()
    params["first_name"] = "Someone Else"
    assert website_main._verify_telegram_auth(params, _BOT_TOKEN) is False


def test_verify_telegram_auth_rejects_wrong_bot_token():
    params = _signed_params()
    assert website_main._verify_telegram_auth(params, "a-different-bot-token") is False


def test_verify_telegram_auth_rejects_stale_auth_date():
    params = _signed_params(auth_date=str(int(time.time()) - 60 * 60 * 24 * 2))
    assert website_main._verify_telegram_auth(params, _BOT_TOKEN) is False


def test_verify_telegram_auth_rejects_missing_hash():
    params = _signed_params()
    del params["hash"]
    assert website_main._verify_telegram_auth(params, _BOT_TOKEN) is False


def test_callback_rejects_invalid_signature(client):
    resp = client.get("/auth/telegram/callback", params={"id": "1", "hash": "bogus", "auth_date": "1"})
    assert resp.status_code == 400


def test_callback_unknown_telegram_id_redirects_to_bot(client):
    user = _FakeUser(id=1, telegram_user_id=999999)
    fake_session = _FakeSession(users_by_telegram_id={}, users_by_pk={1: user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    params = _signed_params(id="424242")
    with patch.object(website_main, "get_session", _fake_get_session):
        resp = client.get("/auth/telegram/callback", params=params)

    assert resp.status_code == 303
    assert resp.headers["location"] == "https://t.me/AmirDirotBot"


def test_callback_known_user_sets_session_and_redirects(client):
    user = _FakeUser(id=7, telegram_user_id=123456)
    fake_session = _FakeSession(users_by_telegram_id={123456: user}, users_by_pk={7: user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    params = _signed_params(id="123456")
    with patch.object(website_main, "get_session", _fake_get_session):
        resp = client.get("/auth/telegram/callback", params=params)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/apartments"
    assert client.cookies.get("session") is not None


def test_callback_respects_safe_next_param(client):
    user = _FakeUser(id=7, telegram_user_id=123456)
    fake_session = _FakeSession(users_by_telegram_id={123456: user}, users_by_pk={7: user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    params = _signed_params(id="123456")
    with patch.object(website_main, "get_session", _fake_get_session):
        resp = client.get("/auth/telegram/callback", params={**params, "next": "/liked"})

    assert resp.headers["location"] == "/liked"


def test_callback_rejects_open_redirect_next_param(client):
    user = _FakeUser(id=7, telegram_user_id=123456)
    fake_session = _FakeSession(users_by_telegram_id={123456: user}, users_by_pk={7: user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    params = _signed_params(id="123456")
    with patch.object(website_main, "get_session", _fake_get_session):
        resp = client.get(
            "/auth/telegram/callback", params={**params, "next": "//evil.example.com"}
        )

    assert resp.headers["location"] == "/apartments"


def test_logout_clears_session_and_redirects_home(client):
    resp = client.get("/auth/logout")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_resolve_user_prefers_session_over_uid_param():
    class _FakeRequest:
        session = {"user_id": 7}
        query_params: dict = {}

    session_user = _FakeUser(id=7, telegram_user_id=123456)
    uid_user = _FakeUser(id=99, telegram_user_id=555)
    fake_session = _FakeSession(
        users_by_telegram_id={555: uid_user}, users_by_pk={7: session_user}
    )

    result = website_main._resolve_user(_FakeRequest(), fake_session, 555)
    assert result is session_user


def test_resolve_user_never_trusts_a_bare_uid_param():
    """2026-10-02 security: a Telegram id is public knowledge; ?uid=<id> alone must not log anyone in."""
    class _FakeRequest:
        session: dict = {}
        query_params: dict = {}

    uid_user = _FakeUser(id=99, telegram_user_id=555)
    fake_session = _FakeSession(users_by_telegram_id={555: uid_user}, users_by_pk={})

    assert website_main._resolve_user(_FakeRequest(), fake_session, 555) is None


def test_resolve_user_accepts_a_valid_signed_token_and_signs_the_session_in():
    from todira_common.uid_token import generate_uid_token

    class _FakeRequest:
        session: dict = {}
        query_params = {"t": generate_uid_token(555)}

    uid_user = _FakeUser(id=99, telegram_user_id=555)
    fake_session = _FakeSession(users_by_telegram_id={555: uid_user}, users_by_pk={})
    request = _FakeRequest()

    assert website_main._resolve_user(request, fake_session, None) is uid_user
    assert request.session["user_id"] == 99


def test_resolve_user_rejects_a_forged_or_tampered_token():
    from todira_common.uid_token import generate_uid_token

    # Tamper with the FIRST character of the signature: the last characters of a base64 value can carry unused bits, so
    # altering only those left the signature valid about one run in sixteen (a flaky failure seen 2026-10-07).
    token = generate_uid_token(555)
    head, _, signature = token.rpartition(".")
    tampered = f"{head}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"

    class _FakeRequest:
        session: dict = {}
        query_params = {"t": tampered}

    uid_user = _FakeUser(id=99, telegram_user_id=555)
    fake_session = _FakeSession(users_by_telegram_id={555: uid_user}, users_by_pk={})

    assert website_main._resolve_user(_FakeRequest(), fake_session, 555) is None


def test_resolve_user_token_wins_over_an_existing_session_for_a_different_account():
    """Tapping a bot link must land on the account that link belongs to, even if this browser was
    signed in as someone else."""
    from todira_common.uid_token import generate_uid_token

    class _FakeRequest:
        session = {"user_id": 7}
        query_params = {"t": generate_uid_token(555)}

    session_user = _FakeUser(id=7, telegram_user_id=123456)
    token_user = _FakeUser(id=99, telegram_user_id=555)
    fake_session = _FakeSession(users_by_telegram_id={555: token_user}, users_by_pk={7: session_user})
    request = _FakeRequest()

    assert website_main._resolve_user(request, fake_session, None) is token_user
    assert request.session["user_id"] == 99


def test_a_token_for_one_user_cannot_be_reused_as_another_users_token():
    from todira_common.uid_token import generate_uid_token, verify_uid_token

    assert verify_uid_token(generate_uid_token(555)) == 555
    assert verify_uid_token("555") is None
    assert verify_uid_token("") is None


def test_resolve_user_returns_none_when_nothing_matches():
    class _FakeRequest:
        session: dict = {}
        query_params: dict = {}

    fake_session = _FakeSession()
    assert website_main._resolve_user(_FakeRequest(), fake_session, None) is None


class _FakeFilter:
    deal_type = None
    cities: list[str] = []


def test_apartments_hides_insecure_notice_when_reached_via_real_session(client):
    """Regression test for a real bug caught manually: after a genuine Telegram Login, /apartments
    was still showing the "temporary, not fully secure" banner meant for the legacy ?uid= link,
    because the notice wasn't conditioned on how the user actually got authenticated."""
    user = _FakeUser(id=7, telegram_user_id=123456)
    user.filter = _FakeFilter()
    fake_session = _FakeSession(users_by_telegram_id={123456: user}, users_by_pk={7: user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session), patch.object(
        website_main, "evaluate", return_value=type("Result", (), {"matched": False})()
    ):
        callback_params = _signed_params(id="123456")
        login_resp = client.get("/auth/telegram/callback", params=callback_params)
        assert login_resp.status_code == 303  # real login succeeded, session cookie now set

        resp = client.get("/apartments")

    assert resp.status_code == 200
    assert "לא מאובטח" not in resp.text


@pytest.mark.no_uid_shim
def test_apartments_with_a_bare_uid_shows_the_sign_in_page_not_the_users_apartments(client):
    user = _FakeUser(id=7, telegram_user_id=123456)
    user.filter = _FakeFilter()
    fake_session = _FakeSession(users_by_telegram_id={123456: user}, users_by_pk={})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    with patch.object(website_main, "get_session", _fake_get_session):
        resp = client.get("/apartments", params={"uid": 123456})

    assert resp.status_code == 200
    assert "לא מאובטח" not in resp.text
    assert "טודירה" in resp.text  # a real page rendered (need_uid.html), not a crash
    assert "data-listing-id" not in resp.text  # none of the user's listings were rendered


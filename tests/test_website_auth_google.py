"""Tests for the website's Google Sign-In (website/main.py's /auth/google/start +
/auth/google/callback): the redirect to Google, CSRF state verification, the linking flow (a
visitor viewing a page via their own ?uid= gets their Google account linked to that same user),
and normal returning-user sign-in via an already-linked google_sub.

Same importlib-loading approach as test_website_auth.py (see that file's comment) — website/
main.py shares a basename with scraper/main.py so it can't go through a bare `import main`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_auth_google", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_CLIENT_ID = "test-client-id"
_CLIENT_SECRET = "test-client-secret"


class _FakeUser:
    def __init__(self, id: int, telegram_user_id: int | None = None, google_sub: str | None = None):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.google_sub = google_sub
        self.first_name = "Amir"
        self.telegram_username = "amirtest"


class _FakeSession:
    """`scalar()` returns queued results in call order — matches the exact sequence
    auth_google_callback makes: (1) lookup by google_sub, (2) if unlinked + a uid is being linked,
    lookup by telegram_user_id via _get_user_by_uid. At most 2 calls per request.

    `users_by_pk` backs the third fallback path — session.get(User, session_user_id) — used when
    the visitor already has an authenticated session but no usable link_uid."""

    def __init__(self, scalar_results, users_by_pk: dict | None = None):
        self._scalar_results = list(scalar_results)
        self._users_by_pk = users_by_pk or {}
        self.committed = False
        self.added: list = []

    def scalar(self, stmt):
        return self._scalar_results.pop(0) if self._scalar_results else None

    def add(self, obj):
        # Backs generate_google_link_token's PendingGoogleLink insert, called whenever the
        # callback ends up on the "we don't recognize this account" path.
        self.added.append(obj)

    def get(self, model, pk):
        return self._users_by_pk.get(pk)

    def execute(self, stmt):
        # Backs base.html's header lookup (_current_user_summary) when google_pending.html
        # renders for an already-authenticated session — only the users_by_pk seed matters here.
        class _Result:
            def __init__(self, row):
                self._row = row

            def first(self):
                return self._row

        user = next(iter(self._users_by_pk.values()), None)
        return _Result(user)

    def commit(self):
        self.committed = True


@pytest.fixture
def client():
    with patch.object(website_main, "GOOGLE_CLIENT_ID", _CLIENT_ID), patch.object(
        website_main, "GOOGLE_CLIENT_SECRET", _CLIENT_SECRET
    ), patch.object(website_main, "WEBSITE_URL", "https://todira.duckdns.org"):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_start_redirects_to_google_with_expected_params(client):
    resp = client.get("/auth/google/start")
    assert resp.status_code == 303
    location = urlparse(resp.headers["location"])
    assert location.netloc == "accounts.google.com"
    params = parse_qs(location.query)
    assert params["client_id"] == [_CLIENT_ID]
    assert params["redirect_uri"] == ["https://todira.duckdns.org/auth/google/callback"]
    assert params["response_type"] == ["code"]
    assert "state" in params


def test_start_without_client_id_configured_returns_400():
    with patch.object(website_main, "GOOGLE_CLIENT_ID", None):
        c = TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)
        resp = c.get("/auth/google/start")
    assert resp.status_code == 400


def test_callback_rejects_missing_state(client):
    resp = client.get("/auth/google/callback", params={"code": "abc"})
    assert resp.status_code == 400


def test_callback_rejects_mismatched_state(client):
    client.get("/auth/google/start")  # seeds the real oauth_state in the session cookie
    resp = client.get("/auth/google/callback", params={"code": "abc", "state": "wrong-state"})
    assert resp.status_code == 400


def test_callback_rejects_google_error_param(client):
    start_resp = client.get("/auth/google/start")
    state = parse_qs(urlparse(start_resp.headers["location"]).query)["state"][0]
    resp = client.get(
        "/auth/google/callback", params={"error": "access_denied", "state": state}
    )
    assert resp.status_code == 400


def _do_start(client, **start_params):
    start_resp = client.get("/auth/google/start", params=start_params)
    state = parse_qs(urlparse(start_resp.headers["location"]).query)["state"][0]
    return state


def _mock_google_exchange(google_sub: str):
    def _fake_request(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "fake-access-token"})
        if request.url.host == "openidconnect.googleapis.com":
            return httpx.Response(200, json={"sub": google_sub})
        raise AssertionError(f"unexpected request to {request.url}")

    return httpx.MockTransport(_fake_request)


def test_callback_known_google_sub_signs_in_directly(client):
    state = _do_start(client)
    user = _FakeUser(id=7, google_sub="google-sub-123")
    fake_session = _FakeSession(scalar_results=[user])

    @contextmanager
    def _fake_get_session():
        yield fake_session

    transport = _mock_google_exchange("google-sub-123")
    with patch.object(website_main, "get_session", _fake_get_session), patch.object(
        httpx, "post", lambda url, **kw: httpx.Client(transport=transport).post(url, **kw)
    ), patch.object(
        httpx, "get", lambda url, **kw: httpx.Client(transport=transport).get(url, **kw)
    ):
        resp = client.get("/auth/google/callback", params={"code": "abc", "state": state})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/apartments"
    assert client.cookies.get("session") is not None


def test_callback_links_google_to_the_uid_being_viewed(client):
    """The valuable case: a visitor viewing a page via their own ?uid= deep link signs in with
    Google for the first time — their Google account gets LINKED to that same existing user, not
    turned into a new/separate account."""
    state = _do_start(client, uid=123456)
    existing_user = _FakeUser(id=7, telegram_user_id=123456, google_sub=None)
    # First scalar() (lookup by google_sub) finds nobody yet; second (lookup by uid, inside
    # _get_user_by_uid) finds the existing Telegram-created user.
    fake_session = _FakeSession(scalar_results=[None, existing_user])

    @contextmanager
    def _fake_get_session():
        yield fake_session

    transport = _mock_google_exchange("google-sub-new")
    with patch.object(website_main, "get_session", _fake_get_session), patch.object(
        httpx, "post", lambda url, **kw: httpx.Client(transport=transport).post(url, **kw)
    ), patch.object(
        httpx, "get", lambda url, **kw: httpx.Client(transport=transport).get(url, **kw)
    ):
        resp = client.get("/auth/google/callback", params={"code": "abc", "state": state})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/apartments"
    assert existing_user.google_sub == "google-sub-new"
    assert fake_session.committed is True


def test_callback_unlinked_google_account_with_no_uid_shows_pending_link_page(client):
    """2026-09-05 fix: this used to bounce straight to the bot with no way back — a real dead
    end, since the plain header "Sign in with Google" button (shown whenever there's no uid in
    the URL) could then never succeed for a first-time linker. Now it stashes the google_sub in
    the session and explains what to do instead; see test_resolve_user_completes_pending_google_
    link_once_a_real_uid_shows_up below for the other half of the fix."""
    state = _do_start(client)  # no uid — nothing to link to right now
    fake_session = _FakeSession(scalar_results=[None])

    @contextmanager
    def _fake_get_session():
        yield fake_session

    transport = _mock_google_exchange("google-sub-unknown")
    with patch.object(website_main, "get_session", _fake_get_session), patch.object(
        httpx, "post", lambda url, **kw: httpx.Client(transport=transport).post(url, **kw)
    ), patch.object(
        httpx, "get", lambda url, **kw: httpx.Client(transport=transport).get(url, **kw)
    ):
        resp = client.get("/auth/google/callback", params={"code": "abc", "state": state})

    assert resp.status_code == 200
    assert "פתח את הבוט" in resp.text
    assert client.cookies.get("session") is not None
    # 2026-09-05: the bot link now carries a google_link_token (dorin_common/google_link.py) so
    # the link completes on /start regardless of which browser/app the visitor ends up in — not
    # just the plain, no-payload bot link this page used to show.
    assert 'href="https://t.me/AmirDirotBot?start=gl_' in resp.text
    assert len(fake_session.added) == 1
    assert fake_session.added[0].google_sub == "google-sub-unknown"


def test_resolve_user_completes_pending_google_link_once_a_real_uid_shows_up():
    """The other half of the fix: once a browser holding a pending_google_sub (from the test
    above) later resolves a real uid — e.g. the visitor opened the bot and came back via any
    ?uid= link — _resolve_user finishes the link AND starts a real session right there, so they
    never have to repeat the Google sign-in."""
    from starlette.requests import Request as StarletteRequest

    user = _FakeUser(id=7, telegram_user_id=123456, google_sub=None)
    fake_session = _FakeSession(scalar_results=[user])

    scope = {
        "type": "http",
        "session": {"pending_google_sub": "google-sub-unknown"},
    }
    request = StarletteRequest(scope)

    result = website_main._resolve_user(request, fake_session, 123456)

    assert result is user
    assert user.google_sub == "google-sub-unknown"
    assert fake_session.committed is True
    assert request.session.get("pending_google_sub") is None
    assert request.session.get("user_id") == 7


def test_resolve_user_leaves_a_plain_uid_visit_unaffected_with_no_pending_link():
    """No pending_google_sub in the session at all — the overwhelmingly common case (any normal
    bot deep-link visit) — must stay exactly as low-trust/ephemeral as before: no session
    established, no DB write."""
    from starlette.requests import Request as StarletteRequest

    user = _FakeUser(id=7, telegram_user_id=123456, google_sub=None)
    fake_session = _FakeSession(scalar_results=[user])

    request = StarletteRequest({"type": "http", "session": {}})
    result = website_main._resolve_user(request, fake_session, 123456)

    assert result is user
    assert user.google_sub is None
    assert fake_session.committed is False
    assert request.session.get("user_id") is None


def test_callback_links_google_to_already_authenticated_session():
    """2026-09-05 fix: a visitor who already has an authenticated session (session["user_id"] —
    e.g. from an earlier Telegram login, or an earlier Google attempt in this same browser) but
    whose *this* callback carries no usable link_uid (the "קשר את Google לחשבון" link can be
    rendered before Telegram finishes linking, or the uid param can otherwise get lost) must
    still get the new Google account linked to that session's user — not stranded on the
    pending-link page while the header plainly shows them as already logged in."""
    from starlette.requests import Request as StarletteRequest

    existing_user = _FakeUser(id=42, telegram_user_id=555, google_sub=None)
    fake_session = _FakeSession(scalar_results=[None], users_by_pk={42: existing_user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    transport = _mock_google_exchange("google-sub-new-2")
    scope = {"type": "http", "session": {"oauth_state": "abc", "user_id": 42}}
    request = StarletteRequest(scope)

    with patch.object(website_main, "GOOGLE_CLIENT_ID", _CLIENT_ID), patch.object(
        website_main, "GOOGLE_CLIENT_SECRET", _CLIENT_SECRET
    ), patch.object(website_main, "get_session", _fake_get_session), patch.object(
        httpx, "post", lambda url, **kw: httpx.Client(transport=transport).post(url, **kw)
    ), patch.object(
        httpx, "get", lambda url, **kw: httpx.Client(transport=transport).get(url, **kw)
    ):
        resp = website_main.auth_google_callback(request, code="abc", state="abc")

    assert resp.status_code == 303
    assert resp.headers["location"] == "/apartments"
    assert existing_user.google_sub == "google-sub-new-2"
    assert fake_session.committed is True
    assert request.session.get("user_id") == 42


def test_callback_does_not_overwrite_an_already_linked_session_users_google_account():
    """The already-authenticated session's user is already linked to a DIFFERENT Google
    account — this callback's new google_sub must not silently overwrite it."""
    from starlette.requests import Request as StarletteRequest

    existing_user = _FakeUser(id=42, telegram_user_id=555, google_sub="other-google-sub")
    fake_session = _FakeSession(scalar_results=[None], users_by_pk={42: existing_user})

    @contextmanager
    def _fake_get_session():
        yield fake_session

    transport = _mock_google_exchange("google-sub-new-3")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/auth/google/callback",
        "session": {"oauth_state": "abc", "user_id": 42},
        "query_string": b"",
        "headers": [],
        "app": website_main.app,
    }
    request = StarletteRequest(scope)

    with patch.object(website_main, "GOOGLE_CLIENT_ID", _CLIENT_ID), patch.object(
        website_main, "GOOGLE_CLIENT_SECRET", _CLIENT_SECRET
    ), patch.object(website_main, "get_session", _fake_get_session), patch.object(
        httpx, "post", lambda url, **kw: httpx.Client(transport=transport).post(url, **kw)
    ), patch.object(
        httpx, "get", lambda url, **kw: httpx.Client(transport=transport).get(url, **kw)
    ):
        resp = website_main.auth_google_callback(request, code="abc", state="abc")

    assert resp.status_code == 200
    assert existing_user.google_sub == "other-google-sub"  # never overwritten — the real invariant
    # A PendingGoogleLink row IS still generated for this new google_sub (harmless: consuming its
    # token later just hits the same "don't overwrite" guard again bot-side), so committed is True.
    assert fake_session.committed is True


def test_callback_token_exchange_failure_returns_400(client):
    state = _do_start(client)

    def _fake_post(url, **kw):
        return httpx.Response(400, json={"error": "invalid_grant"}, request=httpx.Request("POST", url))

    with patch.object(httpx, "post", _fake_post):
        resp = client.get("/auth/google/callback", params={"code": "bad-code", "state": state})

    assert resp.status_code == 400

"""Tests for website/main.py's /account — the cross-channel linking page (todira_common/
channel_link.py): shows which channels (Telegram/Google) are already linked to the
resolved user, and generates a fresh code + a Telegram deep link when Telegram isn't.

2026-09-25: /account became the site's eighth React island (website/landing-react/account.html).
Unlike the other converted pages, its POST actions (cancel/resume-subscription, notifications)
are DELIBERATELY UNCHANGED — still plain form-encoded POSTs redirecting
back to /account, not fetch (see account()'s own comment in main.py for why) — so every POST test
below is untouched from before this conversion. GET tests now extract and assert against the
`account_config` JSON object main.py injects into window.__TODIRA_PAGE__ (via `| tojson` — see
account.html's own comment on why the whole object goes through that, not field-by-field) rather
than server-rendered HTML, which is a frontend concern verified separately (Playwright, against
Account.jsx directly via the Vite dev server with an injected config, since /account needs a real
DB-resolved user that this sandbox has no live database for).

Same importlib-loading approach as test_website_paid_access.py (see that file's comment) —
website/main.py shares a basename with scraper/main.py so it can't go through a bare `import main`.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import json
import os
import re
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_account", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_FIXED_CODE = "ref_test01"
# account.html emits the whole window.__TODIRA_PAGE__ assignment as ONE line (see that template),
# so this matches within a single line rather than across the whole page — a DOTALL/greedy
# version would happily match all the way to some LATER unrelated <script> tag's own "});" instead
# (found live: base.html has other inline scripts using that exact closing pattern).
_CONFIG_RE = re.compile(r'Object\.assign\(\{ lang: "([^"]*)", dir: "([^"]*)" \}, (.*)\);$', re.MULTILINE)


def _account_config(html: str) -> dict:
    """Parses the account_config JSON object (plus lang/dir) out of the rendered React-shell
    response — see account.html's own `Object.assign({ lang, dir }, {{ account_config | tojson }})`
    line. Fails loudly (not silently returns {}) if the page didn't actually render the React
    shell at all, so a route regression shows up as a clear assertion/parse error, not a
    confusing "field missing" failure somewhere else."""
    match = _CONFIG_RE.search(html)
    assert match is not None, "window.__TODIRA_PAGE__ config not found in response"
    lang, dir_, config_json = match.groups()
    config = json.loads(config_json)
    config["lang"] = lang
    config["dir"] = dir_
    return config


class _FakeUser:
    def __init__(
        self,
        id,
        telegram_user_id=None,
        google_sub=None,
        free_access_granted=False,
        trial_ends_at=None,
        paid_until=None,
        notifications_enabled=True,
        takbull_subscription_uniqid=None,
        cancel_at_period_end=False,
        telegram_username=None,
        google_email=None,
        first_name=None,
        channel_link_code=None,
        channel_link_code_expires_at=None,
        language=None,
    ):
        self.id = id
        self.telegram_user_id = telegram_user_id
        self.google_sub = google_sub
        self.free_access_granted = free_access_granted
        self.trial_ends_at = trial_ends_at
        self.paid_until = paid_until
        self.notifications_enabled = notifications_enabled
        self.takbull_subscription_uniqid = takbull_subscription_uniqid
        self.cancel_at_period_end = cancel_at_period_end
        self.telegram_username = telegram_username
        self.google_email = google_email
        self.channel_link_code = channel_link_code
        self.channel_link_code_expires_at = channel_link_code_expires_at
        self.language = language
        # Only read by _current_user_summary (base.html's header, called on every _render()) when
        # the visitor has a REAL signed session — see test_account_config_shows_logout_button_*
        # below, the first test in this file to actually exercise that path.
        self.first_name = first_name


class _FakeSession:
    def __init__(self, users_by_telegram_id=None, payments=None, users_by_pk=None, cancellable_payment=None):
        self._by_telegram_id = users_by_telegram_id or {}
        self._payments = payments or []
        # 2026-10-13: what a select(Payment) scalar() returns - the pass /account may offer to cancel
        # (main.py's _cancellable_pass_payment). Every other scalar() is still a user lookup.
        self._cancellable_payment = cancellable_payment
        # 2026-09-26: backs the session_user_id branch of _resolve_user (session.get(User, pk)) —
        # used to test isLoggedInViaSession, when the visitor has a REAL signed session rather than
        # just a ?uid= deep link. Also backs _current_user_summary's own session.execute(...).first()
        # lookup (called on every _render(), including /account's own) — same pattern
        # test_website_auth_google.py's _FakeSession already uses for the identical lookup.
        self._users_by_pk = users_by_pk or {}
        self.committed = False

    def scalar(self, stmt):
        if stmt.column_descriptions[0].get("entity") is website_main.Payment:
            return self._cancellable_payment
        for user in self._by_telegram_id.values():
            return user
        return None

    def scalars(self, stmt):
        return self._payments

    def commit(self):
        self.committed = True

    def get(self, model, pk):
        return self._users_by_pk.get(pk)

    def execute(self, stmt):
        class _Result:
            def __init__(self, row):
                self._row = row

            def first(self):
                return self._row

        user = next(iter(self._users_by_pk.values()), None)
        return _Result(user)


@pytest.fixture
def client():
    with patch.object(website_main, "generate_link_code", lambda session, user: _FIXED_CODE):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _fake_get_session(session):
    @contextmanager
    def _inner():
        yield session

    return _inner


class _FakePayment:
    def __init__(self, plan, amount_ils, status, created_at, paid_at=None, subscription_uniqid=None):
        self.id = 9
        self.plan = plan
        self.amount_ils = amount_ils
        self.status = status
        self.created_at = created_at
        self.paid_at = paid_at
        self.subscription_uniqid = subscription_uniqid
        self.gateway_transaction_id = "T-1"


def test_account_requires_a_resolvable_user(client):
    fake_session = _FakeSession()
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 999999})

    assert resp.status_code == 200
    assert "טודירה" in resp.text  # need_uid.html rendered, not a crash


def test_account_renders_react_island(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert resp.status_code == 200
    assert 'id="root"' in resp.text
    assert "/static/landing/assets/" in resp.text
    assert "/static/landing/assets/account-" in resp.text  # its OWN entry, not another page's


def _account_for_session_user(user, **patches):
    """/account for a visitor with a real signed session and no Telegram (a Google-only account) —
    the only kind of account that still gets a link code. A raw Request, like
    test_account_config_shows_logged_in_via_session_for_a_real_signed_session below, since the
    TestClient's session cookie can't be set without a real login round-trip."""
    from starlette.requests import Request as StarletteRequest

    fake_session = _FakeSession(users_by_pk={user.id: user})
    scope = {
        "type": "http", "method": "GET", "path": "/account", "session": {"user_id": user.id},
        "query_string": b"", "headers": [], "app": website_main.app,
    }
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        with contextlib.ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(patch.object(website_main, name, value))
            resp = website_main.account(StarletteRequest(scope))
    return _account_config(resp.body.decode())


def test_account_generates_a_code_when_telegram_is_missing():
    user = _FakeUser(id=2, google_sub="g-sub")
    config = _account_for_session_user(user, generate_link_code=lambda session, u: _FIXED_CODE)
    assert config["code"] == _FIXED_CODE
    assert config["hasTelegram"] is False
    assert config["telegramLink"] == f"https://t.me/AmirDirotBot?start={_FIXED_CODE}"


def test_account_reuses_an_existing_still_valid_code_instead_of_regenerating():
    """2026-09-27: real bug, live-confirmed — this route used to call generate_link_code()
    unconditionally on every single page load. generate_link_code REPLACES whatever code was
    already stored, so simply reloading /account after already sending a code (a completely
    natural thing to do while checking whether the link worked) silently orphaned the code
    already sent — resolve_link_code just treats the now-unmatched code as "not a link code" and
    falls through, with no error surfaced anywhere."""
    user = _FakeUser(
        id=2, google_sub="g-sub", channel_link_code="ref_existing",
        channel_link_code_expires_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10),
    )
    generate = MagicMock()
    config = _account_for_session_user(user, generate_link_code=generate)
    generate.assert_not_called()
    assert config["code"] == "ref_existing"


def test_account_regenerates_an_expired_code():
    user = _FakeUser(
        id=2, google_sub="g-sub", channel_link_code="ref_old",
        channel_link_code_expires_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1),
    )
    config = _account_for_session_user(user, generate_link_code=lambda session, u: _FIXED_CODE)
    assert config["code"] == _FIXED_CODE


def test_account_does_not_generate_a_code_once_telegram_is_linked(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(
        website_main, "generate_link_code"
    ) as generate_mock, patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    generate_mock.assert_not_called()
    config = _account_config(resp.text)
    assert config["code"] is None


def test_account_config_has_no_telegram_connect_link_once_telegram_is_linked(client):
    """With Telegram linked there is no link code at all (2026-10-13: Telegram is the only channel
    a code can attach), so Account.jsx shows the connected state and never a connect button."""
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["hasTelegram"] is True
    assert config["telegramLink"] is None


def test_account_config_carries_the_connected_identity_for_each_linked_channel(client):
    """2026-09-26 real owner request: a user with several channels linked couldn't tell them
    apart from a bare "connected" checkmark — /account now also surfaces WHICH Telegram username
    and Google email each connected channel actually is."""
    user = _FakeUser(
        id=2, telegram_user_id=222, google_sub="g-sub-123", telegram_username="amir_toledano",
        google_email="owner@example.com",
    )
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["telegramUsername"] == "amir_toledano"
    assert config["googleEmail"] == "owner@example.com"


def test_account_config_identity_fields_are_null_when_not_set(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["telegramUsername"] is None
    assert config["googleEmail"] is None


def test_account_config_carries_uid_for_the_react_google_link_button(client):
    """2026-09-05 real bug fix (pre-React): the old server-rendered template hand-wrote
    '&amp;uid=' inside a Jinja expression, which autoescaping then escaped AGAIN — a browser
    HTML-decodes that once into the literal string '&amp;uid=123', parsed as a param literally
    named 'amp;uid', never 'uid', so every Google-link click silently lost its uid. That whole bug
    class doesn't apply to React (Account.jsx builds the href in JS, setting the DOM attribute
    directly — see login page's own equivalent test for the same reasoning) — this just confirms
    the real uid value the React button needs actually reaches the page."""
    user = _FakeUser(id=2, telegram_user_id=222, google_sub=None)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["uid"] == 222


def test_account_shows_active_subscription_status_when_paid_until_is_future(client):
    paid_until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=10)
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=paid_until)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["hasAccess"] is True
    assert config["paidUntil"] == paid_until.strftime("%d/%m/%Y")


def test_account_shows_trial_subscription_status_when_trial_still_open(client):
    trial_ends_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)
    user = _FakeUser(id=2, telegram_user_id=222, trial_ends_at=trial_ends_at)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["paidUntil"] is None
    assert config["trialEndsAt"] == trial_ends_at.strftime("%d/%m/%Y")


def test_account_shows_expired_subscription_status_when_no_trial_or_paid(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["hasAccess"] is False
    assert config["paidUntil"] is None
    assert config["trialEndsAt"] is None


def test_account_hides_subscription_card_for_the_owner(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "OWNER_TELEGRAM_USER_ID", "222"),
    ):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["displayIsOwner"] is True


def test_account_notifications_toggle_flips_and_redirects_with_uid(client):
    user = _FakeUser(id=2, telegram_user_id=222, notifications_enabled=True)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/account/notifications", data={"uid": 222})

    assert resp.status_code == 303
    assert resp.headers["location"] == "/account?uid=222"
    assert user.notifications_enabled is False
    assert fake_session.committed is True


def test_account_config_carries_payment_history_when_payments_exist(client):
    """2026-09-26 real crash found live: Payment.amount_ils is a real Decimal (Numeric(10,2)
    column, see common/todira_common/models.py) — this test used to pass a plain int here, which
    never exercises `{{ account_config | tojson }}`'s real failure mode (json.dumps has no default
    encoding for Decimal, so ANY user with real payment history got a 500 — Safari then offered
    FastAPI's default plain-text error body as a download instead of rendering it, the same
    "apartments.txt" symptom as the earlier incident, reported live by the owner testing their own
    real account). Decimal("49.90") here is deliberately the exact value production uses
    (PLAN_PRICES_ILS[SUBSCRIPTION_PLAN] in access.py) — this test would have caught the crash."""
    user = _FakeUser(id=2, telegram_user_id=222)
    payments = [
        _FakePayment(
            "monthly_subscription", Decimal("49.90"), "paid", dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
            paid_at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc),
        ),
        _FakePayment("weekly", Decimal("15.00"), "failed", dt.datetime(2026, 8, 15, tzinfo=dt.timezone.utc)),
    ]
    fake_session = _FakeSession(users_by_telegram_id={222: user}, payments=payments)
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert resp.status_code == 200
    config = _account_config(resp.text)
    assert config["payments"] == [
        {"plan": "monthly_subscription", "amountIls": "49.90", "date": "01/08/2026", "status": "paid"},
        {"plan": "weekly", "amountIls": "15.00", "date": "15/08/2026", "status": "failed"},
    ]


def test_an_abandoned_checkout_is_not_shown_as_a_pending_payment(client):
    """2026-10-13 owner report: three "ממתין" rows on /account — checkouts that were opened and never paid (every press
    of the checkout button records a pending row before Takbull's page opens). A pending row is shown only while it can
    still be paid (the first hour)."""
    now = dt.datetime.now(dt.timezone.utc)
    user = _FakeUser(id=2, telegram_user_id=222)
    payments = [
        _FakePayment("pass_30", Decimal("49.90"), "pending", now - dt.timedelta(minutes=5)),
        _FakePayment("pass_30", Decimal("49.90"), "pending", now - dt.timedelta(hours=3)),
        _FakePayment("weekly", Decimal("15.00"), "pending", dt.datetime(2026, 9, 6, tzinfo=dt.timezone.utc)),
        _FakePayment("pass_7", Decimal("19.90"), "paid", now - dt.timedelta(days=2), paid_at=now - dt.timedelta(days=2)),
    ]
    fake_session = _FakeSession(users_by_telegram_id={222: user}, payments=payments)
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert [(p["plan"], p["status"]) for p in config["payments"]] == [("pass_30", "pending"), ("pass_7", "paid")]


def test_payment_history_still_shows_at_most_ten_rows(client):
    now = dt.datetime.now(dt.timezone.utc)
    user = _FakeUser(id=2, telegram_user_id=222)
    payments = [
        _FakePayment("pass_7", Decimal("19.90"), "paid", now - dt.timedelta(days=d), paid_at=now - dt.timedelta(days=d))
        for d in range(15)
    ]
    fake_session = _FakeSession(users_by_telegram_id={222: user}, payments=payments)
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    assert len(_account_config(resp.text)["payments"]) == 10


def test_account_hides_payment_history_section_when_no_payments(client):
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user}, payments=[])
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["payments"] == []


def test_account_config_matches_requested_language(client):
    user = _FakeUser(
        id=2, telegram_user_id=222, trial_ends_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2),
    )
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222, "lang": "en"})

    config = _account_config(resp.text)
    assert config["lang"] == "en"
    assert config["dir"] == "ltr"


def test_account_config_shows_logged_in_via_session_for_a_real_signed_session(client):
    """2026-09-26 real owner report: logged in with Google, then had no way to log out short of an
    incognito window — /account now surfaces a logout button, but only when the visitor has a REAL
    signed session (request.session["user_id"]), not just a ?uid= deep link, which has no
    session to end. Uses a raw Request (like test_website_auth_google.py's own session-branch
    tests) since the TestClient's session cookie can't be set without a real login round-trip."""
    from starlette.requests import Request as StarletteRequest

    user = _FakeUser(id=2, telegram_user_id=222, first_name="Amir")
    fake_session = _FakeSession(users_by_pk={2: user})
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/account",
        "session": {"user_id": 2},
        "query_string": b"",
        "headers": [],
        "app": website_main.app,
    }
    request = StarletteRequest(scope)
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)), patch.object(
        website_main, "generate_link_code", lambda session, user: _FIXED_CODE
    ):
        resp = website_main.account(request)

    config = _account_config(resp.body.decode())
    assert config["isLoggedInViaSession"] is True


def test_account_config_reports_a_session_when_opened_via_a_signed_bot_link(client):
    """2026-10-02: a signed ?t= bot link signs the visitor in (a real session cookie), so unlike the
    old unsigned ?uid= there IS a session to log out of."""
    user = _FakeUser(id=2, telegram_user_id=222)
    fake_session = _FakeSession(users_by_telegram_id={222: user})
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.get("/account", params={"uid": 222})

    config = _account_config(resp.text)
    assert config["isLoggedInViaSession"] is True


# --- 2026-10-13: cancelling a one-time pass from /account (terms section 10) ---


def _paid_pass(plan="pass_30", amount="49.90", days_ago=9.5):
    paid_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)
    return _FakePayment(plan, Decimal(amount), "paid", paid_at, paid_at=paid_at)


def test_account_config_offers_cancelling_a_recent_pass_with_the_refund_worked_out(client):
    payment = _paid_pass()
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=payment.paid_at + dt.timedelta(days=30))
    fake_session = _FakeSession(users_by_telegram_id={222: user}, cancellable_payment=payment)
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        config = _account_config(client.get("/account", params={"uid": 222}).text)

    assert config["cancelPass"] == {
        "plan": "pass_30", "paidIls": "49.90", "elapsedDays": 10, "coveringIls": "29.90", "feeIls": "2.50",
        "refundIls": "17.50",
    }
    assert config["cancelledRefundIls"] is None


def test_account_config_has_no_cancel_link_without_a_cancellable_pass(client):
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=5))
    fake_session = _FakeSession(users_by_telegram_id={222: user}, cancellable_payment=None)
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        config = _account_config(client.get("/account", params={"uid": 222}).text)
    assert config["cancelPass"] is None


def test_cancelling_a_pass_ends_its_days_marks_it_cancelled_and_tells_the_owner(client):
    payment = _paid_pass()
    paid_until = payment.paid_at + dt.timedelta(days=30)
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=paid_until, first_name="Dana")
    fake_session = _FakeSession(users_by_telegram_id={222: user}, cancellable_payment=payment)
    sent = []
    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "_notify_owner_sync", lambda *args: sent.append(args) or True),
    ):
        resp = client.post("/account/cancel-pass", data={"uid": 222, "confirm": "yes"})
        config = _account_config(client.get("/account", params={"uid": 222}).text)

    assert resp.status_code == 303 and resp.headers["location"] == "/account?uid=222"
    assert payment.status == "cancelled" and fake_session.committed
    assert user.paid_until <= dt.datetime.now(dt.timezone.utc)  # this pass's 30 days are gone, nothing earlier existed
    assert len(sent) == 1 and "₪17.50" in sent[0][2] and "T-1" in sent[0][2]
    assert config["cancelledRefundIls"] == "17.50"  # shown once after the redirect


def test_cancelling_keeps_the_time_an_earlier_pass_had_left(client):
    payment = _paid_pass(plan="pass_7", amount="19.90", days_ago=1)
    earlier_end = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=4)
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=earlier_end + dt.timedelta(days=7))
    fake_session = _FakeSession(users_by_telegram_id={222: user}, cancellable_payment=payment)
    with (
        patch.object(website_main, "get_session", _fake_get_session(fake_session)),
        patch.object(website_main, "_notify_owner_sync", lambda *args: True),
    ):
        client.post("/account/cancel-pass", data={"uid": 222, "confirm": "yes"})
    assert user.paid_until == earlier_end


def test_cancel_without_the_confirm_field_does_nothing(client):
    payment = _paid_pass()
    user = _FakeUser(id=2, telegram_user_id=222, paid_until=payment.paid_at + dt.timedelta(days=30))
    fake_session = _FakeSession(users_by_telegram_id={222: user}, cancellable_payment=payment)
    with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
        resp = client.post("/account/cancel-pass", data={"uid": 222})
    assert resp.status_code == 303 and payment.status == "paid" and not fake_session.committed


def test_account_config_counts_the_days_of_access_left(client):
    now = dt.datetime.now(dt.timezone.utc)
    for ends_in, expected in ((dt.timedelta(days=19, hours=5), 20), (dt.timedelta(hours=3), 1), (-dt.timedelta(days=1), None)):
        user = _FakeUser(id=2, telegram_user_id=222, paid_until=now + ends_in)
        fake_session = _FakeSession(users_by_telegram_id={222: user})
        with patch.object(website_main, "get_session", _fake_get_session(fake_session)):
            config = _account_config(client.get("/account", params={"uid": 222}).text)
        assert config["daysLeft"] == expected

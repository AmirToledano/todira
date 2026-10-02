"""Zero-cost WhatsApp (2026-10-02): the 24h window rule, the "still looking?" check-in, the webhook's
inbound stamping + button replies + missed-listings digest, and the new send message shapes.

The owner's rule: never pay Meta. Free-form messages are free only inside 24h of the user's own last
inbound message, so everything here protects "nothing is sent outside the window".
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

for _dir in ("website", "scraper"):
    _path = str(Path(__file__).resolve().parent.parent / _dir)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import whatsapp_checkin  # noqa: E402
import whatsapp_webhook  # noqa: E402
from todira_common import whatsapp_client, whatsapp_window  # noqa: E402
from todira_common.bot_strings import BOT_STRINGS, bot_text  # noqa: E402

_NOW = dt.datetime(2026, 10, 2, 12, 0, tzinfo=dt.timezone.utc)


def _ago(**kwargs):
    return _NOW - dt.timedelta(**kwargs)


# --- window rules ---


def test_window_closed_when_never_heard_from_user():
    assert whatsapp_window.window_open(None, _NOW) is False


def test_window_open_within_safe_margin_and_closed_after():
    assert whatsapp_window.window_open(_ago(hours=23), _NOW) is True
    assert whatsapp_window.window_open(_ago(hours=23, minutes=45), _NOW) is False
    assert whatsapp_window.window_open(_ago(hours=25), _NOW) is False


def test_window_handles_naive_timestamps_as_utc():
    naive = (_NOW - dt.timedelta(hours=1)).replace(tzinfo=None)
    assert whatsapp_window.window_open(naive, _NOW) is True


def test_checkin_not_due_early_in_the_window():
    assert whatsapp_window.checkin_due(_ago(hours=5), None, _NOW) is False


def test_checkin_due_near_the_end_of_an_open_window():
    assert whatsapp_window.checkin_due(_ago(hours=21), None, _NOW) is True


def test_checkin_not_due_once_the_window_is_closed():
    """No template fallback: a closed window means silence until the user writes again."""
    assert whatsapp_window.checkin_due(_ago(hours=30), None, _NOW) is False


def test_checkin_not_repeated_within_the_same_window():
    last_inbound = _ago(hours=21)
    assert whatsapp_window.checkin_due(last_inbound, _ago(hours=1), _NOW) is False


def test_checkin_due_again_after_a_new_window_opened():
    assert whatsapp_window.checkin_due(_ago(hours=21), _ago(hours=40), _NOW) is True


# --- the check-in runner ---


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, users):
        self.users = users
        self.commits = 0

    def scalars(self, _query):
        return _FakeScalars(self.users)

    def commit(self):
        self.commits += 1


def _wa_user(**overrides):
    defaults = dict(
        id=1, whatsapp_phone_number="9725500000", whatsapp_notifications_opted_in=True,
        whatsapp_last_inbound_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=21),
        whatsapp_checkin_sent_at=None, language="he",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _breaker_not_tripped():
    # Replace the module reference inside whatsapp_checkin only (not the real guard module, which the
    # circuit-breaker tests below exercise directly).
    with patch.object(whatsapp_checkin, "whatsapp_guard", SimpleNamespace(is_paused=lambda session: False)):
        yield


def test_run_checkins_sends_buttons_to_due_users_and_stamps_them():
    user = _wa_user()
    session = _FakeSession([user])
    with (
        patch.object(whatsapp_checkin.whatsapp_client, "send_reply_buttons_message", return_value=True) as mock_send,
        patch.object(whatsapp_checkin, "_SEND_DELAY_SECONDS", 0),
    ):
        result = whatsapp_checkin.run_whatsapp_checkins(session)

    assert result == {"whatsapp_checkins_sent": 1}
    args = mock_send.call_args.args
    assert args[0] == "9725500000"
    assert [button_id for button_id, _t in args[2]] == [
        "checkin_continue", "checkin_found", "checkin_stop",
    ]
    assert user.whatsapp_checkin_sent_at is not None
    assert session.commits == 1


def test_run_checkins_skips_users_not_due_and_users_with_closed_windows():
    early = _wa_user(whatsapp_last_inbound_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2))
    closed = _wa_user(id=2, whatsapp_last_inbound_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=40))
    with patch.object(whatsapp_checkin.whatsapp_client, "send_reply_buttons_message") as mock_send:
        result = whatsapp_checkin.run_whatsapp_checkins(_FakeSession([early, closed]))

    mock_send.assert_not_called()
    assert result == {"whatsapp_checkins_sent": 0}


def test_run_checkins_does_not_stamp_when_the_send_fails():
    user = _wa_user()
    with (
        patch.object(whatsapp_checkin.whatsapp_client, "send_reply_buttons_message", return_value=False),
        patch.object(whatsapp_checkin, "_SEND_DELAY_SECONDS", 0),
    ):
        result = whatsapp_checkin.run_whatsapp_checkins(_FakeSession([user]))

    assert result == {"whatsapp_checkins_sent": 0}
    assert user.whatsapp_checkin_sent_at is None


def test_checkin_button_titles_fit_whatsapps_20_character_limit_in_every_language():
    for key in (
        "whatsapp.checkin_continue_button", "whatsapp.checkin_found_button",
        "whatsapp.checkin_stop_button", "whatsapp.view_listing_button", "whatsapp.upgrade_button",
    ):
        for lang, title in BOT_STRINGS[key].items():
            assert len(title) <= 20, (key, lang, title)


def test_every_new_whatsapp_string_exists_in_all_five_languages():
    for key in BOT_STRINGS:
        if key.startswith("whatsapp.checkin_") or key in (
            "whatsapp.resume_ack", "whatsapp.missed_digest",
            "whatsapp.view_listing_button", "whatsapp.upgrade_button",
        ):
            assert set(BOT_STRINGS[key]) == {"he", "en", "ru", "fr", "ar"}, key
    assert "{total}" in bot_text("whatsapp.missed_digest", "he", total="{total}", url="u")


# --- webhook: button replies, opt-in changes, digest ---


class _WebhookSession:
    def __init__(self, user, filter_row=None):
        self.user = user
        self.filter_row = filter_row
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def scalar(self, query):
        # Both lookups below are by phone number (User) or by user id (Filter).
        return self.filter_row if "filters" in str(query) else self.user

    def commit(self):
        self.commits += 1


def _patch_session(session):
    return patch.object(whatsapp_webhook, "get_session", lambda: session)


def test_touch_inbound_returns_the_summary_start_when_a_closed_window_reopens():
    """Away for 48h, then taps: the summary starts from the moment of the PREVIOUS message."""
    previous = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)
    user = _wa_user(whatsapp_last_inbound_at=previous)
    with _patch_session(_WebhookSession(user)):
        since = whatsapp_webhook._touch_inbound_sync("9725500000")
    assert since == previous
    assert whatsapp_window.window_open(user.whatsapp_last_inbound_at) is True


def test_touch_inbound_summary_never_reaches_back_more_than_a_week():
    user = _wa_user(whatsapp_last_inbound_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30))
    with _patch_session(_WebhookSession(user)):
        since = whatsapp_webhook._touch_inbound_sync("9725500000")
    age = dt.datetime.now(dt.timezone.utc) - since
    assert dt.timedelta(days=6, hours=23) < age < dt.timedelta(days=7, minutes=1)


def test_touch_inbound_defaults_to_48_hours_when_the_previous_message_time_is_unknown():
    user = _wa_user(whatsapp_last_inbound_at=None)
    with _patch_session(_WebhookSession(user)):
        since = whatsapp_webhook._touch_inbound_sync("9725500000")
    age = dt.datetime.now(dt.timezone.utc) - since
    assert dt.timedelta(hours=47, minutes=59) < age < dt.timedelta(hours=48, minutes=1)


def test_touch_inbound_reports_no_reopen_when_window_was_already_open():
    user = _wa_user(whatsapp_last_inbound_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3))
    with _patch_session(_WebhookSession(user)):
        assert whatsapp_webhook._touch_inbound_sync("9725500000") is None


def test_touch_inbound_is_a_noop_for_an_unknown_number():
    with _patch_session(_WebhookSession(None)):
        assert whatsapp_webhook._touch_inbound_sync("9725599999") is None


def test_continue_button_keeps_opt_in_and_acks():
    user = _wa_user()
    with (
        _patch_session(_WebhookSession(user)),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as mock_text,
    ):
        whatsapp_webhook._handle_checkin_button_sync("9725500000", "checkin_continue")

    assert user.whatsapp_notifications_opted_in is True
    assert mock_text.call_args.args[1] == bot_text("whatsapp.checkin_continue_ack", "he")


def test_found_and_stop_buttons_turn_notifications_off():
    for button_id, ack_key in (
        ("checkin_found", "whatsapp.checkin_found_ack"),
        ("checkin_stop", "whatsapp.checkin_stop_ack"),
    ):
        user = _wa_user()
        with (
            _patch_session(_WebhookSession(user)),
            patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as mock_text,
        ):
            whatsapp_webhook._handle_checkin_button_sync("9725500000", button_id)

        assert user.whatsapp_notifications_opted_in is False
        assert mock_text.call_args.args[1] == bot_text(ack_key, "he")


def test_resume_word_reenables_a_stopped_user_who_has_a_filter():
    user = _wa_user(whatsapp_notifications_opted_in=False)
    with (
        _patch_session(_WebhookSession(user, filter_row=SimpleNamespace(id=1))),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as mock_text,
    ):
        assert whatsapp_webhook._try_resume_sync("9725500000", "המשך") is True

    assert user.whatsapp_notifications_opted_in is True
    mock_text.assert_called_once()


def test_resume_word_ignored_when_already_opted_in_or_not_a_resume_word():
    user = _wa_user()
    with _patch_session(_WebhookSession(user, filter_row=SimpleNamespace(id=1))):
        assert whatsapp_webhook._try_resume_sync("9725500000", "המשך") is False
        assert whatsapp_webhook._try_resume_sync("9725500000", "שלום") is False


def test_missed_digest_sends_one_link_with_the_count_and_marks_them_shown():
    user = _wa_user()
    with (
        _patch_session(_WebhookSession(user, filter_row=SimpleNamespace(id=1))),
        patch.object(
            whatsapp_webhook, "find_new_matches_to_show", return_value=(9, [object(), object(), object()])
        ),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as mock_text,
        patch.object(whatsapp_webhook, "generate_wid_token", return_value="signed"),
    ):
        whatsapp_webhook._send_missed_digest_sync("9725500000")

    mock_text.assert_called_once()
    body = mock_text.call_args.args[1]
    assert "3" in body and "wid=signed" in body


def test_missed_digest_sends_nothing_when_nothing_was_missed():
    with (
        _patch_session(_WebhookSession(_wa_user(), filter_row=SimpleNamespace(id=1))),
        patch.object(whatsapp_webhook, "find_new_matches_to_show", return_value=(4, [])),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message") as mock_text,
    ):
        whatsapp_webhook._send_missed_digest_sync("9725500000")

    mock_text.assert_not_called()


_SINCE = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)


def _payload(message):
    return {"entry": [{"changes": [{"value": {"contacts": [], "messages": [message]}}]}]}


def test_payload_button_tap_is_stamped_answered_and_digests_after_a_closed_window():
    message = {
        "id": "m1", "from": "9725500000", "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": "checkin_continue", "title": "x"}},
    }
    with (
        patch.object(whatsapp_webhook, "_already_processed", return_value=False),
        patch.object(whatsapp_webhook, "_touch_inbound_safely", return_value=_SINCE) as mock_touch,
        patch.object(whatsapp_webhook, "_handle_checkin_button_sync") as mock_handle,
        patch.object(whatsapp_webhook, "_send_missed_digest_sync") as mock_digest,
        patch.object(whatsapp_webhook, "_ensure_language_selected_sync") as mock_lang,
    ):
        whatsapp_webhook._process_payload_sync(_payload(message))

    mock_handle.assert_called_once_with("9725500000", "checkin_continue")
    mock_digest.assert_called_once_with("9725500000", _SINCE)
    mock_lang.assert_not_called()
    assert mock_touch.call_count == 2  # before handling and again in the finally


def test_payload_button_tap_inside_open_window_sends_no_digest():
    message = {
        "id": "m1", "from": "9725500000", "type": "interactive",
        "interactive": {"type": "button_reply", "button_reply": {"id": "checkin_continue", "title": "x"}},
    }
    with (
        patch.object(whatsapp_webhook, "_already_processed", return_value=False),
        patch.object(whatsapp_webhook, "_touch_inbound_safely", return_value=None),
        patch.object(whatsapp_webhook, "_handle_checkin_button_sync"),
        patch.object(whatsapp_webhook, "_send_missed_digest_sync") as mock_digest,
    ):
        whatsapp_webhook._process_payload_sync(_payload(message))

    mock_digest.assert_not_called()


# --- new send message shapes ---


def _capture_post():
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs["json"])
        return SimpleNamespace(raise_for_status=lambda: None, status_code=200)

    return calls, fake_post


def test_image_cta_message_has_image_header_body_and_url_button(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1")
    calls, fake_post = _capture_post()
    with patch.object(whatsapp_client._http_client, "post", fake_post):
        assert whatsapp_client.send_image_cta_message(
            "9725500000", image_url="https://todira.app/media/listing/1.jpg", body="text", button_text="btn", url="https://x"
        ) is True

    interactive = calls[0]["interactive"]
    assert calls[0]["type"] == "interactive"
    assert interactive["type"] == "cta_url"
    # Meta rejects an uploaded media id here (error 131008) - the header must be a public link.
    assert interactive["header"] == {"type": "image", "image": {"link": "https://todira.app/media/listing/1.jpg"}}
    assert interactive["body"] == {"text": "text"}
    assert interactive["action"]["parameters"] == {"display_text": "btn", "url": "https://x"}


def test_reply_buttons_message_shape(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1")
    calls, fake_post = _capture_post()
    with patch.object(whatsapp_client._http_client, "post", fake_post):
        whatsapp_client.send_reply_buttons_message("9725500000", "q?", [("a", "A"), ("b", "B")])

    interactive = calls[0]["interactive"]
    assert interactive["type"] == "button"
    assert interactive["action"]["buttons"] == [
        {"type": "reply", "reply": {"id": "a", "title": "A"}},
        {"type": "reply", "reply": {"id": "b", "title": "B"}},
    ]


def test_button_ids_match_between_the_checkin_sender_and_the_webhook():
    assert whatsapp_checkin.CHECKIN_CONTINUE_ID == whatsapp_webhook.CHECKIN_CONTINUE_ID
    assert whatsapp_checkin.CHECKIN_FOUND_ID == whatsapp_webhook.CHECKIN_FOUND_ID
    assert whatsapp_checkin.CHECKIN_STOP_ID == whatsapp_webhook.CHECKIN_STOP_ID


def test_whatsapp_caption_respects_the_interactive_body_limit_and_can_drop_the_link_line():
    from types import SimpleNamespace as NS

    from todira_common.cards import format_caption_whatsapp

    listing = NS(
        id=1, url="https://example.com/x", source="yad2", deal_type="rent", is_broker_listing=False,
        rooms=4, floor=2, floor_total=3, size_sqm=100, price=9000, move_in_date=None,
        has_parking=None, has_elevator=None, has_balcony=None, pets_allowed=None, is_renovated=None,
        is_roommate_friendly=None, safe_room_type=None, furniture=None, street=None,
        neighborhood="ניות", city="ירושלים", description="א" * 3000,
    )
    caption = format_caption_whatsapp(listing, has_access=True, link_in_body=False, limit=1024)
    assert len(caption) <= 1024
    assert "https://" not in caption
    with_link = format_caption_whatsapp(listing, has_access=True, view_url="https://todira.app/v", limit=1024)
    assert "https://todira.app/v" in with_link and len(with_link) <= 1024


def test_checkins_are_not_sent_while_the_circuit_breaker_is_paused():
    with (
        patch.object(whatsapp_checkin.whatsapp_guard, "is_paused", return_value=True),
        patch.object(whatsapp_checkin.whatsapp_client, "send_reply_buttons_message") as mock_send,
    ):
        result = whatsapp_checkin.run_whatsapp_checkins(_FakeSession([_wa_user()]))

    mock_send.assert_not_called()
    assert result["whatsapp_checkins_sent"] == 0


# --- circuit breaker ---


def test_guard_fails_closed_when_the_flag_cannot_be_read():
    from todira_common import whatsapp_guard

    class _BrokenSession:
        def get(self, *args, **kwargs):
            raise RuntimeError("db down")

    assert whatsapp_guard.is_paused(_BrokenSession()) is True


def test_guard_pause_and_resume_roundtrip():
    from todira_common import whatsapp_guard

    store = {}

    class _Session:
        def get(self, model, key):
            return store.get(key)

        def add(self, row):
            store[row.key] = row

        def commit(self):
            pass

    session = _Session()
    assert whatsapp_guard.is_paused(session) is False
    whatsapp_guard.pause(session, "billable message seen")
    assert whatsapp_guard.is_paused(session) is True
    whatsapp_guard.resume(session)
    assert whatsapp_guard.is_paused(session) is False


def _status_value(billable):
    return {"statuses": [{"status": "delivered", "pricing": {"billable": billable, "category": "service" if not billable else "marketing", "pricing_model": "PMP"}}]}


def test_a_billable_delivery_status_trips_the_breaker_and_alerts_the_owner():
    with (
        patch.object(whatsapp_webhook, "_trip_billing_breaker") as mock_trip,
    ):
        whatsapp_webhook._log_delivery_statuses(_status_value(True))

    mock_trip.assert_called_once_with("marketing", "PMP", None)


def test_a_free_delivery_status_never_trips_the_breaker():
    with patch.object(whatsapp_webhook, "_trip_billing_breaker") as mock_trip:
        whatsapp_webhook._log_delivery_statuses(_status_value(False))

    mock_trip.assert_not_called()


def test_tripping_the_breaker_pauses_once_and_alerts_once():
    from contextlib import contextmanager

    state = {"paused": False, "pauses": 0}

    @contextmanager
    def _fake_get_session():
        yield object()

    def _fake_is_paused(_session):
        return state["paused"]

    def _fake_pause(_session, reason):
        state["paused"] = True
        state["pauses"] += 1
        assert "marketing" in reason

    with (
        patch.object(whatsapp_webhook, "get_session", _fake_get_session),
        patch.object(whatsapp_webhook.whatsapp_guard, "is_paused", _fake_is_paused),
        patch.object(whatsapp_webhook.whatsapp_guard, "pause", _fake_pause),
        patch.object(whatsapp_webhook, "alert_owner") as mock_alert,
    ):
        whatsapp_webhook._trip_billing_breaker("marketing", "PMP", "regular")
        whatsapp_webhook._trip_billing_breaker("marketing", "PMP", "regular")

    assert state["pauses"] == 1
    mock_alert.assert_called_once()


# --- the inbound timestamp is Meta's, never "now" for a late redelivery ---


def test_message_sent_at_reads_metas_epoch_timestamp():
    assert whatsapp_webhook._message_sent_at({"timestamp": "1790930400"}) == dt.datetime(
        2026, 10, 2, 8, 40, tzinfo=dt.timezone.utc
    )
    assert whatsapp_webhook._message_sent_at({}) is None
    assert whatsapp_webhook._message_sent_at({"timestamp": "garbage"}) is None


def test_a_late_redelivery_of_an_old_message_cannot_make_the_window_look_fresh():
    user = _wa_user(whatsapp_last_inbound_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=40))
    old_message_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=30)
    with _patch_session(_WebhookSession(user)):
        whatsapp_webhook._touch_inbound_sync("9725500000", old_message_time)

    assert whatsapp_window.window_open(user.whatsapp_last_inbound_at) is False


def test_the_stamp_never_moves_backwards():
    newer = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    user = _wa_user(whatsapp_last_inbound_at=newer)
    with _patch_session(_WebhookSession(user)):
        whatsapp_webhook._touch_inbound_sync("9725500000", newer - dt.timedelta(hours=5))

    assert user.whatsapp_last_inbound_at == newer


# --- cost guard backstop ---


def test_cost_guard_sums_pricing_analytics_cost():
    import whatsapp_cost_guard

    payload = {"pricing_analytics": {"data": [{"data_points": [{"cost": 0}, {"cost": 0.0353}, {"cost": "0.1"}]}]}}
    assert whatsapp_cost_guard.total_cost(payload) == pytest.approx(0.1353)
    assert whatsapp_cost_guard.total_cost({}) == 0.0


def test_cost_guard_pauses_and_alerts_when_any_cost_appears(monkeypatch):
    import whatsapp_cost_guard

    monkeypatch.setenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "1")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    flags = {}
    with (
        patch.object(whatsapp_cost_guard.whatsapp_guard, "get_flag", lambda s, k: flags.get(k)),
        patch.object(whatsapp_cost_guard.whatsapp_guard, "set_flag", lambda s, k, v: flags.__setitem__(k, v)),
        patch.object(whatsapp_cost_guard.whatsapp_guard, "is_paused", lambda s: bool(flags.get("whatsapp_paused"))),
        patch.object(whatsapp_cost_guard, "_fetch_cost", return_value=0.0353),
        patch.object(whatsapp_cost_guard, "alert_owner") as mock_alert,
    ):
        result = whatsapp_cost_guard.run_cost_guard(object())

    assert result == {"whatsapp_cost_alarm": 1}
    assert flags["whatsapp_paused"]
    mock_alert.assert_called_once()


def test_cost_guard_stays_quiet_at_zero_cost_and_ignores_analytics_errors(monkeypatch):
    import whatsapp_cost_guard

    monkeypatch.setenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "1")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    flags = {}
    common = (
        patch.object(whatsapp_cost_guard.whatsapp_guard, "get_flag", lambda s, k: flags.get(k)),
        patch.object(whatsapp_cost_guard.whatsapp_guard, "set_flag", lambda s, k, v: flags.__setitem__(k, v)),
        patch.object(whatsapp_cost_guard, "alert_owner"),
    )
    with common[0], common[1], common[2], patch.object(whatsapp_cost_guard, "_fetch_cost", return_value=0.0):
        assert whatsapp_cost_guard.run_cost_guard(object()) == {"whatsapp_cost_checked": 1}
    assert "whatsapp_paused" not in flags

    flags.clear()
    with common[0], common[1], common[2], patch.object(whatsapp_cost_guard, "_fetch_cost", return_value=None):
        assert whatsapp_cost_guard.run_cost_guard(object()) == {}
    assert "whatsapp_paused" not in flags


def test_cost_guard_is_throttled_to_once_per_few_hours(monkeypatch):
    import whatsapp_cost_guard

    monkeypatch.setenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "1")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    recent = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=30)).isoformat()
    with (
        patch.object(whatsapp_cost_guard.whatsapp_guard, "get_flag", lambda s, k: recent),
        patch.object(whatsapp_cost_guard, "_fetch_cost") as mock_fetch,
    ):
        assert whatsapp_cost_guard.run_cost_guard(object()) == {}

    mock_fetch.assert_not_called()


# --- static guarantee: nothing in the code base can build a template message ---


def test_no_production_code_can_send_a_whatsapp_template():
    import re

    root = Path(__file__).resolve().parent.parent
    offenders = []
    for folder in ("common", "scraper", "website", "bot"):
        for path in (root / folder).rglob("*.py"):
            text = path.read_text()
            if re.search(r"send_template_message|\"type\":\s*\"template\"", text) and path.name != "whatsapp_client.py":
                offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_a_failed_send_never_logs_the_recipients_phone_number(monkeypatch, caplog):
    """The repo and its Actions logs are public: a log line carrying the recipient leaked the owner's
    number once (2026-10-02)."""
    import httpx

    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "t")
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "1")
    with patch.object(whatsapp_client._http_client, "post", side_effect=httpx.ConnectError("boom")):
        with caplog.at_level("ERROR"):
            assert whatsapp_client.send_text_message("972506960111", "hi") is False
    assert "972506960111" not in caplog.text

    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN")
    with caplog.at_level("ERROR"):
        whatsapp_client.send_text_message("972506960111", "hi")
    assert "972506960111" not in caplog.text


def test_listing_photo_route_builds_caches_and_404s_unknown_listings():
    import importlib.util

    from fastapi.testclient import TestClient

    spec = importlib.util.spec_from_file_location(
        "website_main_photo", Path(__file__).resolve().parent.parent / "website" / "main.py"
    )
    website_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(website_main)

    from contextlib import contextmanager

    rows = {7: ["u1", "u2"]}

    @contextmanager
    def _fake_get_session():
        yield SimpleNamespace(
            execute=lambda query: SimpleNamespace(first=lambda: None if not rows else (rows[7],))
        )

    calls = []
    client = TestClient(website_main.app, follow_redirects=False)
    with (
        patch.object(website_main, "get_session", _fake_get_session),
        patch.object(
            website_main, "get_listing_photo_jpeg_bytes", lambda urls: calls.append(urls) or b"jpeg-bytes"
        ),
    ):
        first = client.get("/media/listing/7.jpg")
        second = client.get("/media/listing/7.jpg")
        rows.clear()
        missing = client.get("/media/listing/999.jpg")

    assert first.status_code == 200 and first.content == b"jpeg-bytes"
    assert first.headers["content-type"] == "image/jpeg"
    assert second.content == b"jpeg-bytes"
    assert calls == [["u1", "u2"]]  # built once, then served from the cache
    assert missing.status_code == 404


def test_missed_digest_only_covers_listings_first_seen_since_the_users_previous_message():
    """The user's own scenario: away for 48h, then taps. They get what appeared in those 48h."""
    from todira_common import listing_matches

    since = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.timezone.utc)
    old = SimpleNamespace(id=1, first_seen_at=since - dt.timedelta(hours=1))
    new_a = SimpleNamespace(id=2, first_seen_at=since + dt.timedelta(hours=1))
    new_b = SimpleNamespace(id=3, first_seen_at=since + dt.timedelta(hours=30))
    already_shown = SimpleNamespace(id=4, first_seen_at=since + dt.timedelta(hours=2))
    added = []

    class _Session:
        def scalars(self, query):
            return [4]  # ids already shown

        def add(self, row):
            added.append(row.listing_id)

    with patch.object(
        listing_matches, "find_matching_listings", return_value=[old, new_a, new_b, already_shown]
    ):
        total, shown = listing_matches.find_new_matches_to_show(
            _Session(), 1, SimpleNamespace(), since=since
        )

    assert total == 4
    assert [m.id for m in shown] == [2, 3]
    assert added == [2, 3]  # only these are marked shown; the older one stays unseen


def test_missed_digest_passes_the_cutoff_to_the_matcher():
    user = _wa_user()
    seen = {}

    def _fake_find(session, user_id, filter_row, limit=None, since=None):
        seen["since"] = since
        return 5, [object()]

    with (
        _patch_session(_WebhookSession(user, filter_row=SimpleNamespace(id=1))),
        patch.object(whatsapp_webhook, "find_new_matches_to_show", _fake_find),
        patch.object(whatsapp_webhook.whatsapp_client, "send_text_message"),
    ):
        whatsapp_webhook._send_missed_digest_sync("9725500000", _SINCE)

    assert seen["since"] == _SINCE


def test_a_new_users_first_message_opens_their_window_even_though_the_row_is_created_mid_message():
    """Signup: the user sends their link code (or first message). Their row only gets the phone
    number / is created while this message is handled, so the stamp that counts is the one taken
    AFTER handling (the `finally`) - this pins that it happens even when the handler returns early."""
    message = {"id": "m1", "from": "9725500000", "type": "text", "text": {"body": "ref_abc123"}, "timestamp": "1790930400"}
    with (
        patch.object(whatsapp_webhook, "_already_processed", return_value=False),
        patch.object(whatsapp_webhook, "_touch_inbound_safely", return_value=None) as mock_touch,
        patch.object(whatsapp_webhook, "_try_link_code_sync", return_value=True),
    ):
        whatsapp_webhook._process_payload_sync(_payload(message))

    assert mock_touch.call_count == 2
    assert mock_touch.call_args_list[-1].args[1] == dt.datetime(2026, 10, 2, 8, 40, tzinfo=dt.timezone.utc)

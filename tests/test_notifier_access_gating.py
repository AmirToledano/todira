"""Tests for scraper/notifier.py's 2026-09-05 access gating — the proactive "new match" push
must lock the description/link for a lite/expired user exactly like the bot's own on-demand
handlers (dorin_common/cards.py's format_caption), not just show everything to everyone.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import notifier

_NOW = dt.datetime.now(dt.timezone.utc)


def _user(**overrides):
    defaults = dict(
        id=1,
        telegram_user_id=555,
        free_access_granted=False,
        trial_ends_at=_NOW - dt.timedelta(days=1),
        paid_until=None,
        is_active=True,
        notifications_enabled=True,
        whatsapp_phone_number=None,
        whatsapp_notifications_opted_in=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_has_access_for_expired_user_is_false():
    assert notifier._has_access_for(_user()) is False


def test_has_access_for_user_within_trial_is_true():
    assert notifier._has_access_for(_user(trial_ends_at=_NOW + dt.timedelta(days=1))) is True


def test_has_access_for_owner_is_true_even_if_expired():
    with patch.object(notifier, "OWNER_TELEGRAM_USER_ID", "555"):
        assert notifier._has_access_for(_user(telegram_user_id=555)) is True


def test_notify_new_matches_passes_has_access_false_for_an_expired_user():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user()
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_format.assert_called_once()
    _, kwargs = mock_format.call_args
    assert kwargs["has_access"] is False
    assert kwargs["upgrade_url"] == f"{notifier.WEBSITE_URL}/upgrade?uid=555"


def test_notify_new_matches_passes_has_access_true_for_a_trial_user():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(trial_ends_at=_NOW + dt.timedelta(days=2))
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_new_matches(bot, session, listing))

    assert mock_format.call_args.kwargs["has_access"] is True


# --- _maybe_fetch_description (2026-09-05, Bright Data on-demand enrichment) — answers the
# owner's own sequencing question: fetch only after matching is done, and only when at least one
# recipient about to be notified is a paying user.


def test_maybe_fetch_description_skips_when_not_configured():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1")
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: False),
        patch.object(notifier.bright_data_client, "fetch_listing_description") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_skips_when_already_cached():
    listing = SimpleNamespace(description="כבר יש תיאור", url="https://yad2.co.il/item/1")
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_listing_description") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_skips_when_no_recipient_is_paying():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1")
    session = SimpleNamespace(commit=lambda: None)
    free_users = [_user(), _user(id=2, telegram_user_id=556)]  # both expired trial, no payment
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_listing_description") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, free_users))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_fetches_and_caches_when_a_recipient_is_paying():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1")
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    recipients = [_user(), _user(id=2, telegram_user_id=556, trial_ends_at=_NOW + dt.timedelta(days=1))]

    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(
            notifier.bright_data_client, "fetch_listing_description", lambda url: "תיאור אמיתי"
        ),
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, recipients))

    assert listing.description == "תיאור אמיתי"
    assert committed == [True]


def test_maybe_fetch_description_does_not_cache_on_fetch_failure():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1")
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    recipients = [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]

    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_listing_description", lambda url: None),
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, recipients))

    assert listing.description is None
    assert committed == []


def test_notify_new_matches_skips_a_user_with_no_telegram_id():
    """2026-09-05 real gap found while auditing today's standalone-Google-account feature: push
    notifications are Telegram-only (no WhatsApp send path exists yet — see this module's own
    docstring), but the recipient query never filtered for telegram_user_id at all. A Google-only
    or WhatsApp-only user (both legitimately telegram_user_id=None) would have hit
    send_listing_card(bot, None, ...) on every single matching listing, forever — never a crash
    (send_listing_card catches TelegramError), but a wasted API call + log noise every time,
    since a failed send never writes the SentNotification row that would otherwise remember
    "already tried" this listing."""
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(telegram_user_id=None)
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_send,
    ):
        mock_format.return_value = "caption"
        matched, sent = asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_send.assert_not_awaited()
    mock_format.assert_not_called()
    assert matched == 1  # still counted as a real filter match, just nothing to send to
    assert sent == 0


def test_notify_price_change_skips_a_user_with_no_telegram_id():
    listing = SimpleNamespace(id=10, price=4000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(telegram_user_id=None)
    session = SimpleNamespace(
        scalars=lambda stmt: [1],
        get=lambda model, pk: user,
        scalar=lambda stmt: filter_row,
        add=lambda obj: None,
        commit=lambda: None,
    )
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_send,
    ):
        mock_format.return_value = "caption"
        sent = asyncio.run(notifier._notify_price_change(bot, session, listing, old_price=5000))

    mock_send.assert_not_awaited()
    assert sent == 0


def test_notify_price_change_also_passes_has_access():
    listing = SimpleNamespace(id=10, price=4000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user()
    session = SimpleNamespace(
        scalars=lambda stmt: [1],
        get=lambda model, pk: user,
        scalar=lambda stmt: filter_row,
        add=lambda obj: None,
        commit=lambda: None,
    )
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_price_change(bot, session, listing, old_price=5000))

    kwargs = mock_format.call_args.kwargs
    assert kwargs["has_access"] is False
    assert kwargs["price_change_from"] == 5000


# --- Proactive WhatsApp Message Template push (2026-09-08) ---


def test_whatsapp_eligible_false_when_template_not_configured():
    user = _user(telegram_user_id=None, whatsapp_phone_number="9725500000", whatsapp_notifications_opted_in=True)
    with patch.object(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME", None):
        assert notifier._whatsapp_eligible(user) is False


def test_whatsapp_eligible_false_when_no_phone_number():
    user = _user(telegram_user_id=None, whatsapp_phone_number=None, whatsapp_notifications_opted_in=True)
    with patch.object(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME", "new_listing_match"):
        assert notifier._whatsapp_eligible(user) is False


def test_whatsapp_eligible_false_when_not_opted_in():
    user = _user(telegram_user_id=None, whatsapp_phone_number="9725500000", whatsapp_notifications_opted_in=False)
    with patch.object(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME", "new_listing_match"):
        assert notifier._whatsapp_eligible(user) is False


def test_whatsapp_eligible_true_when_all_three_conditions_met():
    user = _user(telegram_user_id=None, whatsapp_phone_number="9725500000", whatsapp_notifications_opted_in=True)
    with patch.object(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME", "new_listing_match"):
        assert notifier._whatsapp_eligible(user) is True


def test_whatsapp_template_param_collapses_whitespace():
    assert notifier._whatsapp_template_param("רוטשילד   \n  תל אביב") == "רוטשילד תל אביב"


def test_whatsapp_template_param_truncates_long_values():
    long_value = "א" * 400
    result = notifier._whatsapp_template_param(long_value, max_length=10)
    assert result == "א" * 9 + "…"
    assert len(result) == 10


def test_send_whatsapp_match_template_builds_expected_params():
    user = _user(whatsapp_phone_number="9725500000")
    listing = SimpleNamespace(
        street="רוטשילד", neighborhood=None, city="תל אביב יפו", rooms=3.0, price=5500,
    )
    with patch.object(
        notifier.whatsapp_client, "send_template_message", return_value=True
    ) as mock_send, patch.object(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME", "new_listing_match"):
        assert notifier._send_whatsapp_match_template(user, listing) is True

    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert args[0] == "9725500000"
    assert kwargs["template_name"] == "new_listing_match"
    assert kwargs["language_code"] == notifier.WHATSAPP_MATCH_TEMPLATE_LANGUAGE
    assert kwargs["body_params"] == ["רוטשילד", "3", "5,500"]


def test_send_whatsapp_match_template_falls_back_to_city_when_no_street():
    user = _user(whatsapp_phone_number="9725500000")
    listing = SimpleNamespace(street=None, neighborhood=None, city="חיפה", rooms=None, price=None)
    with patch.object(notifier.whatsapp_client, "send_template_message", return_value=True) as mock_send:
        notifier._send_whatsapp_match_template(user, listing)

    body_params = mock_send.call_args.kwargs["body_params"]
    assert body_params[0] == "חיפה"
    assert body_params[1] == "-"
    assert body_params[2] == "-"


def test_notify_new_matches_sends_via_whatsapp_for_whatsapp_only_opted_in_user():
    """A user with no Telegram link at all, but a linked + opted-in WhatsApp number and a real
    template configured, must now actually get pushed — this is the whole point of the feature,
    unlike test_notify_new_matches_skips_a_user_with_no_telegram_id above (opted-out/not-
    configured case, still correctly skipped)."""
    listing = SimpleNamespace(id=10, price=5000, description=None, street="רוטשילד", neighborhood=None, city="תל אביב", rooms=3.0)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(telegram_user_id=None, whatsapp_phone_number="9725500000", whatsapp_notifications_opted_in=True)
    added = []
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: added.append(obj), commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME", "new_listing_match"),
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_telegram_send,
        patch.object(notifier.whatsapp_client, "send_template_message", return_value=True) as mock_wa_send,
        patch.object(notifier, "WHATSAPP_SEND_DELAY_SECONDS", 0),
    ):
        matched, sent = asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_telegram_send.assert_not_awaited()
    mock_wa_send.assert_called_once()
    assert matched == 1
    assert sent == 1
    assert len(added) == 1
    assert added[0].reason == notifier.NotificationReason.NEW


def test_notify_new_matches_sends_via_both_channels_when_linked_to_both():
    listing = SimpleNamespace(id=10, price=5000, description=None, street="רוטשילד", neighborhood=None, city="תל אביב", rooms=3.0)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(telegram_user_id=555, whatsapp_phone_number="9725500000", whatsapp_notifications_opted_in=True)
    added = []
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: added.append(obj), commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME", "new_listing_match"),
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption", return_value="caption"),
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_telegram_send,
        patch.object(notifier.whatsapp_client, "send_template_message", return_value=True) as mock_wa_send,
        patch.object(notifier, "SEND_DELAY_SECONDS", 0),
        patch.object(notifier, "WHATSAPP_SEND_DELAY_SECONDS", 0),
    ):
        matched, sent = asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_telegram_send.assert_awaited_once()
    mock_wa_send.assert_called_once()
    assert sent == 1  # one SentNotification row even though both channels fired
    assert len(added) == 1


def test_notify_new_matches_still_skips_whatsapp_only_user_when_not_opted_in():
    """Same as test_notify_new_matches_skips_a_user_with_no_telegram_id, but explicit about the
    reason: a linked WhatsApp number alone is NOT consent — see User.whatsapp_notifications_
    opted_in's own docstring."""
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user(telegram_user_id=None, whatsapp_phone_number="9725500000", whatsapp_notifications_opted_in=False)
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME", "new_listing_match"),
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier.whatsapp_client, "send_template_message") as mock_wa_send,
    ):
        matched, sent = asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_wa_send.assert_not_called()
    assert matched == 1
    assert sent == 0

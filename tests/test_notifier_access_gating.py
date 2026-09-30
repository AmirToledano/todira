"""Tests for scraper/notifier.py's 2026-09-05 access gating — the proactive "new match" push
must lock the description/link for a lite/expired user exactly like the bot's own on-demand
handlers (todira_common/cards.py's format_caption), not just show everything to everyone.
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
from todira_common.enums import Source

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
        language="he",
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
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1", source=Source.YAD2)
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: False),
        patch.object(notifier.bright_data_client, "fetch_yad2_description_via_web_unlocker") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_skips_when_already_cached():
    listing = SimpleNamespace(description="כבר יש תיאור", url="https://yad2.co.il/item/1", source=Source.YAD2)
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_yad2_description_via_web_unlocker") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_skips_when_no_recipient_is_paying():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1", source=Source.YAD2)
    session = SimpleNamespace(commit=lambda: None)
    free_users = [_user(), _user(id=2, telegram_user_id=556)]  # both expired trial, no payment
    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_yad2_description_via_web_unlocker") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, free_users))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_fetches_and_caches_when_a_recipient_is_paying():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1", source=Source.YAD2)
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    recipients = [_user(), _user(id=2, telegram_user_id=556, trial_ends_at=_NOW + dt.timedelta(days=1))]

    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(
            notifier.bright_data_client, "fetch_yad2_description_via_web_unlocker", lambda url: "תיאור אמיתי"
        ),
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, recipients))

    assert listing.description == "תיאור אמיתי"
    assert committed == [True]


def test_maybe_fetch_description_does_not_cache_on_fetch_failure():
    listing = SimpleNamespace(description=None, url="https://yad2.co.il/item/1", source=Source.YAD2)
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    recipients = [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]

    with (
        patch.object(notifier.bright_data_client, "is_configured", lambda: True),
        patch.object(notifier.bright_data_client, "fetch_yad2_description_via_web_unlocker", lambda url: None),
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, recipients))

    assert listing.description is None
    assert committed == []


def test_maybe_fetch_description_skips_for_non_yad2_source(monkeypatch):
    # 2026-09-13: real bug found via a real production Telegram send — this Bright Data DCA
    # collector is built specifically to parse a YAD2 listing detail page's DOM (see
    # bright_data_client.py's own module docstring); pointing it at a Komo/Homeless URL gets
    # nonsense, not real enrichment. scraper/main.py's own _enrich_new_listings_via_bright_data
    # already had this scoping — this call site was simply missed.
    for source in (Source.KOMO, Source.HOMELESS):
        listing = SimpleNamespace(description=None, url="https://komo.co.il/item/1", source=source)
        session = SimpleNamespace(commit=lambda: None)
        with (
            patch.object(notifier.bright_data_client, "is_configured", lambda: True),
            patch.object(notifier.bright_data_client, "fetch_yad2_description_via_web_unlocker") as mock_fetch,
        ):
            asyncio.run(
                notifier._maybe_fetch_description(
                    session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]
                )
            )
        mock_fetch.assert_not_called()


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
        matched, sent, _newly_notified = asyncio.run(notifier._notify_new_matches(bot, session, listing))

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


def test_notify_price_change_excludes_a_user_just_notified_as_new_matches_in_this_same_run():
    """2026-09-25 real bug fix: run_notifications calls _notify_new_matches for this same listing
    right before _notify_price_change, in the same price-change-event iteration. A user whose
    filter didn't match the OLD price but does the NEW one gets a genuine 'new match' notification
    there, with its own SentNotification(reason=NEW) row committed immediately — the query
    _notify_price_change runs (SELECT user_id WHERE reason=NEW) would then find that brand-new row
    an instant later and wrongly treat them as "previously notified," sending a SECOND, redundant
    'price dropped!' card for a listing they were only just told about. exclude_user_ids (populated
    from that same _notify_new_matches call's own return value) must keep this from happening."""
    listing = SimpleNamespace(id=10, price=4000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    user = _user()
    session = SimpleNamespace(
        # Both user_id 1 (the just-notified-as-new user) and user_id 2 (a genuinely
        # previously-notified user) come back from the reason=NEW query.
        scalars=lambda stmt: [1, 2],
        get=lambda model, pk: user,
        scalar=lambda stmt: filter_row,
        add=lambda obj: None,
        commit=lambda: None,
    )
    bot = SimpleNamespace()

    with (
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption", return_value="caption"),
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_send,
    ):
        sent = asyncio.run(
            notifier._notify_price_change(
                bot, session, listing, old_price=5000, exclude_user_ids={1}
            )
        )

    # Only user_id 2 (genuinely previously notified) gets the price-change card — user_id 1
    # (just sent a 'new match' card moments ago in this same run) is correctly skipped.
    mock_send.assert_called_once()
    assert sent == 1


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
        matched, sent, _newly_notified = asyncio.run(notifier._notify_new_matches(bot, session, listing))

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
        matched, sent, _newly_notified = asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_telegram_send.assert_awaited_once()
    mock_wa_send.assert_called_once()
    assert sent == 1  # one SentNotification row even though both channels fired
    assert len(added) == 1


def test_notify_new_matches_sends_whatsapp_for_every_matching_listing_no_cap():
    """2026-09-27 through 2026-09-30: a real owner report about WhatsApp flooding led to a
    per-run cap (at most one real WhatsApp send per user per scrape run, via a shared
    whatsapp_sent_user_ids set) — removed 2026-09-30 after a second real owner report the other
    direction: the cap's own claim that skipped listings "get picked up on the next run instead"
    was false whenever the same user also had Telegram linked (the common case), since Telegram
    sends uncapped and immediately writes the shared, channel-agnostic SentNotification row that
    _already_notified checks — those listings were silently dropped from WhatsApp forever, not
    deferred. Explicit owner call: WhatsApp is a full channel like Telegram and the website now,
    with no artificial cap — this call (no whatsapp_sent_user_ids arg exists anymore) always
    attempts the send for a matching, opted-in user."""
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
        patch.object(notifier.whatsapp_client, "send_template_message", return_value=True) as mock_wa_send,
        patch.object(notifier, "WHATSAPP_SEND_DELAY_SECONDS", 0),
    ):
        matched, sent, newly_notified = asyncio.run(
            notifier._notify_new_matches(bot, session, listing)
        )

    mock_wa_send.assert_called_once()
    assert matched == 1
    assert sent == 1
    assert len(added) == 1
    assert newly_notified == {1}


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
        matched, sent, _newly_notified = asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_wa_send.assert_not_called()
    assert matched == 1
    assert sent == 0


# --- The rich, Dorin-style per-listing card (2026-09-27: "חובה לעלות תמונות של המודעות ביחד עם כל
# מה שרשמת" — a real owner requirement, not optional) — WHATSAPP_RICH_MATCH_TEMPLATE_NAME unset
# (the default) means every test above is completely unaffected; these tests explicitly set it. ---


def _rich_listing(**overrides):
    defaults = dict(
        id=10, street="רוטשילד", neighborhood=None, city="תל אביב יפו", price=5500, rooms=3.0,
        size_sqm=65, floor=2, move_in_date=None, description="דירה משופצת ומוארת", image_urls=["u1", "u2"],
        has_parking=None, has_elevator=None, has_balcony=None, pets_allowed=None, is_renovated=None,
        is_roommate_friendly=None, safe_room_type=None, furniture=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_send_whatsapp_match_template_dispatches_to_rich_when_configured():
    user = _user(whatsapp_phone_number="9725500000")
    listing = _rich_listing()
    with (
        patch.object(notifier, "WHATSAPP_RICH_MATCH_TEMPLATE_NAME", "new_listing_match_rich"),
        patch.object(notifier, "_send_whatsapp_rich_match_template", return_value=True) as mock_rich,
        patch.object(notifier.whatsapp_client, "send_template_message") as mock_plain,
    ):
        assert notifier._send_whatsapp_match_template(user, listing) is True

    mock_rich.assert_called_once_with(user, listing)
    mock_plain.assert_not_called()


def test_send_whatsapp_rich_match_template_builds_all_8_fields_plus_header_and_button():
    user = _user(whatsapp_phone_number="9725500000")
    listing = _rich_listing()
    with (
        patch.object(notifier, "WHATSAPP_RICH_MATCH_TEMPLATE_NAME", "new_listing_match_rich"),
        patch.object(notifier, "get_listing_photo_jpeg_bytes", return_value=b"jpeg-bytes") as mock_photo,
        patch.object(notifier.whatsapp_client, "upload_media", return_value="media-id-123") as mock_upload,
        patch.object(notifier.whatsapp_client, "send_template_message", return_value=True) as mock_send,
        patch.object(notifier, "generate_wid_token", return_value="signed-token"),
    ):
        assert notifier._send_whatsapp_rich_match_template(user, listing) is True

    mock_photo.assert_called_once_with(listing.image_urls)
    mock_upload.assert_called_once_with(b"jpeg-bytes")
    args, kwargs = mock_send.call_args
    assert args[0] == "9725500000"
    assert kwargs["template_name"] == "new_listing_match_rich"
    assert kwargs["body_params"][0] == "רוטשילד"
    assert kwargs["body_params"][1] == "5,500"
    assert kwargs["body_params"][2] == "3"
    assert kwargs["body_params"][3] == "65"
    assert kwargs["body_params"][4] == "2"
    assert kwargs["body_params"][5] == "-"  # no move_in_date on this fixture
    assert kwargs["body_params"][7] == "דירה משופצת ומוארת"
    assert kwargs["header_image_media_id"] == "media-id-123"
    assert kwargs["button_url_param"] == "10&wid=signed-token"


def test_send_whatsapp_rich_match_template_returns_false_when_upload_fails():
    user = _user(whatsapp_phone_number="9725500000")
    listing = _rich_listing()
    with (
        patch.object(notifier, "get_listing_photo_jpeg_bytes", return_value=b"jpeg-bytes"),
        patch.object(notifier.whatsapp_client, "upload_media", return_value=None),
        patch.object(notifier.whatsapp_client, "send_template_message") as mock_send,
    ):
        assert notifier._send_whatsapp_rich_match_template(user, listing) is False

    mock_send.assert_not_called()


def test_send_whatsapp_rich_match_template_missing_fields_render_as_dashes():
    user = _user(whatsapp_phone_number="9725500000")
    listing = _rich_listing(
        street=None, neighborhood=None, city="חיפה", price=None, rooms=None, size_sqm=None,
        floor=None, description=None,
    )
    with (
        patch.object(notifier, "get_listing_photo_jpeg_bytes", return_value=b"jpeg-bytes"),
        patch.object(notifier.whatsapp_client, "upload_media", return_value="media-id-123"),
        patch.object(notifier.whatsapp_client, "send_template_message", return_value=True) as mock_send,
    ):
        notifier._send_whatsapp_rich_match_template(user, listing)

    body_params = mock_send.call_args.kwargs["body_params"]
    assert body_params == ["חיפה", "-", "-", "-", "-", "-", "-", "-"]

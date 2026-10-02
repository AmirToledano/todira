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


# --- Zero-cost WhatsApp push (2026-10-02): free-form message, only inside the 24h window ---

_OPEN_WINDOW = _NOW - dt.timedelta(hours=3)
_CLOSED_WINDOW = _NOW - dt.timedelta(hours=30)


def _wa_user(**overrides):
    defaults = dict(
        telegram_user_id=None,
        whatsapp_phone_number="9725500000",
        whatsapp_notifications_opted_in=True,
        whatsapp_last_inbound_at=_OPEN_WINDOW,
    )
    defaults.update(overrides)
    return _user(**defaults)


def test_whatsapp_eligible_true_when_linked_opted_in_and_window_open():
    assert notifier._whatsapp_eligible(_wa_user()) is True


def test_whatsapp_eligible_false_when_window_closed():
    assert notifier._whatsapp_eligible(_wa_user(whatsapp_last_inbound_at=_CLOSED_WINDOW)) is False


def test_whatsapp_eligible_false_when_never_heard_from_user():
    assert notifier._whatsapp_eligible(_wa_user(whatsapp_last_inbound_at=None)) is False


def test_whatsapp_eligible_false_when_no_phone_number():
    assert notifier._whatsapp_eligible(_wa_user(whatsapp_phone_number=None)) is False


def test_whatsapp_eligible_false_when_not_opted_in():
    assert notifier._whatsapp_eligible(_wa_user(whatsapp_notifications_opted_in=False)) is False


def test_notifier_has_no_paid_template_path_left():
    """The owner's rule (2026-10-02): never pay for WhatsApp. No template sender may exist here."""
    assert not hasattr(notifier, "_send_whatsapp_match_template")
    assert not hasattr(notifier, "_send_whatsapp_rich_match_template")
    assert not hasattr(notifier, "WHATSAPP_MATCH_TEMPLATE_NAME")


def _rich_listing(**overrides):
    defaults = dict(
        id=10, street="רוטשילד", neighborhood=None, city="תל אביב יפו", price=5500, rooms=3.0,
        size_sqm=65, floor=2, floor_total=None, move_in_date=None, is_broker_listing=False, source="yad2", description="דירה משופצת ומוארת",
        image_urls=["u1", "u2"], lat=None, lon=None, deal_type="rent", url="https://example.com/x",
        has_parking=None, has_elevator=None, has_balcony=None, pets_allowed=None, is_renovated=None,
        is_roommate_friendly=None, safe_room_type=None, furniture=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_send_whatsapp_match_message_sends_photo_text_and_view_button():
    user = _wa_user(trial_ends_at=_NOW + dt.timedelta(days=1))
    listing = _rich_listing()
    with (
        patch.object(notifier, "get_listing_photo_jpeg_bytes", return_value=b"jpeg") as mock_photo,
        patch.object(notifier.whatsapp_client, "upload_media", return_value="media-1") as mock_upload,
        patch.object(notifier.whatsapp_client, "send_image_cta_message", return_value=True) as mock_send,
        patch.object(notifier.whatsapp_client, "send_template_message") as mock_template,
        patch.object(notifier, "generate_wid_token", return_value="signed"),
    ):
        assert notifier._send_whatsapp_match_message(user, listing) is True

    mock_photo.assert_called_once_with(listing.image_urls)
    mock_upload.assert_called_once_with(b"jpeg")
    mock_template.assert_not_called()
    args, kwargs = mock_send.call_args
    assert args[0] == "9725500000"
    assert kwargs["media_id"] == "media-1"
    assert kwargs["url"].endswith("/apartments?wid=signed&listing=10")
    assert "רוטשילד" in kwargs["body"]
    assert "דירה משופצת ומוארת" in kwargs["body"]
    assert len(kwargs["body"]) <= notifier.WHATSAPP_INTERACTIVE_BODY_LIMIT


def test_send_whatsapp_match_message_button_goes_to_upgrade_for_user_without_access():
    user = _wa_user()  # trial expired, no paid_until -> no access
    with (
        patch.object(notifier, "get_listing_photo_jpeg_bytes", return_value=b"jpeg"),
        patch.object(notifier.whatsapp_client, "upload_media", return_value="media-1"),
        patch.object(notifier.whatsapp_client, "send_image_cta_message", return_value=True) as mock_send,
        patch.object(notifier, "generate_wid_token", return_value="signed"),
    ):
        notifier._send_whatsapp_match_message(user, _rich_listing())

    assert "/upgrade?wid=signed" in mock_send.call_args.kwargs["url"]


def test_send_whatsapp_match_message_returns_false_when_upload_fails():
    with (
        patch.object(notifier, "get_listing_photo_jpeg_bytes", return_value=b"jpeg"),
        patch.object(notifier.whatsapp_client, "upload_media", return_value=None),
        patch.object(notifier.whatsapp_client, "send_image_cta_message") as mock_send,
    ):
        assert notifier._send_whatsapp_match_message(_wa_user(), _rich_listing()) is False

    mock_send.assert_not_called()


def _run_notify(user, listing):
    filter_row = SimpleNamespace(user_id=1)
    added = []
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: added.append(obj), commit=lambda: None)
    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "format_caption", return_value="caption"),
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)) as mock_telegram,
        patch.object(notifier, "_send_whatsapp_match_message", return_value=True) as mock_wa,
        patch.object(notifier, "SEND_DELAY_SECONDS", 0),
        patch.object(notifier, "WHATSAPP_SEND_DELAY_SECONDS", 0),
    ):
        result = asyncio.run(notifier._notify_new_matches(SimpleNamespace(), session, listing))
    return result, added, mock_telegram, mock_wa


def test_notify_new_matches_sends_via_whatsapp_for_whatsapp_only_user_in_window():
    (matched, sent, newly), added, mock_telegram, mock_wa = _run_notify(_wa_user(), _rich_listing())

    mock_telegram.assert_not_awaited()
    mock_wa.assert_called_once()
    assert (matched, sent) == (1, 1)
    assert len(added) == 1 and added[0].reason == notifier.NotificationReason.NEW
    assert newly == {1}


def test_notify_new_matches_sends_nothing_and_records_nothing_when_window_closed():
    """Window closed = no free message possible = nothing sent AND no SentNotification row, so the
    listing is still unseen and website/whatsapp_webhook.py's digest covers it when they reply."""
    (matched, sent, _newly), added, mock_telegram, mock_wa = _run_notify(
        _wa_user(whatsapp_last_inbound_at=_CLOSED_WINDOW), _rich_listing()
    )

    mock_telegram.assert_not_awaited()
    mock_wa.assert_not_called()
    assert (matched, sent) == (1, 0)
    assert added == []


def test_notify_new_matches_sends_via_both_channels_when_linked_to_both():
    (_m, sent, _n), added, mock_telegram, mock_wa = _run_notify(
        _wa_user(telegram_user_id=555), _rich_listing()
    )

    mock_telegram.assert_awaited_once()
    mock_wa.assert_called_once()
    assert sent == 1  # one SentNotification row even though both channels fired
    assert len(added) == 1


def test_notify_new_matches_telegram_still_works_when_whatsapp_window_closed():
    (_m, sent, _n), added, mock_telegram, mock_wa = _run_notify(
        _wa_user(telegram_user_id=555, whatsapp_last_inbound_at=_CLOSED_WINDOW), _rich_listing()
    )

    mock_telegram.assert_awaited_once()
    mock_wa.assert_not_called()
    assert sent == 1


def test_notify_new_matches_skips_whatsapp_only_user_when_not_opted_in():
    (matched, sent, _n), added, _mock_telegram, mock_wa = _run_notify(
        _wa_user(whatsapp_notifications_opted_in=False), _rich_listing()
    )

    mock_wa.assert_not_called()
    assert (matched, sent) == (1, 0)

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
from todira_common.uid_token import verify_uid_token

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
        patch.object(notifier, "_hidden_by", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_new_matches(bot, session, listing))

    mock_format.assert_called_once()
    _, kwargs = mock_format.call_args
    assert kwargs["has_access"] is False
    assert kwargs["upgrade_url"].startswith(f"{notifier.WEBSITE_URL}/upgrade?t=")
    token = kwargs["upgrade_url"].split("?t=", 1)[1]
    assert verify_uid_token(token) == 555  # a signed link for THIS user, never a bare id


def _captured_format_kwargs(user):
    listing = SimpleNamespace(id=10, price=5000, description=None)
    filter_row = SimpleNamespace(user_id=1)
    session = SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)
    with (
        patch.object(notifier, "_candidate_filters", return_value=[filter_row]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "_hidden_by", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_new_matches(SimpleNamespace(), session, listing))
    return mock_format.call_args.kwargs


def test_new_match_card_tells_an_expired_trial_from_an_expired_subscription():
    """2026-10-09 owner request: the card's footer says WHY the link is locked."""
    assert _captured_format_kwargs(_user())["access_state"] == "trial_ended"
    paid_then_expired = _user(paid_until=_NOW - dt.timedelta(days=2))
    assert _captured_format_kwargs(paid_then_expired)["access_state"] == "subscription_expired"
    assert _captured_format_kwargs(_user(trial_ends_at=_NOW + dt.timedelta(days=1)))["access_state"] == "full"
    with patch.object(notifier, "OWNER_TELEGRAM_USER_ID", "555"):
        assert _captured_format_kwargs(_user(telegram_user_id=555))["access_state"] == "full"


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
        patch.object(notifier, "_hidden_by", return_value=False),
        patch.object(notifier, "format_caption") as mock_format,
        patch.object(notifier, "send_listing_card", AsyncMock(return_value=True)),
    ):
        mock_format.return_value = "caption"
        asyncio.run(notifier._notify_new_matches(bot, session, listing))

    assert mock_format.call_args.kwargs["has_access"] is True


# --- _maybe_fetch_description (2026-09-05 as an on-demand Bright Data fetch for paying recipients only).
# 2026-10-09: now a just-in-time completion of EVERY Yad2 card about to be sent (Yad2's own free item JSON, Gemini as
# backup, todira_common/yad2_detail.py): no access gate, `details_fetched_at` is the "already read" marker.


def _detail_patches(updates, enabled=True):
    return (
        patch.object(notifier.yad2_detail, "is_enabled", lambda: enabled),
        patch.object(notifier.yad2_detail, "fetch_updates", lambda url: updates),
    )


def _yad2_listing(**overrides):
    fields = dict(description=None, details_fetched_at=None, url="https://yad2.co.il/item/1", source=Source.YAD2)
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_maybe_fetch_description_skips_when_no_fetcher_is_enabled():
    listing = _yad2_listing()
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.yad2_detail, "is_enabled", lambda: False),
        patch.object(notifier.yad2_detail, "fetch_updates") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))]))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_skips_when_the_details_were_already_read():
    listing = _yad2_listing(details_fetched_at=_NOW)
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.yad2_detail, "is_enabled", lambda: True),
        patch.object(notifier.yad2_detail, "fetch_updates") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user()]))
    mock_fetch.assert_not_called()


def test_maybe_fetch_description_fetches_even_when_no_recipient_has_access():
    """The card is complete for everyone (the description is shown to every viewer; only the original link is gated)."""
    listing = _yad2_listing()
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    free_users = [_user(), _user(id=2, telegram_user_id=556)]  # both expired trial, no payment
    enabled, fetch = _detail_patches({"description": "תיאור", "floor_total": 5})
    with enabled, fetch:
        asyncio.run(notifier._maybe_fetch_description(session, listing, free_users))
    assert listing.description == "תיאור" and listing.floor_total == 5
    assert listing.details_fetched_at is not None
    assert committed == [True]


def test_maybe_fetch_description_fetches_a_listing_that_has_a_description_but_was_never_read():
    listing = _yad2_listing(description="מהסריקה")
    session = SimpleNamespace(commit=lambda: None)
    enabled, fetch = _detail_patches({"floor_total": 3, "has_parking": True})
    with enabled, fetch:
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user()]))
    assert listing.floor_total == 3 and listing.has_parking is True


def test_maybe_fetch_description_marks_an_empty_answer_as_read():
    """{} = reached, nothing usable (or the ad is gone): recorded so it is never asked about again."""
    listing = _yad2_listing()
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    enabled, fetch = _detail_patches({})
    with enabled, fetch:
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user()]))
    assert listing.details_fetched_at is not None
    assert committed == [True]


def test_maybe_fetch_description_does_nothing_when_there_is_nobody_to_send_to():
    """run_notifications walks ~13,500 retry candidates a run, almost all matching nobody - fetching for them wasted ~700 reads."""
    listing = _yad2_listing()
    session = SimpleNamespace(commit=lambda: None)
    with (
        patch.object(notifier.yad2_detail, "is_enabled", lambda: True),
        patch.object(notifier.yad2_detail, "fetch_updates") as mock_fetch,
    ):
        asyncio.run(notifier._maybe_fetch_description(session, listing, []))
    mock_fetch.assert_not_called()
    assert listing.details_fetched_at is None


def test_notify_new_matches_makes_no_fetch_for_a_listing_nobody_matches():
    listing = SimpleNamespace(id=10, price=5000, description=None)
    session = SimpleNamespace(get=lambda model, pk: None, add=lambda obj: None, commit=lambda: None)
    with (
        patch.object(notifier, "_candidate_filters", return_value=[]),
        patch.object(notifier.yad2_detail, "is_enabled", lambda: True),
        patch.object(notifier.yad2_detail, "fetch_updates") as mock_fetch,
    ):
        asyncio.run(notifier._notify_new_matches(SimpleNamespace(), session, listing))
    mock_fetch.assert_not_called()


def test_notifier_has_no_paid_detail_fetcher_left():
    assert not hasattr(notifier, "fetch_listing_detail_via_web_unlocker")
    assert not hasattr(notifier, "bright_data_client")


def test_maybe_fetch_description_does_not_mark_anything_when_there_is_no_answer():
    listing = _yad2_listing()
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    enabled, fetch = _detail_patches(None)
    with enabled, fetch:
        asyncio.run(notifier._maybe_fetch_description(session, listing, [_user()]))
    assert listing.description is None
    assert listing.details_fetched_at is None
    assert committed == []


def test_maybe_fetch_description_skips_for_non_yad2_source():
    # The Yad2 fetchers are built for a Yad2 listing; Komo/Homeless/Facebook get their details from their own scrapers.
    for source in (Source.KOMO, Source.HOMELESS):
        listing = _yad2_listing(url="https://komo.co.il/item/1", source=source)
        session = SimpleNamespace(commit=lambda: None)
        with (
            patch.object(notifier.yad2_detail, "is_enabled", lambda: True),
            patch.object(notifier.yad2_detail, "fetch_updates") as mock_fetch,
        ):
            asyncio.run(
                notifier._maybe_fetch_description(session, listing, [_user(trial_ends_at=_NOW + dt.timedelta(days=1))])
            )
        mock_fetch.assert_not_called()


def test_notify_new_matches_skips_a_user_with_no_telegram_id():
    """2026-09-05 real gap found while auditing today's standalone-Google-account feature: push
    notifications are Telegram-only, but the recipient query never filtered for telegram_user_id
    at all. A Google-only user (legitimately telegram_user_id=None) would have hit
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
        patch.object(notifier, "_hidden_by", return_value=False),
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
        patch.object(notifier, "_hidden_by", return_value=False),
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
        patch.object(notifier, "_hidden_by", return_value=False),
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
        patch.object(notifier, "_hidden_by", return_value=False),
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


# --- 2026-10-09: the card is completed from the description text just before it is sent -----------------------------------


def _text_listing(**overrides):
    fields = dict(
        description="קומה 2 מתוך 4, חניה, מעלית", text_parsed_at=None, source=Source.KOMO, details_fetched_at=None,
        floor=None, floor_total=None, has_parking=None, has_elevator=None, has_balcony=None, pets_allowed=None,
        is_renovated=None, is_roommate_friendly=None, safe_room_type=None, furniture=None, property_type=None,
        move_in_date=None, move_in_note=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_complete_card_fields_fills_the_empty_columns_from_the_text_and_marks_it_read():
    listing = _text_listing()
    committed = []
    session = SimpleNamespace(commit=lambda: committed.append(True))
    asyncio.run(notifier._complete_card_fields(session, listing, [_user()]))
    assert listing.floor == 2 and listing.floor_total == 4
    assert listing.has_parking is True and listing.has_elevator is True
    assert listing.text_parsed_at is not None
    assert committed == [True]


def test_complete_card_fields_never_overwrites_a_structured_value():
    listing = _text_listing(has_parking=False, floor=3)
    session = SimpleNamespace(commit=lambda: None)
    asyncio.run(notifier._complete_card_fields(session, listing, [_user()]))
    assert listing.has_parking is False and listing.floor == 3
    assert listing.floor_total == 4  # only the empty column is filled


def test_complete_card_fields_does_nothing_without_recipients_or_when_already_read_or_without_text():
    for listing, recipients in (
        (_text_listing(), []),
        (_text_listing(text_parsed_at=_NOW), [_user()]),
        (_text_listing(description=None), [_user()]),
    ):
        committed = []
        session = SimpleNamespace(commit=lambda: committed.append(True))
        asyncio.run(notifier._complete_card_fields(session, listing, recipients))
        assert committed == []
        assert listing.floor is None


def test_complete_card_fields_runs_the_yad2_detail_fetch_first_then_the_text():
    listing = _text_listing(source=Source.YAD2, description=None, url="https://www.yad2.co.il/item/x")
    session = SimpleNamespace(commit=lambda: None)
    enabled, fetch = _detail_patches({"description": "קומה 1 מתוך 3, מרפסת", "has_parking": True})
    with enabled, fetch:
        asyncio.run(notifier._complete_card_fields(session, listing, [_user()]))
    assert listing.has_parking is True  # from the structured record
    assert listing.floor == 1 and listing.floor_total == 3 and listing.has_balcony is True  # from the description text


def test_a_hidden_listing_gets_no_price_alert():
    """2026-10-15 bug: someone who hid an apartment still got "the price dropped" for it."""
    listing = SimpleNamespace(id=10, price=4000, description=None)
    user = _user()
    session = SimpleNamespace(
        scalars=lambda stmt: [1],
        get=lambda model, pk: user,
        scalar=lambda stmt: SimpleNamespace(user_id=1),
        add=lambda obj: None,
        commit=lambda: None,
    )
    send = AsyncMock(return_value=True)

    with (
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "_hidden_by", return_value=True),
        patch.object(notifier, "send_listing_card", send),
    ):
        asyncio.run(notifier._notify_price_change(SimpleNamespace(), session, listing, old_price=5000))

    send.assert_not_called()


def test_retried_listings_reach_one_user_at_most_a_few_times_per_run():
    """2026-10-15: the retry pass could push a week of listings at once to a user whose filter just widened."""
    budget: dict[int, int] = {}
    user = _user()
    sends = AsyncMock(return_value=True)

    def _session():
        return SimpleNamespace(get=lambda model, pk: user, add=lambda obj: None, commit=lambda: None)

    with (
        patch.object(notifier, "_candidate_filters", return_value=[SimpleNamespace(user_id=1)]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "_hidden_by", return_value=False),
        patch.object(notifier, "_complete_card_fields", AsyncMock()),
        patch.object(notifier, "format_caption", return_value="caption"),
        patch.object(notifier, "send_listing_card", sends),
        patch.object(notifier, "SEND_DELAY_SECONDS", 0),
    ):
        for listing_id in range(notifier.RETRY_MAX_PER_USER_PER_RUN + 3):
            listing = SimpleNamespace(id=listing_id, price=4000, description=None)
            asyncio.run(notifier._notify_new_matches(SimpleNamespace(), _session(), listing, per_user_budget=budget))

    assert sends.await_count == notifier.RETRY_MAX_PER_USER_PER_RUN

"""2026-11-02 (growth): keeping trial-ended users. No dashes in bot texts, a truthful "your access ended" /start reply, the
long "access ended" card notice once a day, the invite-a-friend button on locked cards, no check-in for users without
access, and the invite reward when the first search is saved through /filter."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

import checkin  # noqa: E402
import notifier  # noqa: E402
from handlers import filter_conversation, invite  # noqa: E402
from todira_common.access import ACCESS_TRIAL_ENDED  # noqa: E402
from todira_common.bot_strings import BOT_STRINGS, bot_text  # noqa: E402
from todira_common.cards import format_caption, listing_keyboard  # noqa: E402

LANGS = ("he", "en", "ru", "fr", "ar")
_NOW = dt.datetime.now(dt.timezone.utc)


def _listing(**overrides):
    fields = dict(
        id=7, url="https://example.invalid/item/7", source="yad2", deal_type="rent", is_broker_listing=False, rooms=3,
        floor=1, floor_total=4, size_sqm=70, price=6000, move_in_date=None, has_parking=None, has_elevator=None,
        has_balcony=None, pets_allowed=None, is_renovated=None, is_roommate_friendly=None, safe_room_type=None,
        furniture=None, street=None, neighborhood=None, city="חיפה", description=None, image_urls=[],
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_no_bot_string_has_an_em_or_en_dash():
    bad = [(key, lang) for key, entry in BOT_STRINGS.items() for lang, text in entry.items() if "—" in text or "–" in text]
    assert bad == []


def test_renewal_text_is_truthful_and_complete_in_every_language():
    for key in ("start.renewal_needed", "start.renewal_needed_paid"):
        for lang in LANGS:
            raw = BOT_STRINGS[key][lang]
            assert "{upgrade_url}" in raw and "/invite" in raw
            text = bot_text(key, lang, name="Dana", cities_line="", upgrade_url="https://x/upgrade", days=7)
            assert "https://x/upgrade" in text
    he = BOT_STRINGS["start.renewal_needed"]["he"]
    assert "מושהות" not in he and "הסתיימה" in he and "נעול" in he
    assert "paused" not in BOT_STRINGS["start.renewal_needed"]["en"]


def test_card_without_full_notice_shows_only_the_short_lock_line():
    long_notice = bot_text("card.trial_ended_notice", "he")
    kwargs = dict(has_access=False, upgrade_url="https://x/upgrade", lang="he", access_state=ACCESS_TRIAL_ENDED)
    assert long_notice in format_caption(_listing(), **kwargs)
    short = format_caption(_listing(), full_notice=False, **kwargs)
    assert long_notice not in short
    assert bot_text("card.upgrade_to_see_link", "he") in short


def _job(user, has_access=False):
    job = notifier._Send(user=user, listing=_listing(), caption="LONG", lang="he")
    if not has_access:
        job.short_caption = lambda: "SHORT"
        job.invite = True
    return job


def _send(job, had_card_today):
    session = SimpleNamespace(add=lambda row: None, commit=lambda: None)
    send = AsyncMock(return_value=True)
    with (
        patch.object(notifier, "_had_card_today", return_value=had_card_today),
        patch.object(notifier, "send_listing_card", send),
        patch.object(notifier, "SEND_DELAY_SECONDS", 0),
    ):
        asyncio.run(notifier._send_one(SimpleNamespace(), session, job))
    return send.await_args


def test_long_notice_only_on_the_first_card_of_the_day():
    user = SimpleNamespace(id=1, telegram_user_id=555, is_active=True)
    first = _send(_job(user), had_card_today=False)
    later = _send(_job(user), had_card_today=True)
    assert first.args[3] == "LONG" and later.args[3] == "SHORT"
    assert first.kwargs["invite"] is True


def test_user_with_access_keeps_the_normal_card_and_no_invite_button():
    user = SimpleNamespace(id=1, telegram_user_id=555, is_active=True)
    sent = _send(_job(user, has_access=True), had_card_today=True)
    assert sent.args[3] == "LONG" and sent.kwargs["invite"] is False


def test_new_match_for_a_user_without_access_queues_a_short_caption_and_the_invite_button():
    user = SimpleNamespace(
        id=1, telegram_user_id=555, free_access_granted=False, trial_ends_at=_NOW - dt.timedelta(days=1),
        paid_until=None, is_active=True, notifications_enabled=True, language="he",
    )
    session = SimpleNamespace(get=lambda model, pk: user)
    queue: list = []
    with (
        patch.object(notifier, "_candidate_filters", return_value=[SimpleNamespace(user_id=1)]),
        patch.object(notifier, "evaluate", return_value=SimpleNamespace(matched=True)),
        patch.object(notifier, "_already_notified", return_value=False),
        patch.object(notifier, "_hidden_by", return_value=False),
        patch.object(notifier, "_complete_card_fields", AsyncMock()),
        patch.object(notifier, "_below_area_pct", return_value=None),
        patch.object(notifier.alert_hours, "in_window", return_value=True),
    ):
        asyncio.run(notifier._notify_new_matches(SimpleNamespace(), session, _listing(), queue=queue))
    (job,) = queue
    assert job.invite is True
    assert bot_text("card.trial_ended_notice", "he") in job.caption
    assert bot_text("card.trial_ended_notice", "he") not in job.short_caption()


def test_invite_button_on_a_locked_card_matches_the_invite_handler():
    pattern = next(h.pattern for h in invite.build_invite_handlers() if hasattr(h, "pattern"))
    for lang in LANGS:
        buttons = [b for row in listing_keyboard(7, lang, invite=True).inline_keyboard for b in row]
        (button,) = [b for b in buttons if b.callback_data == "invite:show"]
        assert button.text == BOT_STRINGS["card.invite_button"][lang]
        assert re.match(pattern, button.callback_data)
    assert BOT_STRINGS["card.invite_button"]["he"] == "🎁 7 ימים חינם: הזמנת חבר"
    plain = [b.callback_data for row in listing_keyboard(7, "he").inline_keyboard for b in row]
    assert "invite:show" not in plain


def test_checkin_skips_users_without_full_access():
    def user(uid, **access):
        fields = dict(id=uid, telegram_user_id=1000 + uid, free_access_granted=False, trial_ends_at=None, paid_until=None)
        fields.update(access)
        return SimpleNamespace(**fields)

    trial = user(1, trial_ends_at=_NOW + dt.timedelta(days=3))
    ended = user(2, trial_ends_at=_NOW - dt.timedelta(days=3))
    session = SimpleNamespace(
        execute=lambda query: SimpleNamespace(all=lambda: [(trial, 20), (ended, 20)]),
        scalars=lambda query: [],
    )
    with patch.object(checkin.alert_hours, "in_window", return_value=True):
        due = checkin.due_users(session, _NOW)
    assert [u.id for u, _ in due] == [1]


@contextmanager
def _fake_db(existing_filter):
    user = SimpleNamespace(id=9)
    session = SimpleNamespace(scalar=lambda q: existing_filter, add=lambda row: None, commit=lambda: None)

    @contextmanager
    def get_session():
        yield session

    reward = patch.object(filter_conversation.referrals, "reward", return_value=True)
    with (
        patch.object(filter_conversation, "get_session", get_session),
        patch.object(filter_conversation, "get_or_create_user", return_value=user),
        patch.object(filter_conversation, "find_new_matches_to_show", return_value=(3, [])),
        reward as mock_reward,
    ):
        yield mock_reward


def test_first_filter_saved_through_filter_grants_the_invite_reward():
    with _fake_db(existing_filter=None) as mock_reward:
        assert filter_conversation._save_sync(SimpleNamespace(id=5), {"cities": []}) is True
    mock_reward.assert_called_once()


def test_updating_an_existing_filter_does_not_reward():
    with _fake_db(existing_filter=SimpleNamespace()) as mock_reward:
        assert filter_conversation._save_sync(SimpleNamespace(id=5), {"cities": []}) is False
    mock_reward.assert_not_called()


def test_handle_save_sends_the_friend_bonus_note(monkeypatch):
    monkeypatch.setattr(filter_conversation, "_save_sync", lambda *a, **k: True)
    monkeypatch.setattr(filter_conversation, "_count_matches_sync", lambda *a, **k: 0)
    draft = filter_conversation._default_draft()
    message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(edit_message_text=AsyncMock(), message=message)
    update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=555))
    asyncio.run(filter_conversation._handle_save(update, SimpleNamespace(user_data={"draft": draft}), draft))
    sent = [call.args[0] for call in message.reply_text.await_args_list]
    assert bot_text("invite.friend_bonus", "he", days=7) in sent

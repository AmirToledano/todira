"""Real testimonials (2026-10-22 owner request): the bot asks "did you find a flat?", a "yes" leads to a one-sentence
testimonial saved for the owner, and only owner-approved ones appear on the home page."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import renewal_reminder as rr  # noqa: E402
from handlers import testimonial  # noqa: E402
from todira_common import testimonials  # noqa: E402


def _update(text="היה מעולה, מצאתי דירה תוך שבוע"):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    return SimpleNamespace(message=message, effective_user=SimpleNamespace(id=55, first_name="דנה"))


def test_message_is_not_taken_unless_a_testimonial_was_asked_for():
    context = SimpleNamespace(user_data={}, bot=SimpleNamespace(send_message=AsyncMock()))
    assert asyncio.run(testimonial.take_testimonial(_update(), context)) is False


def test_testimonial_is_saved_and_thanked_once():
    context = SimpleNamespace(user_data={testimonial.AWAITING_KEY: True}, bot=SimpleNamespace(send_message=AsyncMock()))
    update = _update()
    saved = []
    with (
        patch.object(testimonial, "_save_sync", lambda name, uid, text: saved.append((name, uid, text)) or 9),
        patch.object(testimonial, "_user_lang_sync", lambda uid: "he"),
        patch.object(testimonial, "OWNER_TELEGRAM_USER_ID", ""),
    ):
        assert asyncio.run(testimonial.take_testimonial(update, context)) is True
        assert asyncio.run(testimonial.take_testimonial(update, context)) is False
    assert saved == [("דנה", 55, "היה מעולה, מצאתי דירה תוך שבוע")]
    update.message.reply_text.assert_awaited_once_with("תודה רבה! 🙏")


def test_found_question_keyboard():
    rows = testimonials.found_keyboard("he").inline_keyboard
    assert [b.callback_data for b in rows[0]] == ["tq:yes", "tq:no"]
    assert [b.text for b in rows[0]] == ["כן! 🎉", "עדיין מחפש"]


def test_found_question_only_in_the_morning():
    evening = dt.datetime(2026, 10, 22, 17, 0, tzinfo=dt.timezone.utc)  # 20:00 Israel
    with patch.object(rr, "_due_found_users", side_effect=AssertionError("must not look for users")):
        assert asyncio.run(rr._run_found(SimpleNamespace(), evening)) == 0


def test_asked_recently_window():
    now = dt.datetime(2026, 10, 22, tzinfo=dt.timezone.utc)
    with patch.object(testimonials, "get_flag", lambda session, key: (now - dt.timedelta(days=10)).isoformat()):
        assert testimonials.asked_recently(None, 1, now)
    with patch.object(testimonials, "get_flag", lambda session, key: (now - dt.timedelta(days=61)).isoformat()):
        assert not testimonials.asked_recently(None, 1, now)
    with patch.object(testimonials, "get_flag", lambda session, key: None):
        assert not testimonials.asked_recently(None, 1, now)


def test_testimonials_module_imports_without_the_telegram_library():
    # 2026-10-22: the website image has no Telegram library; importing this at module level crashed the website pod.
    import subprocess
    import sys

    code = (
        "import sys; sys.modules['telegram'] = None\n"
        "import todira_common.testimonials, todira_common.share\n"
        "print('ok')"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    assert result.stdout.strip() == "ok", result.stderr

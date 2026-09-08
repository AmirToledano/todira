"""Tests for bot/main.py's liveness-probe heartbeat (added 2026-09-08, pre-launch reliability
pass — see charts/todira/templates/bot-deployment.yaml's own new livenessProbe comment). Before
this, the bot Deployment had no probe at all, so a genuinely hung bot (an event-loop deadlock)
would sit "Running" forever with zero automatic recovery.

Same importlib-loading approach as the website test files (see test_website_paid_access.py's own
comment) — bot/main.py shares a basename with scraper/main.py so it can't go through a bare
`import main`.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_BOT_DIR = Path(__file__).resolve().parent.parent / "bot"
if str(_BOT_DIR) not in sys.path:
    sys.path.insert(0, str(_BOT_DIR))

_spec = importlib.util.spec_from_file_location("bot_main_heartbeat", _BOT_DIR / "main.py")
bot_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot_main)


def test_heartbeat_job_touches_the_configured_file(tmp_path, monkeypatch):
    heartbeat_path = tmp_path / "bot_heartbeat"
    monkeypatch.setattr(bot_main, "HEARTBEAT_PATH", str(heartbeat_path))

    assert not heartbeat_path.exists()
    asyncio.run(bot_main._heartbeat_job(context=None))
    assert heartbeat_path.exists()


def test_post_init_schedules_the_heartbeat_job_when_job_queue_available():
    scheduled = []
    fake_job_queue = SimpleNamespace(
        run_repeating=lambda func, interval, first: scheduled.append((func, interval, first))
    )
    application = SimpleNamespace(
        bot=SimpleNamespace(set_my_commands=AsyncMock()), job_queue=fake_job_queue
    )

    asyncio.run(bot_main._post_init(application))

    application.bot.set_my_commands.assert_awaited_once()
    assert len(scheduled) == 1
    func, interval, first = scheduled[0]
    assert func is bot_main._heartbeat_job
    assert interval == bot_main.HEARTBEAT_INTERVAL_S
    assert first == 0  # fires immediately - see _post_init's own comment on why


def test_post_init_logs_loudly_when_job_queue_unavailable(caplog):
    application = SimpleNamespace(
        bot=SimpleNamespace(set_my_commands=AsyncMock()), job_queue=None
    )

    with caplog.at_level("ERROR", logger="bot.main"):
        asyncio.run(bot_main._post_init(application))

    assert any("JobQueue unavailable" in record.message for record in caplog.records)

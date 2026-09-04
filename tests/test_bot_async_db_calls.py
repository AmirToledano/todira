"""Regression test for a systemic bot-wide issue found 2026-08-31 while investigating "buttons
feel slow / get stuck" reports (see PROJECT_STATE.md): every bot handler that touches the DB did
`with get_session() as session: ...` directly inside an `async def` handler, using SQLAlchemy's
synchronous engine (`create_engine`, not an async one). python-telegram-bot's Application
processes updates ONE AT A TIME by default (`max_concurrent_updates=1`, never overridden in
bot/main.py) on a single asyncio event loop - so a blocking synchronous DB call made directly on
that loop freezes the ENTIRE bot (every other user's button press, every other command) for the
call's whole duration, not just the interaction that triggered it. On this project's small,
resource-constrained EC2 box (see PROJECT_STATE.md's infra notes), any DB latency at all would
show up exactly as reported: a button tap that "just thinks" and everything else stuck behind it.

Fix: wrap each handler's DB-touching logic in a plain sync function, called via
`await asyncio.to_thread(...)` instead of directly. This test proves the actual guarantee that
matters - that the event loop stays free to run OTHER coroutines while a slow DB call is in
flight - by monkeypatching the DB-load function to a slow, real `time.sleep()` (simulating a slow
network round-trip, not a fast in-memory mock that wouldn't expose blocking) and checking a
concurrent, independently-scheduled task finishes BEFORE the slow one, not after."""
import asyncio
import sys
import time
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

if "patchright" not in sys.modules:
    patchright_stub = types.ModuleType("patchright")
    sync_api_stub = types.ModuleType("patchright.sync_api")
    sync_api_stub.TimeoutError = TimeoutError
    sync_api_stub.sync_playwright = None
    patchright_stub.sync_api = sync_api_stub
    sys.modules["patchright"] = patchright_stub
    sys.modules["patchright.sync_api"] = sync_api_stub

import handlers.apartments as apartments_module
import handlers.filter_conversation as filter_conversation
from handlers.apartments import apartments
from handlers.filter_conversation import filter_start

USER_ID = 222
SLOW_CALL_SECONDS = 0.3
FAST_TASK_SECONDS = 0.03  # comfortably shorter than SLOW_CALL_SECONDS


async def _race_against(coro) -> list[str]:
    """Runs `coro` concurrently against a short independent task; returns the completion order.
    If `coro`'s own DB-touching work blocks the event loop, the short task can't run until the
    blocking work finishes, and would show up AFTER "slow" in the returned order instead of
    before it."""
    order: list[str] = []

    async def _fast_task():
        await asyncio.sleep(FAST_TASK_SECONDS)
        order.append("fast")

    task = asyncio.create_task(_fast_task())
    await coro
    order.append("slow")
    await task
    return order


def test_filter_start_db_load_does_not_block_the_event_loop(monkeypatch):
    def _slow_load(_tg_user):
        time.sleep(SLOW_CALL_SECONDS)  # a real blocking call, like a slow DB round-trip
        return filter_conversation._default_draft()

    monkeypatch.setattr(filter_conversation, "_load_draft_from_db_sync", _slow_load)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=USER_ID),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace(user_data={})

    order = asyncio.run(_race_against(filter_start(update, context)))

    assert order == ["fast", "slow"], (
        "filter_start's DB load blocked the event loop - a concurrent task scheduled to finish "
        f"in {FAST_TASK_SECONDS}s didn't run until after the {SLOW_CALL_SECONDS}s 'DB call' "
        "completed, meaning it isn't actually running off the event loop via asyncio.to_thread"
    )


def test_apartments_db_load_does_not_block_the_event_loop(monkeypatch):
    def _slow_load(_tg_user):
        time.sleep(SLOW_CALL_SECONDS)
        return True, []

    monkeypatch.setattr(apartments_module, "_load_matches_sync", _slow_load)

    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=USER_ID),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace()

    order = asyncio.run(_race_against(apartments(update, context)))

    assert order == ["fast", "slow"], (
        "apartments()'s DB load blocked the event loop - see the same assertion message in "
        "test_filter_start_db_load_does_not_block_the_event_loop for what this means"
    )

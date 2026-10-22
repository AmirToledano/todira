"""2026-10-20 (owner: "every hour, as long as it does not get the account into trouble"): a login/checkpoint page
pauses the groups feed for a day and tells the owner, instead of knocking again every hour."""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
_SCRAPER_DIR = Path(__file__).resolve().parent.parent / "scraper"
_spec = importlib.util.spec_from_file_location("scraper_main_fb_pause", _SCRAPER_DIR / "main.py")
scraper_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scraper_main)


@pytest.fixture
def flags(monkeypatch):
    store: dict = {}

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(scraper_main, "get_session", lambda: _Session())
    monkeypatch.setattr(scraper_main.app_flags, "get_flag", lambda session, key: store.get(key))
    monkeypatch.setattr(scraper_main.app_flags, "set_flag", lambda session, key, value: store.__setitem__(key, value))
    monkeypatch.setenv("FACEBOOK_COOKIES", "c_user=1")
    return store


def test_a_login_wall_pauses_the_feed_and_tells_the_owner(flags, monkeypatch):
    sent = []
    monkeypatch.setattr(scraper_main, "alert_owner", lambda text: sent.append(text) or True)

    def wall(cookie, scrolls):
        raise scraper_main.FacebookGroupsFetchError("Facebook showed a login/checkpoint page - stopping the groups feed")

    import facebook_browser.feed as feed
    monkeypatch.setattr(feed, "collect_group_posts", wall)
    scraper_main._scrape_facebook_groups_feed(set())
    until = dt.datetime.fromisoformat(flags[scraper_main._FACEBOOK_GROUPS_PAUSE_FLAG])
    assert dt.timedelta(hours=23) < until - dt.datetime.now(dt.timezone.utc) <= dt.timedelta(hours=24)
    assert sent and "24 שעות" in sent[0]

    calls = []
    monkeypatch.setattr(feed, "collect_group_posts", lambda cookie, scrolls: calls.append(1) or [])
    assert scraper_main._scrape_facebook_groups_feed(set()) == ([], set(), 0, 0, True)
    assert calls == []  # paused: Facebook is not touched at all


def test_another_failure_does_not_pause(flags, monkeypatch):
    def broken(cookie, scrolls):
        raise scraper_main.FacebookGroupsFetchError("groups feed browser session failed: timeout")

    import facebook_browser.feed as feed
    monkeypatch.setattr(feed, "collect_group_posts", broken)
    scraper_main._scrape_facebook_groups_feed(set())
    assert scraper_main._FACEBOOK_GROUPS_PAUSE_FLAG not in flags


def test_the_feed_runs_every_hour():
    values = (Path(__file__).resolve().parent.parent / "charts" / "todira" / "values.yaml").read_text()
    # hourly, at :24 - between the main scraper's :00 and :30 runs (2026-10-22)
    assert 'schedule: "24 8-22 * * *"' in values

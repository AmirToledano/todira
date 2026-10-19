"""Reads the dedicated account's Facebook GROUPS FEED in a real (headless) browser session - 2026-10-19, owner approved.

Why: a plain page load of facebook.com shows ~2 group posts (scraper/facebook_groups_client.py). Measured live with
scripts/probes/facebook_groups_feed_probe.py: ONE groups-feed session with 12 slow scrolls saw 32 distinct posts from 14
groups, 30 of them with their text and 31 from the last 24 hours, with no checkpoint. The page itself fetches the posts
(Facebook's own GraphQL responses), so this only listens to what a person's browser receives while scrolling - one
session per run, human-paced, no per-post page loads at all (each post's text, time and photos come with the feed).

Careful by design: stops at once on a login or checkpoint page (FacebookGroupsFetchError), random 3.5-7.5 s pauses
between scrolls, a fixed number of scrolls, the same user agent / locale / time zone every time. Playwright is imported
inside collect_group_posts so the main scraper image, which has no browser, can still import this module."""
from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

from facebook_groups_client import FacebookGroupsFetchError

logger = logging.getLogger(__name__)

GROUPS_FEED_URL = "https://www.facebook.com/groups/feed/"
_SCRIPT_JSON_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.S)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
_MAX_IMAGES = 10


def cookies_from_header(header: str) -> list[dict[str, Any]]:
    cookies = []
    for part in header.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        if name:
            cookies.append({"name": name, "value": value, "domain": ".facebook.com", "path": "/", "secure": True})
    return cookies


def _walk_stories(obj: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        if obj.get("__typename") == "Story" and obj.get("post_id"):
            out.append(obj)
        for value in obj.values():
            _walk_stories(value, out)
    elif isinstance(obj, list):
        for value in obj:
            _walk_stories(value, out)


def _story_text(story: dict[str, Any]) -> str | None:
    """The post's own text: the first `message.text` inside the Story (a comment's text never sits under `message`)."""
    stack: list[Any] = [story]
    while stack:
        obj = stack.pop(0)
        if isinstance(obj, dict):
            message = obj.get("message")
            if isinstance(message, dict) and isinstance(message.get("text"), str) and message["text"].strip():
                return message["text"].strip()
            stack.extend(obj.values())
        elif isinstance(obj, list):
            stack.extend(obj)
    return None


def _story_images(story: dict[str, Any]) -> list[str]:
    """Photo URLs attached to the post: `uri` values on Facebook's CDN under an image-like key of its attachments."""
    found: list[str] = []
    attachments = story.get("attachments")

    def walk(obj: Any, key: str = "") -> None:
        if len(found) >= _MAX_IMAGES:
            return
        if isinstance(obj, dict):
            uri = obj.get("uri")
            if isinstance(uri, str) and "scontent" in uri and ("image" in key.lower() or "photo" in key.lower()):
                if uri not in found:
                    found.append(uri)
            for child_key, value in obj.items():
                walk(value, child_key)
        elif isinstance(obj, list):
            for value in obj:
                walk(value, key)

    walk(attachments)
    return found


def story_to_post(story: dict[str, Any]) -> dict[str, Any] | None:
    """{post_id, group_id, text, creation_time, author, image_urls} for one Story, or None without a group or text."""
    feedback = story.get("feedback") if isinstance(story.get("feedback"), dict) else {}
    group = feedback.get("associated_group") if isinstance(feedback.get("associated_group"), dict) else {}
    group_id = group.get("id")
    text = _story_text(story)
    if not isinstance(group_id, str) or not text:
        return None
    owner = feedback.get("owning_profile") if isinstance(feedback.get("owning_profile"), dict) else {}
    author = owner.get("name").strip() if isinstance(owner.get("name"), str) else None
    created = story.get("creation_time")
    return {
        "post_id": str(story["post_id"]),
        "group_id": group_id,
        "text": text,
        "creation_time": created if isinstance(created, int) else None,
        "author": author,
        "image_urls": _story_images(story),
    }


def collect_group_posts(cookie_header: str, scrolls: int) -> list[dict[str, Any]]:
    """One groups-feed session. Returns the distinct group posts seen (see story_to_post). Raises
    FacebookGroupsFetchError on a login/checkpoint page or a browser failure."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    stories: list[dict[str, Any]] = []

    def on_response(response) -> None:
        if "/api/graphql" not in response.url:
            return
        try:
            body = response.text()
        except Exception:
            return
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    _walk_stories(json.loads(line), stories)
                except ValueError:
                    continue

    def blocked(url: str) -> bool:
        return "/login" in url or "checkpoint" in url

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                # /dev/shm is 64 MB in a pod; --disable-dev-shm-usage keeps Chromium off it on the 2 GB node
                args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            try:
                context = browser.new_context(
                    user_agent=_USER_AGENT, locale="he-IL", timezone_id="Asia/Jerusalem",
                    viewport={"width": 1366, "height": 900},
                )
                context.add_cookies(cookies_from_header(cookie_header))
                page = context.new_page()
                page.on("response", on_response)
                page.goto(GROUPS_FEED_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(6 + random.random() * 3)
                if blocked(page.url):
                    raise FacebookGroupsFetchError("Facebook showed a login/checkpoint page - stopping the groups feed")
                for block in _SCRIPT_JSON_RE.findall(page.content()):
                    try:
                        _walk_stories(json.loads(block), stories)
                    except ValueError:
                        continue
                for _ in range(scrolls):
                    page.mouse.wheel(0, random.randint(1600, 2600))
                    time.sleep(3.5 + random.random() * 4)
                    if blocked(page.url):
                        raise FacebookGroupsFetchError("Facebook showed a login/checkpoint page mid-scroll - stopping")
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise FacebookGroupsFetchError(f"groups feed browser session failed: {exc}") from exc

    posts: dict[str, dict[str, Any]] = {}
    for story in stories:
        post = story_to_post(story)
        if post is not None and post["post_id"] not in posts:
            posts[post["post_id"]] = post
    logger.info("Facebook groups feed: %d stories seen, %d usable group posts", len(stories), len(posts))
    return list(posts.values())

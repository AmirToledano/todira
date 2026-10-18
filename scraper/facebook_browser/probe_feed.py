"""One-off probe (2026-10-19, owner approved): can a real browser session on the dedicated account's GROUPS FEED see
many more group posts than the plain page load the scraper uses today (~2 posts per load)? Opens
https://www.facebook.com/groups/feed/ with the stored cookie, scrolls slowly like a person, and reads the Story nodes
Facebook's own page receives (its GraphQL responses and the first HTML). Prints COUNTS ONLY - never a name, id or post
text; the repository and its logs are public. Stops at once on a login or checkpoint page."""
from __future__ import annotations

import json
import os
import random
import re
import time

from playwright.sync_api import sync_playwright

SCROLLS = int(os.environ.get("PROBE_SCROLLS", "12"))
_SCRIPT_JSON_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.S)


def cookies_from_header(header: str) -> list[dict]:
    out = []
    for part in header.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        out.append({"name": name, "value": value, "domain": ".facebook.com", "path": "/", "secure": True})
    return out


def walk(obj, stories: list) -> None:
    if isinstance(obj, dict):
        if obj.get("__typename") == "Story" and obj.get("post_id"):
            stories.append(obj)
        for value in obj.values():
            walk(value, stories)
    elif isinstance(obj, list):
        for value in obj:
            walk(value, stories)


def story_text(story) -> str | None:
    found: list[str] = []

    def find(obj) -> None:
        if found:
            return
        if isinstance(obj, dict):
            message = obj.get("message")
            if isinstance(message, dict) and isinstance(message.get("text"), str) and message["text"].strip():
                found.append(message["text"])
                return
            for value in obj.values():
                find(value)
        elif isinstance(obj, list):
            for value in obj:
                find(value)

    find(story)
    return found[0] if found else None


def main() -> None:
    stories: list[dict] = []
    graphql_responses = 0

    def on_response(response) -> None:
        nonlocal graphql_responses
        if "/api/graphql" not in response.url:
            return
        try:
            body = response.text()
        except Exception:
            return
        graphql_responses += 1
        for line in body.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    walk(json.loads(line), stories)
                except Exception:
                    continue

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/128.0.0.0 Safari/537.36"),
            locale="he-IL", timezone_id="Asia/Jerusalem", viewport={"width": 1366, "height": 900},
        )
        context.add_cookies(cookies_from_header(os.environ["FACEBOOK_COOKIES"]))
        page = context.new_page()
        page.on("response", on_response)
        page.goto("https://www.facebook.com/groups/feed/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(6 + random.random() * 3)
        if "login" in page.url or "checkpoint" in page.url:
            print("STOPPED: landed on a login/checkpoint page")
            browser.close()
            return
        for block in _SCRIPT_JSON_RE.findall(page.content()):
            try:
                walk(json.loads(block), stories)
            except Exception:
                continue
        print(f"after first load: posts={len({s['post_id'] for s in stories})}")
        for i in range(SCROLLS):
            page.mouse.wheel(0, random.randint(1600, 2600))
            time.sleep(3.5 + random.random() * 4)
            if "login" in page.url or "checkpoint" in page.url:
                print(f"STOPPED after scroll {i + 1}: login/checkpoint")
                break
            if (i + 1) % 4 == 0:
                print(f"after scroll {i + 1}: posts={len({s['post_id'] for s in stories})}")
        browser.close()

    by_post: dict[str, dict] = {}
    for story in stories:
        by_post.setdefault(story["post_id"], story)
    now = time.time()
    groups: set[str] = set()
    with_text = recent = 0
    for story in by_post.values():
        feedback = story.get("feedback") if isinstance(story.get("feedback"), dict) else {}
        group = feedback.get("associated_group") if isinstance(feedback.get("associated_group"), dict) else {}
        if group.get("id"):
            groups.add(group["id"])
        if story_text(story):
            with_text += 1
        created = story.get("creation_time")
        if isinstance(created, int) and now - created < 86400:
            recent += 1
    print(f"graphql responses: {graphql_responses}")
    print(f"distinct posts: {len(by_post)} | distinct groups: {len(groups)} | posts with text: {with_text} | "
          f"posts from the last 24h: {recent}")


if __name__ == "__main__":
    main()

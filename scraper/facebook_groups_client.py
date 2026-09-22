"""Fetches raw post payloads from a Facebook Group's real estate posts (unlike Marketplace, a
Group post has no structured price/rooms/city fields at all — everything is free-text, written by
hand by the poster, same as a WhatsApp message).

STATUS 2026-09-21: post-detail structure CONFIRMED live via
.github/workflows/diagnose-facebook-group-post-detail.yaml, run twice against a real post
(post_id=4728400380727033, group_id=1665476640352771, "פשפשוק - דירות להשכרה"). Same "never guess a
page structure" discipline as facebook_client.py/yad2_client.py/komo_client.py/homeless_client.py —
every field name below was seen in a real, live response before this file was written.

DISCOVERY, per-group (diagnose-facebook-group-page-structure.yaml): a plain HTTPS GET of a group's
own URL (same Cookie + browser client-hint headers facebook_client.py already uses for Marketplace)
returns a real 200 HTML page with the group's real title. BUT — genuinely important, real limitation:
the group's own landing page only server-renders ONE real post permalink id in its embedded JSON
(confirmed twice, same single id both times) — the rest of the feed is lazy-loaded client-side
(GraphQL pagination, explicitly left as a last-resort option, not attempted). fetch_group_post_ids
below is honest about only returning what one plain fetch actually contains.

DISCOVERY, real fix — the HOME FEED covers every joined group in ONE request (confirmed live
2026-09-21, diagnose-facebook-home-feed-story-extraction.yaml): a plain GET of
https://www.facebook.com/ (same fetch mechanism, no group_id needed at all) server-renders MULTIPLE
real Story nodes from MULTIPLE DIFFERENT groups the dedicated account has joined — confirmed with 2
distinct real posts from 2 distinct real groups in one fetch, PLUS each post's own full free-text
body (the same {__typename, text}-only TextWithEntities shape documented below) co-located right on
the home feed itself. The home feed also mixes in non-group content (a followed Page's post showed
up in the same fetch, `feedback.associated_group` absent entirely) — fetch_home_feed_post_ids below
only returns a post when `feedback.associated_group.id` is genuinely present, and only when that id
is in the caller-supplied `tracked_group_ids` set, so untracked/non-group noise never reaches the
scraper. Deliberately does NOT trust the home feed's own co-located message text for attribution
(with several posts on one page, matching the right text to the right post_id isn't guaranteed safe
the way it is on a single post's own permalink page, which has exactly one candidate) — it only
extracts (group_id, post_id) pairs; the caller re-fetches each genuinely-new one via
fetch_post_detail below, which unambiguously ties one page fetch to one specific post_id, same
"discover cheap, enrich only what's genuinely new" two-stage pattern facebook_client.py/yad2_client.py
already use.

POST DETAIL (diagnose-facebook-group-post-detail.yaml): fetching a post's own permalink page
(https://www.facebook.com/groups/<group_id>/posts/<post_id>/ — no /groups/<gid>/permalink/<pid>/
redirect needed, that path already 200s directly) returns the post's real content embedded as
GraphQL-shaped JSON, same <script type="application/json"> framing as everywhere else in this
project's Facebook code:
    - A `Story` node (matched by __typename + post_id == the post_id being fetched) carries
      `creation_time` (unix timestamp), `feedback.owning_profile` ({__typename: "User", name,
      short_name, id} — the poster, i.e. the listing's real "contact"), `feedback.associated_group.
      id` (confirms which group), and `attachments` (a list whose `media` entries are Photo nodes —
      id only at this stage, no direct image URL; NOT resolved yet, same open question Marketplace's
      own docstring already carries for a different field).
    - The real free-text post body is a `TextWithEntities` node — confirmed live, real text:
      "*יחידת הורים אחרונה ברחוב ששת הימים 7*\nיחידת הורים מוארת בדירת שותפים...1,350ש"ח...לפרטים
      ותמונות נוספות: דרור בעלי 050-9516572...". Distinguishing it from a COMMENT's own
      TextWithEntities (the same page also embeds real comments, which are irrelevant noise here) is
      real and confirmed, not guessed: the post's own body node has EXACTLY two keys (`__typename`,
      `text`) and nothing else, while every comment/mention TextWithEntities node carries `ranges`/
      `aggregated_ranges`/`color_ranges`/`delight_ranges`/`image_ranges`/`inline_style_ranges`/
      `translation_type` alongside `text` even when those range lists are empty — confirmed on both
      live runs, never once ambiguous. _parse_post_message below relies on exactly that shape check.
    - A second, more UI-oriented rendering of the same text also exists as
      `ComposedUnstyledBlockWithEntities` nodes (one per paragraph/line) — NOT used here, since the
      single TextWithEntities node above already carries the complete text in one field.

Genuinely NOT available even after this: price/rooms/floor/square_meters/city/neighborhood/street —
none of these exist as structured fields on a Group post, unlike every other source this project
scrapes. normalize() already treats every one of these as optional (degrades to None), so a Group
post normalizes fine with only description/url/posted_at/external_id populated — but
scraper/main.py's matching/notification logic has NOT yet been checked for whether it's safe to
notify a saved search with a price-range filter about a listing whose price is always None (open
question, flagged rather than guessed at — see the owner conversation this file was built in).

Requires FACEBOOK_COOKIES — same dedicated, never-personal account's session cookie as
facebook_client.py. See set-facebook-cookies-secret.yaml's own header comment."""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from typing import Any, Iterator

import httpx

import facebook_groups_text_parser

logger = logging.getLogger(__name__)

_GROUPS_BASE = "https://www.facebook.com/groups/"

FACEBOOK_COOKIES_ENV_VAR = "FACEBOOK_COOKIES"

# Identical to facebook_client.py's own _BROWSER_HEADERS — confirmed live (both group-page and
# post-detail diagnostics) that the same exact header set works for Groups too, not re-derived.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

PAGE_LOAD_TIMEOUT_S = 30.0

_SCRIPT_JSON_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', re.S)
_POST_PERMALINK_RE = re.compile(r"/groups/\d+/(?:posts|permalink)/(\d+)")

# The post-body TextWithEntities node has exactly these two keys and nothing else — see module
# docstring for how this was confirmed live against real comment/mention nodes on the same page.
_POST_BODY_TEXT_KEYS = frozenset({"__typename", "text"})


class FacebookGroupsFetchError(RuntimeError):
    """The request failed, timed out, or Facebook returned a non-200 — same meaning as
    facebook_client.FacebookFetchError, kept as a separate class so callers can tell the two
    sources' failures apart in logs without inspecting the message string."""


def _get_cookie_header() -> str:
    cookie = os.environ.get(FACEBOOK_COOKIES_ENV_VAR, "").strip()
    if not cookie:
        raise FacebookGroupsFetchError(
            f"{FACEBOOK_COOKIES_ENV_VAR} is not set — see set-facebook-cookies-secret.yaml. "
            "Facebook Groups require a real logged-in session; there is no anonymous access."
        )
    return cookie


def _fetch(url: str, *, context_label: str) -> str:
    headers = dict(_BROWSER_HEADERS)
    headers["Cookie"] = _get_cookie_header()
    try:
        response = httpx.get(
            url, headers=headers, timeout=PAGE_LOAD_TIMEOUT_S, follow_redirects=True
        )
    except httpx.HTTPError as exc:
        raise FacebookGroupsFetchError(f"Facebook request failed for {context_label}: {exc}") from exc

    if response.status_code != 200:
        raise FacebookGroupsFetchError(
            f"Facebook returned http_status={response.status_code} for {context_label} — the "
            "session cookie may have expired and need re-exporting (see "
            "set-facebook-cookies-secret.yaml), or this is a real login/checkpoint wall."
        )
    return response.text


def _iter_json_blocks(html: str) -> Iterator[Any]:
    """Same XSSI-prefix/HTML-comment stripping as facebook_client._iter_json_blocks — kept as a
    separate copy rather than importing from that module, since this file has no other dependency
    on it and the two sources' discovery histories are deliberately independent (see each module's
    own docstring)."""
    for block in _SCRIPT_JSON_RE.findall(html):
        block = block.strip()
        if block.startswith("for (;;);"):
            block = block[len("for (;;);") :]
        if block.startswith("<!--") and block.endswith("-->"):
            block = block[4:-3].strip()
        if not block:
            continue
        try:
            yield json.loads(block)
        except json.JSONDecodeError:
            continue


def fetch_group_post_ids(group_url: str) -> list[str]:
    """Returns the distinct post ids found server-rendered on ONE fetch of `group_url` (a share
    link or a canonical /groups/<id>/ URL — both confirmed live to work, curl follows the
    share-link redirect same as a browser would). CONFIRMED LIVE LIMITATION, not worked around:
    a group's landing page only ever carried ONE real post id in two separate live test fetches —
    the rest of the feed is lazy-loaded client-side. This is therefore only ever going to surface
    the single newest post per call, not a real backlog — see module docstring."""
    html = _fetch(group_url, context_label=f"Group url={group_url!r}")
    return sorted(set(_POST_PERMALINK_RE.findall(html)))


_HOME_FEED_URL = "https://www.facebook.com/"


def _iter_story_nodes(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, dict):
        if obj.get("__typename") == "Story" and obj.get("post_id"):
            yield obj
        for value in obj.values():
            yield from _iter_story_nodes(value)
    elif isinstance(obj, list):
        for entry in obj:
            yield from _iter_story_nodes(entry)


def fetch_home_feed_post_ids(tracked_group_ids: set[str]) -> list[tuple[str, str]]:
    """Returns distinct (group_id, post_id) pairs found on ONE fetch of the dedicated account's own
    home feed, restricted to `tracked_group_ids` — see module docstring for why this is the real
    fix for "only one post per group" (covers every joined group in one request) and why it only
    returns ids, never the co-located text (attribution across several posts on one page isn't
    provably safe the way a single post's own permalink page is). Caller is expected to pass this
    every group id it actually wants posts from; a Story whose `feedback.associated_group.id` is
    missing (non-group content — e.g. a followed Page's post, confirmed live to appear in the same
    feed) or not in `tracked_group_ids` is silently skipped, never guessed at."""
    html = _fetch(_HOME_FEED_URL, context_label="home feed")
    pairs: set[tuple[str, str]] = set()
    for block in _iter_json_blocks(html):
        for story in _iter_story_nodes(block):
            post_id = story.get("post_id")
            feedback = story.get("feedback")
            group = feedback.get("associated_group") if isinstance(feedback, dict) else None
            group_id = group.get("id") if isinstance(group, dict) else None
            if (
                isinstance(post_id, str)
                and isinstance(group_id, str)
                and group_id in tracked_group_ids
            ):
                pairs.add((group_id, post_id))
    return sorted(pairs)


def _parse_post_message(blocks: Iterator[Any]) -> str | None:
    for block in blocks:
        result = _find_post_body_text(block)
        if result is not None:
            return result
    return None


def _find_post_body_text(obj: Any) -> str | None:
    if isinstance(obj, dict):
        if (
            obj.get("__typename") == "TextWithEntities"
            and set(obj.keys()) == _POST_BODY_TEXT_KEYS
            and isinstance(obj.get("text"), str)
            and obj["text"].strip()
        ):
            return obj["text"].strip()
        for value in obj.values():
            found = _find_post_body_text(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for entry in obj:
            found = _find_post_body_text(entry)
            if found is not None:
                return found
    return None


def _find_story_node(obj: Any, *, post_id: str) -> dict[str, Any] | None:
    if isinstance(obj, dict):
        if obj.get("__typename") == "Story" and obj.get("post_id") == post_id:
            return obj
        for value in obj.values():
            found = _find_story_node(value, post_id=post_id)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for entry in obj:
            found = _find_story_node(entry, post_id=post_id)
            if found is not None:
                return found
    return None


def fetch_post_detail(group_id: str, post_id: str) -> dict[str, Any] | None:
    """Fetches ONE post's own permalink page and returns a normalize()-ready flat dict — {id, url,
    description, posted_at, price, rooms, floor, square_meters, city, neighborhood, street} with
    every structured field None (see module docstring: Group posts genuinely never carry them) — or
    None on ANY failure (missing cookie, network error, non-200, or no usable post body found),
    never raises, same defensive contract as facebook_client.fetch_listing_detail."""
    url = f"{_GROUPS_BASE}{group_id}/posts/{post_id}/"
    try:
        html = _fetch(url, context_label=f"Group post group_id={group_id!r} post_id={post_id!r}")
    except FacebookGroupsFetchError:
        logger.exception(
            "Failed to fetch Facebook group post detail page: group_id=%s post_id=%s",
            group_id,
            post_id,
        )
        return None

    blocks = list(_iter_json_blocks(html))
    message = _parse_post_message(iter(blocks))
    if message is None:
        logger.warning(
            "No post body TextWithEntities found for group_id=%s post_id=%s — page fetched fine "
            "but the shape didn't match what was confirmed live; nothing usable to return.",
            group_id,
            post_id,
        )
        return None

    story: dict[str, Any] | None = None
    for block in blocks:
        story = _find_story_node(block, post_id=post_id)
        if story is not None:
            break

    author_name: str | None = None
    posted_at_iso: str | None = None
    if story is not None:
        feedback = story.get("feedback")
        if isinstance(feedback, dict):
            owning_profile = feedback.get("owning_profile")
            if isinstance(owning_profile, dict) and isinstance(owning_profile.get("name"), str):
                author_name = owning_profile["name"].strip()
        creation_time = story.get("creation_time")
        if isinstance(creation_time, int):
            # normalize.py's _parse_datetime expects an ISO string (dt.datetime.fromisoformat), not
            # a raw unix timestamp — confirmed creation_time is real unix seconds (1789882033 on
            # the live-tested post, a plausible 2026 date), converted here rather than passed
            # through raw, which would silently fail to parse and leave posted_at as None.
            posted_at_iso = dt.datetime.fromtimestamp(creation_time, tz=dt.timezone.utc).isoformat()

    description = message
    if author_name:
        description = f"{message}\n\n(מפרסם/ת: {author_name})"

    result: dict[str, Any] = {
        "id": str(post_id),
        "url": url,
        "description": description,
        "dateAdded": posted_at_iso,
        "price": None,
        "rooms": None,
        "floor": None,
        "square_meters": None,
        "city": None,
        "neighborhood": None,
        "street": None,
        "images": [],
    }
    # 2026-09-21, explicit owner decision: regex/keyword extraction, not a per-post LLM call (this
    # project has never made one; the owner weighed cost vs. accuracy and chose free/imperfect) —
    # see facebook_groups_text_parser.py's own module docstring. Only ever OVERWRITES one of the
    # structured-field placeholders above with something a pattern actually matched in the real
    # message text — never touches description/url/id/dateAdded.
    result.update(facebook_groups_text_parser.parse_listing_fields(message))
    return result

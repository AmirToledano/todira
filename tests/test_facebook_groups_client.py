"""Tests for facebook_groups_client.py — mocks facebook_groups_client._fetch directly (same
mocking boundary test_facebook_client.py uses), so these never make a real network call and never
touch FACEBOOK_COOKIES. Fixture JSON mirrors the real, live-confirmed shape from
.github/workflows/diagnose-facebook-group-post-detail.yaml's actual runs against a real post (see
facebook_groups_client.py's own module docstring for the real field names this was built against).
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import pytest

import facebook_groups_client
from facebook_groups_client import FacebookGroupsFetchError


def _script_wrap(payload) -> str:
    return f'<script type="application/json" data-sjs>{json.dumps(payload)}</script>'


def _group_landing_html(*post_ids: str, group_id: str = "1665476640352771") -> str:
    links = "".join(
        f'<a href="/groups/{group_id}/posts/{pid}/">post</a>' for pid in post_ids
    )
    return f"<html><body>{links}</body></html>"


def _post_detail_html(
    *,
    post_id: str = "4728400380727033",
    group_id: str = "1665476640352771",
    message_text: str = '*יחידת הורים אחרונה ברחוב ששת הימים 7*\nיחידת הורים מוארת בדירת שותפים.',
    author_name: str = "Avivit Zissholz",
    creation_time: int = 1789882033,
    include_comment_noise: bool = True,
) -> str:
    story = {
        "__typename": "Story",
        "id": "UzpfSTU4ODY5MDg5NDpWSzo0NzI4NDAwMzgwNzI3MDMz",
        "post_id": post_id,
        "creation_time": creation_time,
        "feedback": {
            "id": "feedback-id",
            "associated_group": {"context_actor_hovercard": "GROUP", "id": group_id},
            "owning_profile": {"__typename": "User", "name": author_name, "short_name": "Avivit", "id": "588690894"},
        },
        "attachments": [
            {"media": {"__typename": "Photo", "id": "10163808700600895"}},
        ],
    }
    post_body_text = {"__typename": "TextWithEntities", "text": message_text}
    blocks = [{"story": story, "message": post_body_text}]
    if include_comment_noise:
        # A real comment/mention TextWithEntities always carries these extra keys even when the
        # range lists are empty — confirmed live twice, this is the exact shape that must NOT be
        # mistaken for the post's own body.
        comment_text = {
            "__typename": "TextWithEntities",
            "text": "@Israel תודה",
            "ranges": [{"entity": {"__typename": "User", "id": "100081164555811"}}],
            "aggregated_ranges": [],
            "color_ranges": [],
            "delight_ranges": [],
            "image_ranges": [],
            "inline_style_ranges": [],
            "translation_type": None,
        }
        blocks.append({"comment": {"__typename": "Comment", "body": comment_text}})
    return "<html><body>" + "".join(_script_wrap(b) for b in blocks) + "</body></html>"


def test_fetch_group_post_ids_returns_distinct_ids_found_on_one_fetch(monkeypatch):
    monkeypatch.setenv("FACEBOOK_COOKIES", "c_user=1; xs=fake")
    html = _group_landing_html("4728400380727033")
    monkeypatch.setattr(facebook_groups_client, "_fetch", lambda url, **kw: html)

    ids = facebook_groups_client.fetch_group_post_ids("https://www.facebook.com/groups/1665476640352771/")

    assert ids == ["4728400380727033"]


def test_fetch_group_post_ids_raises_without_cookie(monkeypatch):
    monkeypatch.delenv("FACEBOOK_COOKIES", raising=False)
    with pytest.raises(FacebookGroupsFetchError):
        facebook_groups_client.fetch_group_post_ids("https://www.facebook.com/groups/1/")


def test_fetch_post_detail_extracts_real_message_ignoring_comment_noise(monkeypatch):
    monkeypatch.setenv("FACEBOOK_COOKIES", "c_user=1; xs=fake")
    html = _post_detail_html()
    monkeypatch.setattr(facebook_groups_client, "_fetch", lambda url, **kw: html)

    result = facebook_groups_client.fetch_post_detail("1665476640352771", "4728400380727033")

    assert result is not None
    assert result["id"] == "4728400380727033"
    assert "יחידת הורים אחרונה" in result["description"]
    assert "Avivit Zissholz" in result["description"]
    assert "@Israel" not in result["description"]  # comment noise never leaks into the listing text
    assert result["dateAdded"] == "2026-09-20T05:27:13+00:00"
    assert result["price"] is None
    assert result["rooms"] is None
    assert result["city"] is None


def test_fetch_post_detail_returns_none_when_no_post_body_found(monkeypatch):
    monkeypatch.setenv("FACEBOOK_COOKIES", "c_user=1; xs=fake")
    monkeypatch.setattr(
        facebook_groups_client, "_fetch", lambda url, **kw: "<html><body>no json here</body></html>"
    )

    result = facebook_groups_client.fetch_post_detail("1665476640352771", "4728400380727033")

    assert result is None


def test_fetch_post_detail_returns_none_on_fetch_failure(monkeypatch):
    monkeypatch.setenv("FACEBOOK_COOKIES", "c_user=1; xs=fake")

    def _boom(url, **kw):
        raise FacebookGroupsFetchError("http_status=400")

    monkeypatch.setattr(facebook_groups_client, "_fetch", _boom)

    result = facebook_groups_client.fetch_post_detail("1665476640352771", "4728400380727033")

    assert result is None


def _home_feed_story(*, post_id: str, group_id: str | None, author: str | None = "Someone") -> dict:
    feedback: dict = {}
    if group_id is not None:
        feedback["associated_group"] = {"id": group_id}
    if author is not None:
        feedback["owning_profile"] = {"__typename": "User", "name": author}
    return {"__typename": "Story", "post_id": post_id, "creation_time": 111, "feedback": feedback}


def test_fetch_home_feed_post_ids_returns_only_tracked_groups(monkeypatch):
    monkeypatch.setenv("FACEBOOK_COOKIES", "c_user=1; xs=fake")
    blocks = [
        _home_feed_story(post_id="1728205471811554", group_id="266774507954665"),
        # Real, live-confirmed shape: a followed Page's post has no associated_group at all.
        _home_feed_story(post_id="1662526462549755", group_id=None, author="Bits of Gold"),
        # A real post from a group we're simply not tracking.
        _home_feed_story(post_id="999", group_id="1111111"),
    ]
    html = "<html><body>" + "".join(_script_wrap(b) for b in blocks) + "</body></html>"
    monkeypatch.setattr(facebook_groups_client, "_fetch", lambda url, **kw: html)

    result = facebook_groups_client.fetch_home_feed_post_ids({"266774507954665", "1665476640352771"})

    assert result == [("266774507954665", "1728205471811554")]


def test_fetch_home_feed_post_ids_raises_without_cookie(monkeypatch):
    monkeypatch.delenv("FACEBOOK_COOKIES", raising=False)
    with pytest.raises(FacebookGroupsFetchError):
        facebook_groups_client.fetch_home_feed_post_ids({"1665476640352771"})

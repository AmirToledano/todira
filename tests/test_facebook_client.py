"""Tests for facebook_client.py — mocks facebook_client._fetch directly (same mocking boundary
test_komo_client.py uses for komo_client._isp_proxy_get/_isp_proxy_post), so these never make a
real network call and never touch FACEBOOK_COOKIES. Fixture HTML mirrors the real, live-confirmed
shape from .github/workflows/diagnose-facebook-marketplace-page-structure.yaml's actual runs
(see facebook_client.py's own module docstring for the real field names this was built against).
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import pytest

import facebook_client
from facebook_client import FacebookFetchError


def _script_wrap(payload: dict) -> str:
    return f'<script type="application/json" data-sjs>{json.dumps(payload)}</script>'


def _feed_html(*stories: dict) -> str:
    wrapper = {"data": {"marketplace_search": {"feed_units": {"edges": [
        {"node": story} for story in stories
    ]}}}}
    return "<html><body>" + _script_wrap(wrapper) + "</body></html>"


def _make_listing_story(
    listing_id: str,
    *,
    price_text: str = "₪3,000",
    url: str | None = None,
    photo_uris: tuple[str, ...] = ("https://scontent.example/a.jpg",),
) -> dict:
    return {
        "__typename": "MarketplaceFeedListingStory",
        "id": f"{listing_id}:IN_MEMORY_MARKETPLACE_FEED_STORY_ENT:EntMarketplaceFeedListingStory:1",
        "story_type": "LISTING",
        "for_sale_item": {
            "__typename": "GroupCommerceProductItem",
            "id": listing_id,
            "location": {"latitude": 32.06, "longitude": 34.77},
            "marketplace_listing_title": "דירה 3 חדרי שינה 1 חדרי אמבטיה",
            "custom_title": "3 bedrooms · 1 bathroom",
            "formatted_price": {"text": price_text},
            "listing_photos": [
                {
                    "__typename": "CatalogMarketplaceEnhancementTransformedImage",
                    "image": {"height": 159, "width": 320, "uri": uri},
                    "id": f"img-{i}",
                }
                for i, uri in enumerate(photo_uris)
            ],
            "marketplace_listing_seller": {"__typename": "User", "name": "Someone", "id": "999"},
            "story": {
                "id": "story-id",
                "url": url or f"https://www.facebook.com/marketplace/item/{listing_id}/",
                "post_id": listing_id,
            },
            "is_sold": False,
            "is_pending": False,
            "is_hidden": False,
        },
    }


def _detail_html(*, city: str | None, description: str | None) -> str:
    node = {"__typename": "GroupCommerceProductItem", "id": "1"}
    if description is not None:
        node["redacted_description"] = {"text": description}
    wrapper = {"data": {"viewer": {"marketplace_product_details_page": node}}}
    html = "<html><body>" + _script_wrap(wrapper)
    if city is not None:
        # reverse_geocode_detailed is confirmed live to sit as its own dict elsewhere on the
        # page, not nested under GroupCommerceProductItem — a separate script block here mirrors
        # that real shape.
        html += _script_wrap({"reverse_geocode_detailed": {"city": city, "state": "", "postal_code": "46000"}})
    html += "</body></html>"
    return html


def test_fetch_search_results_parses_real_shaped_feed(monkeypatch):
    html = _feed_html(_make_listing_story("111"), _make_listing_story("222", price_text="₪5,500"))
    monkeypatch.setattr(facebook_client, "_fetch", lambda url, **kw: html)

    results = list(facebook_client.fetch_search_results())

    assert [r["id"] for r in results] == ["111", "222"]
    assert results[0]["price"] == 3000
    assert results[1]["price"] == 5500
    assert results[0]["url"] == "https://www.facebook.com/marketplace/item/111/"
    assert results[0]["images"] == ["https://scontent.example/a.jpg"]
    # not available at discovery stage — see module docstring
    assert results[0]["city"] is None
    assert results[0]["rooms"] is None
    assert results[0]["street"] is None


def test_fetch_search_results_dedupes_by_id(monkeypatch):
    story = _make_listing_story("111")
    html = _feed_html(story, story)  # same node appears twice, as Facebook's own page can
    monkeypatch.setattr(facebook_client, "_fetch", lambda url, **kw: html)

    results = list(facebook_client.fetch_search_results())

    assert len(results) == 1


def test_fetch_search_results_skips_stories_with_no_for_sale_item(monkeypatch):
    broken = {"__typename": "MarketplaceFeedListingStory", "id": "x", "for_sale_item": None}
    html = _feed_html(broken, _make_listing_story("222"))
    monkeypatch.setattr(facebook_client, "_fetch", lambda url, **kw: html)

    results = list(facebook_client.fetch_search_results())

    assert [r["id"] for r in results] == ["222"]


def test_fetch_search_results_uses_custom_url_path(monkeypatch):
    seen_urls = []

    def fake_fetch(url, **kw):
        seen_urls.append(url)
        return _feed_html()

    monkeypatch.setattr(facebook_client, "_fetch", fake_fetch)

    list(facebook_client.fetch_search_results(url_path="telaviv/propertyrentals/"))

    assert seen_urls == ["https://www.facebook.com/marketplace/telaviv/propertyrentals/"]


def test_fetch_listing_detail_extracts_real_city_and_description(monkeypatch):
    html = _detail_html(city="הרצליה", description="דירת 3.5 חדרים ברחוב הכוזרי")
    monkeypatch.setattr(facebook_client, "_fetch", lambda url, **kw: html)

    result = facebook_client.fetch_listing_detail("1053986910834947")

    assert result == {"city": "הרצליה", "description": "דירת 3.5 חדרים ברחוב הכוזרי"}


def test_fetch_listing_detail_city_none_when_geocode_missing(monkeypatch):
    html = _detail_html(city=None, description="תיאור כלשהו")
    monkeypatch.setattr(facebook_client, "_fetch", lambda url, **kw: html)

    result = facebook_client.fetch_listing_detail("1")

    assert result == {"city": None, "description": "תיאור כלשהו"}


def test_fetch_listing_detail_returns_none_on_fetch_error(monkeypatch):
    def raise_error(url, **kw):
        raise FacebookFetchError("boom")

    monkeypatch.setattr(facebook_client, "_fetch", raise_error)

    assert facebook_client.fetch_listing_detail("1") is None


def test_get_cookie_header_raises_when_env_var_unset(monkeypatch):
    monkeypatch.delenv(facebook_client.FACEBOOK_COOKIES_ENV_VAR, raising=False)

    with pytest.raises(FacebookFetchError, match="FACEBOOK_COOKIES"):
        facebook_client._get_cookie_header()


def test_get_cookie_header_returns_the_real_value(monkeypatch):
    monkeypatch.setenv(facebook_client.FACEBOOK_COOKIES_ENV_VAR, "c_user=1; xs=2")

    assert facebook_client._get_cookie_header() == "c_user=1; xs=2"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("₪3,000", 3000),
        ("₪18,500", 18500),
        ("", None),
        (None, None),
        ("Free", None),
    ],
)
def test_parse_price(text, expected):
    assert facebook_client._parse_price(text) == expected


def test_fetch_raises_on_non_200(monkeypatch):
    class FakeResponse:
        status_code = 400
        text = "error page"

    monkeypatch.setenv(facebook_client.FACEBOOK_COOKIES_ENV_VAR, "c_user=1")
    monkeypatch.setattr(facebook_client.httpx, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(FacebookFetchError, match="http_status=400"):
        facebook_client._fetch("https://www.facebook.com/marketplace/x", context_label="test")


def test_fetch_raises_facebook_fetch_error_on_httpx_error(monkeypatch):
    import httpx

    def raise_httpx_error(*a, **kw):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setenv(facebook_client.FACEBOOK_COOKIES_ENV_VAR, "c_user=1")
    monkeypatch.setattr(facebook_client.httpx, "get", raise_httpx_error)

    with pytest.raises(FacebookFetchError, match="timed out"):
        facebook_client._fetch("https://www.facebook.com/marketplace/x", context_label="test")

"""2026-10-19 (owner approved a browser for Facebook): the groups feed read in one browser session
(scraper/facebook_browser/feed.py), and every post turned into a listing with what its free text states."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

import facebook_groups_client
import facebook_groups_text_parser as parser
from facebook_browser import feed


def _story(text, group="111", post="999", images=("https://scontent.xx/photo1.jpg",)):
    return {
        "__typename": "Story", "post_id": post, "creation_time": 1789900000,
        "feedback": {"associated_group": {"id": group}, "owning_profile": {"name": "Dana"}},
        "comet_sections": {"content": {"story": {"message": {"text": text}}}},
        "attachments": [{"media": {"photo_image": {"uri": u}}} for u in images],
    }


def test_a_feed_story_becomes_a_post_with_text_group_time_and_photos():
    post = feed.story_to_post(_story("להשכרה 3 חדרים ברמת גן 6,200 ש\"ח"))
    assert post["group_id"] == "111" and post["post_id"] == "999" and post["creation_time"] == 1789900000
    assert post["text"].startswith("להשכרה") and post["image_urls"] == ["https://scontent.xx/photo1.jpg"]


def test_a_story_without_a_group_or_text_is_dropped():
    assert feed.story_to_post({"__typename": "Story", "post_id": "1", "feedback": {}}) is None


def test_the_free_text_becomes_a_listing_with_city_street_price_and_deal():
    post = feed.story_to_post(_story("להשכרה דירת 3 חדרים ברחוב הרצל 12 ברמת גן, קומה 2, 6,200 ש\"ח, מרפסת"))
    item = facebook_groups_client.raw_item_from_feed_post(post)
    assert item["city"] == "רמת גן" and item["street"] == "הרצל 12" and item["price"] == 6200
    assert item["rooms"] == 3.0 and item["floor"] == 2 and item["balcony"] is True and item["dealHint"] == "rent"
    assert item["url"] == "https://www.facebook.com/groups/111/posts/999/"
    assert item["images"] == ["https://scontent.xx/photo1.jpg"] and "(מפרסם/ת: Dana)" in item["description"]


def test_someone_looking_for_a_flat_is_not_a_listing():
    assert parser.looks_like_seeker("מחפשת דירת 2 חדרים בגבעתיים עד 5,000")
    assert not parser.looks_like_seeker("מפנה דירה בתל אביב, מחפשים מחליף, 3 חד׳ 7,500 ₪")
    assert not parser.looks_like_seeker("להשכרה דירת 3 חדרים ברמת גן")


def test_cookie_header_becomes_browser_cookies():
    cookies = feed.cookies_from_header("c_user=1; xs=abc=def; ")
    assert [(c["name"], c["value"]) for c in cookies] == [("c_user", "1"), ("xs", "abc=def")]
    assert all(c["domain"] == ".facebook.com" for c in cookies)


def test_an_ad_for_a_service_is_not_a_listing():
    # 2026-10-19 (owner): a guarantees-company post with a "10,000 ₪" voucher reached everyone as a flat.
    ad = ("מתנה לחגים מערבויות ישיר 🎁 כל מי שמנפיק אצלנו ערבות ללא פיקדון לשכר דירה נכנס להגרלה על שובר מתנה של "
          "10,000 ש\"ח למחסני חשמל. https://www.arvuyotyashir.co.il/?utm_source=x")
    assert not parser.looks_like_listing(ad, parser.parse_listing_fields(ad))
    assert not parser.looks_like_listing("מישהו מכיר אינסטלטור טוב? 300 ש\"ח")


def test_real_flats_on_offer_are_listings():
    for text in ("להשכרה דירת 3 חדרים ברמת גן 6,200 ש\"ח", "מתפנה יחידת דיור בגבעתיים, 4,000 ₪, כניסה מיידית",
                 "סאבלט בחיפה לחודש, 2 חד׳", "דירה יפה למכירה 2.1 מיליון"):
        assert parser.looks_like_listing(text, parser.parse_listing_fields(text)), text

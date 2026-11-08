"""2026-11-08: the morning email of new matching flats (todira_common/email_digest.py, website /email/stop)."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from todira_common import email_digest


def _listing(i, **kw):
    base = {"id": i, "price": 6500, "rooms": 3, "floor": 2, "size_sqm": 75, "street": "הרצל", "neighborhood": None,
            "city": "חולון", "image_urls": ["https://img.example/a.jpg"], "first_seen_at": dt.datetime(2026, 11, 8, tzinfo=dt.timezone.utc)}
    base.update(kw)
    return SimpleNamespace(**base)


def test_email_shows_up_to_ten_flats_with_share_links_and_a_stop_link():
    listings = [_listing(i) for i in range(1, 13)]
    subject, page, text = email_digest.build(listings, 42, "דנה", "חולון", 15)
    assert subject == "15 דירות חדשות בחולון שמתאימות לך"
    assert page.count("לפרטי הדירה") == 10 and "ועוד 5 דירות באתר" in page
    assert "/s/1-" in page and "?src=email_digest" in page
    assert "/email/stop?t=" in page and "/email/stop?t=" in text
    assert 'dir="rtl"' in page and "היי דנה," in page
    assert "—" not in page and "–" not in page


def test_one_flat_and_missing_facts():
    subject, page, _ = email_digest.build([_listing(1, price=None, floor=0, size_sqm=None, image_urls=[])], 1, None, None, 1)
    assert subject == "דירה חדשה שמתאימה לך"
    assert "מחיר לא צוין" in page and "קרקע" in page and "<img" not in page


def test_stop_token_round_trip_and_forgery():
    token = email_digest.stop_token(42)
    assert email_digest.user_from_stop_token(token) == 42
    assert email_digest.user_from_stop_token(token[:-2] + "xx") is None


def test_stop_page_asks_first_and_a_bad_link_says_so():
    import importlib.util
    import sys
    from pathlib import Path

    from fastapi.testclient import TestClient

    website = Path(__file__).resolve().parent.parent / "website"
    sys.path.insert(0, str(website))
    spec = importlib.util.spec_from_file_location("website_main_email_stop", website / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    http = TestClient(module.app)
    page = http.get(f"/email/stop?t={email_digest.stop_token(5)}").text
    assert "להפסיק את המייל היומי?" in page and 'method="post"' in page
    assert "הקישור לא תקין" in http.get("/email/stop?t=nonsense").text

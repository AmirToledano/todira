"""The rich listing detail view (2026-10-14 owner request): GET /apartments/listing/{id}/details renders
templates/_listing_details.html, which apartments.html's openListingDetail loads into the detail view.

Same importlib loading as the other website test files (website/main.py shares its basename with scraper/main.py).
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_listing_details", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

_NOW = dt.datetime.now(dt.timezone.utc)


def _user(**overrides):
    values = {
        "id": 2, "telegram_user_id": 222, "first_name": None, "telegram_username": None, "filter": None,
        "free_access_granted": False, "trial_ends_at": _NOW + dt.timedelta(days=2), "paid_until": None,
        "language": "he", "google_sub": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _listing(**overrides):
    values = {
        "id": 7, "source": "yad2", "url": "https://www.yad2.co.il/item/secret-source-url", "deal_type": "rent",
        "property_type": "apartment", "price": 6000, "previous_price": 6500,
        "price_changed_at": _NOW - dt.timedelta(days=2), "rooms": Decimal("3.0"), "floor": 2, "floor_total": 5,
        "size_sqm": 75, "city": "תל אביב יפו", "neighborhood": "פלורנטין", "street": "הרצל",
        "latitude": Decimal("32.056000"), "longitude": Decimal("34.770000"), "has_parking": True,
        "has_elevator": False, "has_balcony": None, "pets_allowed": None, "is_renovated": True,
        "is_roommate_friendly": None, "safe_room_type": "safe_room", "furniture": "unfurnished",
        "is_broker_listing": False, "move_in_date": dt.date(2026, 11, 1), "move_in_note": None,
        "description": "דירה יפה", "image_urls": [], "posted_at": _NOW - dt.timedelta(days=3),
        "scraped_at": _NOW - dt.timedelta(minutes=20), "first_seen_at": _NOW - dt.timedelta(days=3),
        "is_delisted": False, "delisted_at": None, "duplicate_of_id": None, "also_on": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeSession:
    def __init__(self, user, listing):
        self._user = user
        self._listing = listing

    def scalar(self, stmt):
        return self._user

    def get(self, model, pk):
        if model is website_main.Listing:
            return self._listing if self._listing is not None and self._listing.id == pk else None
        return self._user

    def execute(self, stmt):  # base.html's header lookup
        return SimpleNamespace(first=lambda: None)


def _fake_get_session(session):
    @contextmanager
    def _inner():
        yield session

    return _inner


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _get_details(client, listing, *, area=None, similar=(), also_on=(), user=None):
    session = _FakeSession(user or _user(), listing)

    def _fake_also_on(session, listings, lang):
        for item in listings:
            item.also_on = list(also_on)

    with (
        patch.object(website_main, "get_session", _fake_get_session(session)),
        patch.object(website_main, "_attach_also_on", _fake_also_on),
        patch.object(website_main, "_listing_action_ids", lambda session, user_id, action: set()),
        patch.object(website_main, "_area_price_comparison", lambda session, listing: area),
        patch.object(website_main, "_similar_listings", lambda session, listing, hidden: list(similar)),
    ):
        return client.get(f"/apartments/listing/{listing.id if listing else 999}/details", params={"uid": 222})


def test_details_shows_where_else_it_was_posted_the_facts_and_the_timeline(client):
    resp = _get_details(
        client, _listing(), also_on=[{"n": "קומו", "u": "/go/8"}, {"n": "הומלס", "u": "/go/9"}],
    )

    assert resp.status_code == 200
    html = resp.text
    assert "המודעה הזאת הועלתה גם ב:" in html
    assert 'href="/go/8"' in html and 'href="/go/9"' in html
    assert "המודעה הזאת מיד2" in html
    assert "פרטי הנכס" in html
    assert "2 מתוך 5" in html
    assert "75 מ״ר" in html
    assert "80 ₪" in html  # price per m²: 6000 / 75
    assert "01.11.2026" in html
    assert "פרטי, בלי תיווך" in html
    assert "לא מרוהטת" in html
    assert "ממ״ד בדירה" in html
    assert "המחיר ירד מ-6,500 ₪ ל-6,000 ₪" in html
    assert "טודירה מצאה אותה" in html
    assert "עדיין באוויר" in html
    assert 'class="ld-map" data-lat="32.056000" data-lng="34.770000"' in html
    # The real source URL never sits in this fragment - every outbound link goes through /go/<id>.
    assert "secret-source-url" not in html


def test_details_lists_known_amenities_either_way_and_leaves_unknown_ones_out(client):
    html = _get_details(client, _listing()).text

    assert 'class="ld-amenity yes"' in html and "חניה" in html  # has_parking True
    assert 'class="ld-amenity no"' in html and "מעלית" in html  # has_elevator False
    assert "מרפסת" not in html  # has_balcony unknown


def test_details_says_when_no_other_site_has_it(client):
    html = _get_details(client, _listing()).text

    assert "לא מצאנו אותה באתרים אחרים, רק ביד2" in html
    assert "הועלתה גם ב:" not in html


@pytest.mark.parametrize(
    ("diff_pct", "expected"),
    [(-12, "זולה ב-12% מהמחיר הרגיל באזור"), (9, "יקרה ב-9% מהמחיר הרגיל באזור"), (3, "בדיוק במחיר הרגיל באזור")],
)
def test_details_compares_the_price_with_the_area(client, diff_pct, expected):
    area = {"area": "פלורנטין", "median": 6500, "count": 23, "diff_pct": diff_pct, "solid": True, "sqm_median": None}
    html = _get_details(client, _listing(), area=area).text

    assert expected in html
    assert "המחיר האמצעי לדירות 3 חדרים בפלורנטין: 6,500 ₪" in html
    assert "לפי 23 מודעות מהחודש האחרון" in html
    assert "כדאי להתייחס בזהירות" not in html
    assert "למ״ר:" not in html


def test_details_explains_exactly_how_the_area_price_was_worked_out(client):
    area = {"area": "פלורנטין", "median": 6500, "count": 6, "diff_pct": -8, "solid": False, "sqm_median": 92}
    html = _get_details(client, _listing(price=6000, size_sqm=75), area=area).text

    assert "איך חישבנו את זה?" in html
    assert "מתוך 6 מודעות של דירות 3 חדרים להשכרה בפלורנטין שראינו ב־30 הימים האחרונים" in html
    assert "לא המחירים שנסגרו בפועל" in html
    assert "מבוסס על מעט מודעות (6), כדאי להתייחס בזהירות" in html
    assert "למ״ר: 80 ₪ כאן, לעומת 92 ₪ בדרך כלל" in html


def test_details_leaves_the_area_comparison_out_without_enough_data(client):
    html = _get_details(client, _listing(), area=None).text

    assert "המחיר ביחס לאזור" not in html


def test_details_shows_similar_listings_as_deep_links(client):
    similar = [_listing(id=11, price=5800, rooms=Decimal("3.5"), image_urls=["https://img.example/a.jpg"])]
    html = _get_details(client, _listing(), similar=similar).text

    assert "דירות דומות באזור" in html
    assert 'href="/apartments?listing=11"' in html
    assert "5,800 ₪" in html
    assert "3.5 חד׳" in html


def test_details_marks_a_delisted_listing_as_taken_down(client):
    listing = _listing(is_delisted=True, delisted_at=_NOW - dt.timedelta(days=1))
    html = _get_details(client, listing).text

    assert "ירדה מהאתר" in html
    assert "עדיין באוויר" not in html


def test_details_survives_a_listing_with_almost_nothing_known(client):
    bare = _listing(
        property_type=None, previous_price=None, price_changed_at=None, rooms=None, floor=None, floor_total=None,
        size_sqm=None, neighborhood=None, street=None, latitude=None, longitude=None, has_parking=None,
        has_elevator=None, is_renovated=None, safe_room_type=None, furniture=None, is_broker_listing=None,
        move_in_date=None, posted_at=None,
    )
    resp = _get_details(client, bare)

    assert resp.status_code == 200
    assert "פיצ׳רים בדירה" not in resp.text
    assert 'class="ld-map"' not in resp.text
    assert "📍 תל אביב יפו" in resp.text


def test_details_ground_floor_reads_as_ground(client):
    html = _get_details(client, _listing(floor=0, floor_total=None)).text

    assert "<dd>קרקע</dd>" in html


def test_details_404s_for_a_missing_listing(client):
    assert _get_details(client, None).status_code == 404


@pytest.mark.no_uid_shim
def test_details_401s_without_a_signed_in_user(client):
    session = _FakeSession(None, _listing())
    with patch.object(website_main, "get_session", _fake_get_session(session)):
        resp = client.get("/apartments/listing/7/details")

    assert resp.status_code == 401


class _MedianSession:
    """Answers _area_price_comparison's queries in order: the neighborhood one first (when there is a neighborhood),
    then the city one."""

    def __init__(self, *rows):
        self._rows = list(rows)
        self.statements = []

    def execute(self, stmt):
        self.statements.append(stmt)
        row = self._rows.pop(0)
        return SimpleNamespace(one=lambda: row)


def _sql(stmt) -> str:
    from sqlalchemy.dialects import postgresql

    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_area_comparison_uses_the_neighborhood_when_it_has_enough_listings():
    session = _MedianSession((Decimal("6500"), 12), (86.4, 9))
    result = website_main._area_price_comparison(session, _listing(price=6000))

    assert result == {
        "area": "פלורנטין", "median": 6500, "count": 12, "diff_pct": -8, "solid": True, "sqm_median": 86, "sqm_count": 9,
    }
    assert len(session.statements) == 2
    assert "listings.neighborhood = 'פלורנטין'" in _sql(session.statements[0])
    assert "listings.size_sqm BETWEEN 15 AND 500" in _sql(session.statements[1])


def test_area_comparison_falls_back_to_the_city_and_flags_a_small_sample():
    session = _MedianSession((Decimal("6500"), 2), (Decimal("5000"), 7), (None, 0))
    result = website_main._area_price_comparison(session, _listing(price=6000))

    assert result == {"area": "תל אביב יפו", "median": 5000, "count": 7, "diff_pct": 20, "solid": False, "sqm_median": None}
    assert "neighborhood" not in _sql(session.statements[1])


def test_area_comparison_needs_enough_listings_and_a_price():
    assert website_main._area_price_comparison(_MedianSession((Decimal("6500"), 2), (6400, 4)), _listing()) is None
    assert website_main._area_price_comparison(_MedianSession(), _listing(price=None)) is None


def test_area_comparison_treats_the_rest_of_the_city_bucket_as_the_city():
    session = _MedianSession((Decimal("2500"), 5))
    website_main._area_price_comparison(session, _listing(neighborhood="שאר העיר", size_sqm=None))

    assert len(session.statements) == 1
    assert "neighborhood" not in _sql(session.statements[0])


def test_area_comparison_only_counts_real_peers():
    """Last 30 days (taken-down ones included), no duplicates, never this flat, same rooms and deal, and a shared room
    only against shared rooms."""
    session = _MedianSession((Decimal("6500"), 5))
    website_main._area_price_comparison(session, _listing(neighborhood=None, size_sqm=None, duplicate_of_id=3))
    sql = _sql(session.statements[0])

    assert "percentile_cont(0.5) WITHIN GROUP (ORDER BY listings.price)" in sql
    assert "listings.scraped_at >= now() - " in sql
    assert "is_delisted" not in sql
    assert "listings.duplicate_of_id IS NULL" in sql
    assert "listings.id != 7" in sql and "listings.id != 3" in sql
    assert "listings.deal_type = 'rent'" in sql and "listings.rooms = 3.0" in sql
    assert "listings.property_type != 'shared_room'" in sql

    shared = _MedianSession((Decimal("1500"), 5))
    website_main._area_price_comparison(shared, _listing(property_type="shared_room", neighborhood=None, size_sqm=None))
    assert "listings.property_type = 'shared_room'" in _sql(shared.statements[0])


def test_details_order_facts_then_features_then_area_price(client):
    # 2026-10-18 (owner): property details first (the description goes right under them, placed by apartments.html),
    # then the features, renamed, and the price-for-the-area comparison lower down.
    area = SimpleNamespace(diff_pct=-12.0, median=6800, count=40, area="לב העיר", sqm_median=None, solid=True)
    html = _get_details(client, _listing(), area=area).text

    top = html.index('data-slot="top"')
    after_desc = html.index('data-slot="after-desc"')
    middle = html.index('data-slot="middle"')
    assert top < html.index("פרטי הנכס") < after_desc
    assert after_desc < html.index("פיצ׳רים בדירה") < html.index("ld-insight") < middle


def test_apartments_sort_orders():
    rows = [(3, 5000), (2, None), (1, 4000)]  # newest first, as the match scan returns them
    assert website_main._sorted_ids(rows, "new") == [3, 2, 1]
    assert website_main._sorted_ids(rows, "old") == [1, 2, 3]
    assert website_main._sorted_ids(rows, "cheap") == [1, 3, 2]
    assert website_main._sorted_ids(rows, "expensive") == [3, 1, 2]


def test_report_needs_a_signed_in_visitor_and_a_known_reason():
    from fastapi.testclient import TestClient

    client = TestClient(website_main.app)
    assert client.post("/api/report", data={"listing": "5", "reason": "taken"}).status_code == 400
def test_mini_app_init_data_check():
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import urlencode

    token = "123:abc"
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 42, "first_name": "A"})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    good = urlencode({**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})
    assert website_main.verify_webapp_init_data(good, token)["id"] == 42
    assert website_main.verify_webapp_init_data(good, "other:token") is None
    assert website_main.verify_webapp_init_data(good.replace("42", "43"), token) is None

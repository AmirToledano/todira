"""2026-10-31: a page per city for people searching Google (website/city_pages.py)."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_city_pages", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402

PAGE = {
    "city": "חיפה", "total": 155, "week": 28, "gone_days": 9,
    "by_rooms": [{"rooms": 3, "median": 4060, "count": 51}, {"rooms": 5, "median": 5190, "count": 12}],
    "neighborhoods": [{"name": "הדר", "median": 3500, "count": 12}],
    "newest": [{"price": 3900, "rooms": 3, "neighborhood": "הדר", "street": None, "size": 70,
                "photo": "https://example.invalid/p.jpg", "link": "/s/abc", "first_seen_at": None}],
}


class _NoDatabase:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(website_main, "get_session", _NoDatabase)
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_a_city_page_shows_our_numbers_and_the_way_in(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "city_page", lambda session, city: PAGE)
    monkeypatch.setattr(website_main.city_pages, "city_index", lambda session: [])  # 2026-11-02 (growth): other-cities row
    resp = client.get("/rent/חיפה?lang=he")
    assert resp.status_code == 200
    text = resp.text
    assert "<title>דירות להשכרה בחיפה: מחירים עדכניים ודירות חדשות | טודירה</title>" in text
    assert "לפי 155 דירות שעלו ב־30 הימים האחרונים" in text  # the meta description
    assert "חצי מהדירות כאן ירדו מהאוויר תוך 9 ימים." in text
    assert "₪4,060" in text and "5+" in text and "הדר" in text
    assert 'href="/s/abc"' in text and "t.me/AmirDirotBot?start=rent_city" in text


def test_no_page_for_a_place_that_is_not_a_locality_or_has_too_few_flats(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "city_page", lambda session, city: None)
    assert client.get("/rent/not-a-city").status_code == 404
    assert client.get("/rent/חיפה").status_code == 404


def test_the_index_links_every_city(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "city_index", lambda session: [
        {"city": "תל אביב יפו", "count": 900, "median3": 7200}, {"city": "חיפה", "count": 155, "median3": None},
    ])
    text = client.get("/rent?lang=he").text
    assert "/rent/%D7%AA%D7%9C%20%D7%90%D7%91%D7%99%D7%91%20%D7%99%D7%A4%D7%95" in text and "₪7,200" in text
    sitemap = client.get("/sitemap.xml").text
    assert "/rent/%D7%97%D7%99%D7%A4%D7%94" in sitemap and "/rent<" in sitemap


# 2026-10-31: every city is now built from one pass over the window (the first live visits took 16 s). The numbers must
# stay the ones the per-city SQL gave: medians like percentile_cont(0.5), the same thresholds and the same newest flats.
import datetime as dt  # noqa: E402
from decimal import Decimal  # noqa: E402

import city_pages  # noqa: E402

NOW = dt.datetime(2026, 10, 31, 12, 0, tzinfo=dt.timezone.utc)


class _Rows:
    def __init__(self, rows):
        self.rows = rows
        self.queries = 0

    def execute(self, query):
        self.queries += 1
        return iter(self.rows)


def _row(listing_id, city, *, rooms=3, price=4000, days_ago=1, hood="הדר", gone_after=None, photo="https://x.invalid/p.jpg",
         delisted=False):
    first_seen = NOW - dt.timedelta(days=days_ago)
    delisted_at = first_seen + dt.timedelta(days=gone_after) if gone_after is not None else None
    return (listing_id, city, hood, None, Decimal(str(rooms)), price, 70, first_seen, delisted_at,
            delisted or delisted_at is not None, photo)


def test_one_pass_builds_the_index_and_every_page():
    rows = []
    for i in range(30):  # Haifa: 30 flats, enough for a page; 3-room prices 3000..5900
        rows.append(_row(i, "חיפה", price=3000 + 100 * i, days_ago=1 + i % 28,
                         gone_after=(4 if i % 28 >= 14 else None)))
    rows += [_row(100 + i, "חיפה", rooms=5.5, price=7000 + i) for i in range(5)]  # the 5+ bucket
    rows += [_row(200 + i, "עכו", price=3000) for i in range(29)]  # one short of a page
    session = _Rows(rows)
    index, pages = city_pages.build(session, NOW)
    assert session.queries == 1
    assert index == [{"city": "חיפה", "count": 35, "median3": 4450}]
    page = pages["חיפה"]
    assert "עכו" not in pages
    # this week: Haifa rows 0-6 (days 1-7), 28 and 29 (days 1 and 2), and the five 5.5-room flats
    assert page["total"] == 35 and page["week"] == 7 + 2 + 5
    assert page["by_rooms"] == [{"rooms": 3, "median": 4450, "count": 30}, {"rooms": 5, "median": 7000, "count": 5}]
    assert page["neighborhoods"] == [{"name": "הדר", "median": 4450, "count": 30}]
    assert page["gone_days"] == 4  # rows 14-27 went in 4 days, row 13 (14 days old) is still up
    # live, newest first, the higher id first on the same day: day 1 is 100-104, 28 and 0, then day 2 has 29 and 1
    assert [flat["link"] for flat in page["newest"]] == [
        city_pages.share.share_path(i) for i in (104, 103, 102, 101, 100, 28, 0, 29)
    ]


def test_slow_cities_show_no_days_and_only_live_flats_with_photos_are_newest():
    rows = [_row(i, "חיפה", days_ago=20, gone_after=(15 if i % 2 else None), photo=None if i < 25 else "p",
                 delisted=i == 29) for i in range(30)]
    _, pages = city_pages.build(_Rows(rows), NOW)
    assert pages["חיפה"]["gone_days"] is None  # half still up after 20 days
    # photos only on 25-29; the odd ones went down (and 29 is marked down too)
    assert [flat["link"] for flat in pages["חיפה"]["newest"]] == [
        city_pages.share.share_path(i) for i in (28, 26)
    ]


def test_a_request_uses_the_built_copy_and_only_one_build_runs(monkeypatch):
    builds = []
    monkeypatch.setattr(city_pages, "build", lambda session, now: builds.append(now) or ([{"city": "x"}], {"x": {"t": 1}}))
    monkeypatch.setattr(city_pages, "_snapshot", {"at": None, "index": None, "pages": None})
    assert city_pages.city_index(object()) == [{"city": "x"}]
    assert city_pages.city_page(object(), "x") == {"t": 1} and city_pages.city_page(object(), "y") is None
    assert len(builds) == 1
    monkeypatch.setitem(city_pages._snapshot, "at", city_pages.time.monotonic() - city_pages.TTL_SECONDS - 1)
    city_pages.city_index(object())
    assert len(builds) == 2


@pytest.mark.skipif(not os.environ.get("TODIRA_TEST_DATABASE_URL"), reason="needs a real Postgres")
def test_the_one_query_runs_on_postgres():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(os.environ["TODIRA_TEST_DATABASE_URL"])
    with Session(engine) as session:
        index, pages = city_pages.build(session, dt.datetime.now(dt.timezone.utc))
    assert isinstance(index, list) and isinstance(pages, dict)


# 2026-11-04 (owner): a page per neighbourhood, built in the same one pass as the cities.
HOOD = {
    "city": "חיפה", "name": "הדר", "total": 14,
    "by_rooms": [{"rooms": 3, "median": 3500, "count": 9, "city_median": 4060, "diff": -14},
                 {"rooms": 5, "median": 5300, "count": 5, "city_median": 5190, "diff": 2}],
    "newest": [{"price": 3400, "rooms": 3, "neighborhood": "הדר", "street": "החלוץ", "size": 60,
                "photo": "https://example.invalid/h.jpg", "link": "/s/hdr", "first_seen_at": None}],
}
HOOD["headline"] = HOOD["by_rooms"][0]
HAIFA = "/rent/%D7%97%D7%99%D7%A4%D7%94"
HADAR = "%D7%94%D7%93%D7%A8"


def test_a_neighbourhood_page_compares_with_its_city(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_page",
                        lambda session, city, name: HOOD if (city, name) == ("חיפה", "הדר") else None)
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_links", lambda session, city: ["הדר", "כרמל"])
    resp = client.get("/rent/חיפה/הדר?lang=he")
    assert resp.status_code == 200
    text = resp.text
    assert "<title>דירות להשכרה בהדר, חיפה: מחירים ודירות חדשות | טודירה</title>" in text
    assert "לפי 14 דירות שעלו ב־30 הימים האחרונים" in text  # the meta description
    assert "דירת 3 חד׳ כאן עולה בדרך כלל ₪3,500, 14% פחות מהמחיר האמצעי בחיפה." in text
    assert "₪4,060" in text and "-14%" in text and "+2%" in text
    assert 'href="/s/hdr"' in text and "החלוץ" in text and "t.me/AmirDirotBot?start=rent_hood" in text
    assert f'href="{HAIFA}"' in text  # back to the city page
    assert f'href="{HAIFA}/%D7%9B%D7%A8%D7%9E%D7%9C"' in text and f'href="{HAIFA}/{HADAR}"' not in text  # others only
    assert f'rel="canonical" href="{website_main.PUBLIC_BASE}{HAIFA[1:]}/{HADAR}"' in text
    body = text.split('class="guide rent"', 1)[1].split("<footer", 1)[0]
    assert "—" not in body and "–" not in body


def test_an_english_neighbourhood_page(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_page", lambda session, city, name: HOOD)
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_links", lambda session, city: [])
    text = client.get("/rent/חיפה/הדר?lang=en").text
    assert "<title>Flats for rent in הדר, חיפה: prices and new flats | Todira</title>" in text
    assert "A 3-room flat here usually costs ₪3,500, 14% less than the median in חיפה." in text


def test_an_unknown_neighbourhood_is_a_404(client, monkeypatch):
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_page", lambda session, city, name: None)
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_links", lambda session, city: [])
    assert client.get("/rent/חיפה/no-such-place").status_code == 404
    assert client.get("/rent/not-a-city/הדר").status_code == 404


def test_the_city_page_links_its_neighbourhoods_and_the_sitemap_lists_them(client, monkeypatch):
    page = dict(PAGE, hood_links=["הדר"], hood_pages={"הדר": HOOD})
    monkeypatch.setattr(website_main.city_pages, "city_page", lambda session, city: page)
    monkeypatch.setattr(website_main.city_pages, "city_index", lambda session: [{"city": "חיפה", "count": 155, "median3": 1}])
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_index", lambda session: [("חיפה", "הדר"), ("חיפה", "א/ב")])
    text = client.get("/rent/חיפה?lang=he").text
    assert "<h2>שכונות</h2>" in text
    assert text.count(f'href="{HAIFA}/{HADAR}"') == 2  # the row and the 3-room table
    sitemap = client.get("/sitemap.xml").text
    assert f"{HAIFA}/{HADAR}<" in sitemap and f"{HAIFA}/%D7%90%2F%D7%91<" in sitemap


def test_a_name_with_a_slash_still_reaches_its_page(client, monkeypatch):
    seen = []
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_page",
                        lambda session, city, name: seen.append(name) or dict(HOOD, name=name))
    monkeypatch.setattr(website_main.city_pages, "neighbourhood_links", lambda session, city: [])
    resp = client.get(f"{HAIFA}/%D7%90%2F%D7%91?lang=en")
    assert resp.status_code == 200 and seen == ["א/ב"]
    assert f'rel="canonical" href="{website_main.PUBLIC_BASE}{HAIFA[1:]}/%D7%90%2F%D7%91?lang=en"' in resp.text
    # 2026-11-04: other pages' canonical is the quoted path (a space in a city name was printed raw before)
    monkeypatch.setattr(website_main.city_pages, "city_page", lambda session, city: PAGE)
    monkeypatch.setattr(website_main.city_pages, "city_index", lambda session: [])
    text = client.get("/rent/תל אביב יפו").text
    assert f'rel="canonical" href="{website_main.PUBLIC_BASE}rent/%D7%AA%D7%9C%20%D7%90' in text


def test_neighbourhood_pages_from_the_same_one_pass():
    rows = [_row(i, "חיפה", price=4000 + 10 * i, hood=None) for i in range(20)]  # no neighbourhood given
    rows += [_row(100 + i, "חיפה", price=5000, hood="כרמל") for i in range(6)]  # Carmel, 3 rooms
    rows += [_row(200 + i, "חיפה", rooms=4, price=6000, hood="כרמל", photo=None) for i in range(4)]  # 10 in Carmel
    rows += [_row(300 + i, "חיפה", hood="נווה שאנן") for i in range(9)]  # one short of a page
    rows += [_row(400 + i, "חיפה", hood="שאר העיר") for i in range(12)]  # never a page
    rows += [_row(500 + i, "חיפה", rooms=2, hood=" בת גלים ") for i in range(4)]  # 10 flats, no rooms row with 5
    rows += [_row(510 + i, "חיפה", rooms=4, hood="בת גלים") for i in range(4)]
    rows += [_row(520 + i, "חיפה", rooms=1, hood="בת גלים") for i in range(2)]
    rows += [_row(600 + i, "עכו", hood="העיר העתיקה") for i in range(12)]  # Akko has no city page, so no hood page
    session = _Rows(rows)
    index, pages = city_pages.build(session, NOW)
    assert session.queries == 1 and "עכו" not in pages
    page = pages["חיפה"]
    assert page["hood_links"] == ["כרמל"] and set(page["hood_pages"]) == {"כרמל"}
    carmel = page["hood_pages"]["כרמל"]
    city3 = next(r["median"] for r in page["by_rooms"] if r["rooms"] == 3)
    assert carmel["total"] == 10 and carmel["city"] == "חיפה"
    assert carmel["by_rooms"] == [{"rooms": 3, "median": 5000, "count": 6, "city_median": city3,
                                   "diff": round((5000 - city3) * 100 / city3)}]
    assert carmel["headline"] == carmel["by_rooms"][0]
    # only live flats with a photo, newest first: Carmel's 3-room ones (its 4-room ones have none)
    assert [f["link"] for f in carmel["newest"]] == [city_pages.share.share_path(i) for i in range(105, 99, -1)]
    city_pages._snapshot.update(at=city_pages.time.monotonic(), index=index, pages=pages)
    try:
        assert city_pages.neighbourhood_page(object(), "חיפה", "כרמל") is carmel
        assert city_pages.neighbourhood_page(object(), "חיפה", "שאר העיר") is None
        assert city_pages.neighbourhood_page(object(), "עכו", "העיר העתיקה") is None
        assert city_pages.neighbourhood_links(object(), "חיפה") == ["כרמל"]
        assert city_pages.neighbourhood_index(object()) == [("חיפה", "כרמל")]
    finally:
        city_pages._snapshot.update(at=None, index=None, pages=None)


def test_the_city_newest_list_is_unchanged_by_the_neighbourhood_lists():
    # odd ids in הדר, even ones in כרמל; day 1 has ids 0 and 20, day 2 has 1 and 21, and so on
    rows = [_row(i, "חיפה", days_ago=1 + i % 20, hood=("הדר" if i % 2 else "כרמל")) for i in range(30)]
    _, pages = city_pages.build(_Rows(rows), NOW)
    links = lambda ids: [city_pages.share.share_path(i) for i in ids]  # noqa: E731
    assert [f["link"] for f in pages["חיפה"]["newest"]] == links((20, 0, 21, 1, 22, 2, 23, 3))
    assert [f["link"] for f in pages["חיפה"]["hood_pages"]["הדר"]["newest"]] == links((21, 1, 23, 3, 25, 5, 27, 7))
    assert [f["link"] for f in pages["חיפה"]["hood_pages"]["כרמל"]["newest"]] == links((20, 0, 22, 2, 24, 4, 26, 6))

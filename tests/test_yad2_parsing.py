"""Unit tests for the pure HTML-parsing helpers in scraper/yad2_client.py (_parse_cards and its
sub-parsers). These are the most fragile part of the scraper — Yad2 can change its markup at any
time with no warning — and had zero test coverage before this. Deliberately does NOT test
fetch_search_results (needs a real network round-trip, out of scope for this dependency-light
suite, same reasoning as the other tests/ modules).

The sample HTML fragments below mirror the exact structure documented in yad2_client.py's module
docstring and scraper/YAD2_NOTES.md's "Attempt 9: SOLVED" section (data-testid spans inside an
<a data-nagish="feed-item-layout-link" href="..."> with an "itemLink" class) — not arbitrary
guesses at real Yad2 HTML.
"""
from yad2_client import _clean, _parse_cards, _parse_info_line_2, _parse_location, _parse_price


def _card_html(href: str, price: str, street: str, info1: str, info2: str) -> str:
    return (
        f'<li data-testid="platinum-item"><a class="itemLink_link__abc123" '
        f'data-nagish="feed-item-layout-link" href="{href}">'
        f'<span data-testid="price">{price}</span>'
        f'<span data-testid="street-name">{street}</span>'
        f'<span data-testid="item-info-line-1st">{info1}</span>'
        f'<span data-testid="item-info-line-2nd">{info2}</span>'
        f"</a></li>"
    )


# --- _parse_price ---


def test_parse_price_strips_currency_and_thousands_separator():
    assert _parse_price("8,500 ₪") == 8500


def test_parse_price_no_digits_returns_none():
    assert _parse_price("לא צוין") is None


# --- _parse_info_line_2 ---


def test_parse_info_line_2_full():
    rooms, floor, size = _parse_info_line_2('3 חדרים • קומה 2 • 75 מ"ר')
    assert rooms == 3.0
    assert floor == 2
    assert size == 75


def test_parse_info_line_2_ground_floor():
    _, floor, _ = _parse_info_line_2('2 חדרים • קומה קרקע • 50 מ"ר')
    assert floor == 0


def test_parse_info_line_2_half_room_and_missing_parts():
    rooms, floor, size = _parse_info_line_2("2.5 חדרים")
    assert rooms == 2.5
    assert floor is None
    assert size is None


# --- _parse_location ---


def test_parse_location_with_neighborhood():
    neighborhood, city = _parse_location("דירה, מרכז העיר, רמת גן")
    assert neighborhood == "מרכז העיר"
    assert city == "רמת גן"


def test_parse_location_without_neighborhood():
    # Only property type + city — no middle segment, matching _parse_cards' real-world case where
    # Yad2 sometimes omits the neighborhood breadcrumb entirely.
    neighborhood, city = _parse_location("דירה, רמת גן")
    assert neighborhood is None
    assert city == "רמת גן"


def test_parse_location_empty_returns_none_none():
    assert _parse_location("") == (None, None)


# --- _clean ---


def test_clean_strips_direction_marks():
    assert _clean("‎8,500 ₪‏") == "8,500 ₪"


# --- _parse_cards (the real integration point) ---


def test_parse_cards_extracts_a_normal_listing():
    html = _card_html(
        href="/item/abcd1234",
        price="8,500 ₪",
        street="ביאליק 10",
        info1="דירה, מרכז העיר, רמת גן",
        info2='3 חדרים • קומה 2 • 75 מ"ר',
    )
    items = list(_parse_cards(html))
    assert len(items) == 1
    item = items[0]
    assert item["id"] == "abcd1234"
    assert item["url"] == "https://www.yad2.co.il/item/abcd1234"
    assert item["price"] == 8500
    assert item["rooms"] == 3.0
    assert item["floor"] == 2
    assert item["square_meters"] == 75
    assert item["street"] == "ביאליק 10"
    assert item["neighborhood"] == "מרכז העיר"
    assert item["city"] == "רמת גן"


def test_parse_cards_skips_sponsored_project_cards():
    # Sponsored "new project" cards use an absolute URL under /yad1/project/ — _parse_cards must
    # skip these (see the comment above the check in yad2_client.py), not treat them as a listing.
    project_card = _card_html(
        href="https://www.yad2.co.il/yad1/project/98765",
        price="1,900,000 ₪",
        street="פרויקט חדש",
        info1="פרויקט, רמת גן",
        info2="עד 5 חדרים",
    )
    real_card = _card_html(
        href="/item/real1",
        price="7,200 ₪",
        street="הרצל 5",
        info1="דירה, גבעתיים",
        info2='2 חדרים • קומה 1 • 55 מ"ר',
    )
    items = list(_parse_cards(project_card + real_card))
    assert len(items) == 1
    assert items[0]["id"] == "real1"
    assert items[0]["city"] == "גבעתיים"


def test_parse_cards_multiple_real_listings():
    html = "".join(
        [
            _card_html("/item/one", "5,000 ₪", "א", "דירה, תל אביב יפו", "2 חדרים"),
            _card_html("/item/two", "6,000 ₪", "ב", "דירה, חיפה", "3 חדרים"),
        ]
    )
    items = list(_parse_cards(html))
    assert [item["id"] for item in items] == ["one", "two"]
    assert [item["city"] for item in items] == ["תל אביב יפו", "חיפה"]


def test_parse_cards_empty_html_yields_nothing():
    assert list(_parse_cards("<html><body>no cards here</body></html>")) == []

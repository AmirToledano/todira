"""Unit tests for scraper/homeless_client.py. Sample HTML fragments are the exact real cards
confirmed live against homeless.co.il/rent/ and /sale/ (see
.github/workflows/diagnose-homeless-pagination.yaml's real output, 2026-09-24, after a real site
redesign moved the listing grid from <tr> table rows to a <div>-based card layout — see
homeless_client.py's own module docstring) — not invented shapes. Mocks httpx.get directly rather
than hitting the network, no real ZenRows credits spent by running this suite, same reasoning as
test_yad2_client.py/test_komo_client.py."""
import httpx
import pytest

from homeless_client import (
    SALE_SEARCH_PAGE_URL,
    SEARCH_PAGE_URL,
    ZENROWS_API_KEY_ENV_VAR,
    HomelessFetchError,
    _parse_cards,
    fetch_listing_description,
    fetch_search_results,
)

# Confirmed live 2026-09-13 (diagnose-komo-gallery-and-homeless-description.yaml) against a real
# listing's own detail page (id=746758) — not invented. Unaffected by the 2026-09-24 search-page
# redesign (a different page).
_REAL_DETAIL_PAGE_HTML = (
    '<meta name="Description" content="דירה להשכרה בתל אביב, דרך השלום מודעה 746758 -  '
    'הכניסה מרחוב הורודצקי. זו הכניסה השקטה של הבניין.">'
    '<meta property="og:description" content="דירה להשכרה בתל אביב, דרך השלום מודעה 746758 -  '
    'הכניסה מרחוב הורודצקי. זו הכניסה השקטה של הבניין.">'
)

# --- real confirmed cards (see module docstring) ---

# A real rent card, confirmed live 2026-09-24 (diagnose-homeless-pagination.yaml) — no neighborhood
# (nothing after the trailing "•" on its own h3 first line, a real, genuinely absent value).
_REAL_RENT_CARD_NO_NEIGHBORHOOD = (
    '<div id="ad_710102" class="image-carousel">    '
    '<div>'
    '<a class="R promotedAd" style="background-color: unset;" href="/rent/viewad,710102.aspx" '
    'title="דירה, 3 חדרים, שד.מנחם בגין, כפר הים  ">'
    '<img src="https://uploads.homeless.co.il/rent/202405/300/nvFile5334656.jpeg" '
    'alt="דירה, 3 חדרים, שד.מנחם בגין, כפר הים  ">'
    ' <div class="promotedAdLabel">מקודמת</div>'
    '<div class="price">'
    '   6,000 ₪'
    '</div>'
    '<h3 class="desc" style="font-size: 14px; font-weight: normal; margin: 0; padding: 0; '
    'line-height: 1.4; ">'
    ''
    '   <span>דירה</span>&nbsp;להשכרה ברמת אביב&nbsp;•&nbsp;'
    ''
    '<div class="custom-divider"></div>'
    ''
    '    2.5 חדרים • 40 מ"ר • קומה 2 '
    '</h3>'
    '</a>'
    '<input type="checkbox" id="chk_746287" name="chk_746287" class="markmessage">'
    '<label for="chk_746287">'
    '<img class="LikeAd" src="/images/BoardImages/LikeAd-gray.svg" alt="Like Ad" '
    'id="likeAd_746287" style="cursor: pointer;">'
    '</label>'
    '</div>'
    '</div>'
)

# A real sale card, confirmed live 2026-09-24 — HAS a real neighborhood (text after the "•" on its
# own h3 first line), and confirms square_meters (מ"ר) is now a real, populated field (never
# present at all in the old <tr> table layout — see module docstring).
_REAL_SALE_CARD_WITH_NEIGHBORHOOD = (
    '<div id="ad_253432" class="image-carousel">    '
    '<div>'
    '<a class="R promotedAd" style="background-color: unset;" href="/sale/viewad,253432.aspx" '
    'title="דירה, 6 חדרים, שאול חרנם 6 , פתח תקווה פז  ">'
    '<img src="https://uploads.homeless.co.il/sale/202512/300/nvFile5111325.jpeg" '
    'alt="דירה, 6 חדרים, שאול חרנם 6 , פתח תקווה פז  ">'
    ' <div class="promotedAdLabel">מקודמת</div>'
    '<div class="price">'
    '   3,700,000 ₪'
    '</div>'
    '<h3 class="desc" style="font-size: 14px; font-weight: normal; margin: 0; padding: 0; '
    'line-height: 1.4; ">'
    ''
    '   <span>דירה</span>&nbsp;למכירה בפתח תקווה פז&nbsp;•&nbsp;פסגת הדר נווה עוז'
    ''
    '<div class="custom-divider"></div>'
    ''
    '    6 חדרים • 164 מ"ר • קומה 6 '
    '</h3>'
    '</a>'
    '<input type="checkbox" id="chk_253432" name="chk_253432" class="markmessage">'
    '</div>'
    '</div>'
)


# --- _parse_cards (the real integration point) ---


def test_parse_cards_extracts_the_real_confirmed_rent_card_without_neighborhood():
    items = list(_parse_cards(_REAL_RENT_CARD_NO_NEIGHBORHOOD))
    assert len(items) == 1
    assert items[0] == {
        "id": "710102",
        "url": "https://www.homeless.co.il/rent/viewad,710102.aspx",
        "price": 6000,
        "rooms": 2.5,
        "floor": 2,
        "square_meters": 40,
        "street": "שד.מנחם בגין",
        "neighborhood": None,
        "city": "כפר הים",
        "images": ["https://uploads.homeless.co.il/rent/202405/300/nvFile5334656.jpeg"],
    }


def test_parse_cards_extracts_the_real_confirmed_sale_card_with_neighborhood():
    items = list(_parse_cards(_REAL_SALE_CARD_WITH_NEIGHBORHOOD))
    assert len(items) == 1
    assert items[0] == {
        "id": "253432",
        "url": "https://www.homeless.co.il/sale/viewad,253432.aspx",
        "price": 3700000,
        "rooms": 6.0,
        "floor": 6,
        "square_meters": 164,
        "street": "שאול חרנם 6",
        "neighborhood": "פסגת הדר נווה עוז",
        "city": "פתח תקווה פז",
        "images": ["https://uploads.homeless.co.il/sale/202512/300/nvFile5111325.jpeg"],
    }


def test_parse_cards_empty_src_yields_no_images_not_a_placeholder():
    # A blank src="" (a real possible shape — e.g. a listing with no uploaded photo yet) must
    # degrade to an empty list, not a list containing an empty string.
    card = (
        '<div id="ad_1" class="image-carousel">'
        '<a href="/rent/viewad,1.aspx" title="דירה, 3 חדרים, הרצל, חיפה">'
        '<img src="" alt="">'
        '<div class="price">4,000 ₪</div>'
        '<h3>חדרים <div class="custom-divider"></div>3 חדרים • קומה 1</h3>'
        '</a>'
        '</div>'
    )
    items = list(_parse_cards(card))
    assert items[0]["images"] == []


def test_parse_cards_no_floor_or_sqm_in_h3_degrades_to_none_not_a_miscapture():
    # A real, genuine gap (e.g. a brokered listing whose h3 line never mentions קומה/מ"ר at all)
    # must leave those fields None, never silently pick up an unrelated number.
    card = (
        '<div id="ad_2" class="image-carousel">'
        '<a href="/rent/viewad,2.aspx" title="דירה, 2 חדרים, אלנבי, תל אביב">'
        '<img src="x.jpg" alt="">'
        '<div class="price">3,500 ₪</div>'
        '<h3>דירה להשכרה <div class="custom-divider"></div>2 חדרים</h3>'
        '</a>'
        '</div>'
    )
    items = list(_parse_cards(card))
    assert items[0]["rooms"] == 2.0
    assert items[0]["floor"] is None
    assert items[0]["square_meters"] is None


def test_parse_cards_multiple_real_cards_in_one_page():
    items = list(
        _parse_cards(_REAL_RENT_CARD_NO_NEIGHBORHOOD + _REAL_SALE_CARD_WITH_NEIGHBORHOOD)
    )
    assert [item["id"] for item in items] == ["710102", "253432"]


def test_parse_cards_skips_a_card_with_no_real_link_instead_of_crashing(caplog):
    # No <a href=.../viewad,<id>.aspx ... title="..."> at all — the card's own markup changed
    # again in some way this project hasn't seen yet. Must be skipped with a clear warning, never
    # raise and never yield a bogus/partial item.
    malformed_card = '<div id="ad_999" class="image-carousel"><div>no link here</div></div>'
    items = list(_parse_cards(malformed_card + _REAL_RENT_CARD_NO_NEIGHBORHOOD))
    assert [item["id"] for item in items] == ["710102"]
    assert "Skipping Homeless card id=999" in caplog.text


def test_parse_cards_empty_html_yields_nothing():
    assert list(_parse_cards("<html><body>no cards here</body></html>")) == []


def test_parse_cards_a_real_tivuch_style_href_prefix_is_read_as_is_not_reconstructed():
    # A brokered ("Tivuch") listing has historically used a different real path prefix than a
    # plain one (/RentTivuch/ vs /rent/, found live 2026-09-13) — the href regex accepts any real
    # "/<prefix>/viewad,<id>.aspx" path, never assumes a fixed one.
    card = (
        '<div id="ad_3" class="image-carousel">'
        '<a href="/RentTivuch/viewad,3.aspx" title="דירה, 2 חדרים, הקונגרס, תל אביב יפו">'
        '<img src="x.jpg" alt="">'
        '<div class="price">5,600 ₪</div>'
        '<h3>דירה <div class="custom-divider"></div>2 חדרים</h3>'
        '</a>'
        '</div>'
    )
    items = list(_parse_cards(card))
    assert items[0]["url"] == "https://www.homeless.co.il/RentTivuch/viewad,3.aspx"


# --- fetch_search_results ---


def test_missing_api_key_raises_without_any_http_call(monkeypatch):
    monkeypatch.delenv(ZENROWS_API_KEY_ENV_VAR, raising=False)
    with pytest.raises(HomelessFetchError, match=ZENROWS_API_KEY_ENV_VAR):
        list(fetch_search_results())


def test_successful_fetch_sends_custom_headers_true_and_parses_cards(monkeypatch):
    # 2026-09-24: custom_headers=true (+ real browser headers) is REQUIRED for the search page
    # (real site redesign — see module docstring, point 1) — a plain fetch with ZenRows' own
    # default headers gets ZenRows' own RESP001 error, confirmed live. js_render=true is NOT used —
    # tested live and confirmed unnecessary (custom_headers=true fixes RESP001 at the same 1-credit
    # cost as before; js_render would cost 5x for no real benefit).
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return httpx.Response(
            200, text=_REAL_RENT_CARD_NO_NEIGHBORHOOD, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_search_results())

    assert len(items) == 1
    assert items[0]["id"] == "710102"
    assert captured["url"] == "https://api.zenrows.com/v1/"
    assert captured["params"]["apikey"] == "fake-key"
    assert captured["params"]["url"] == SEARCH_PAGE_URL
    assert captured["params"]["custom_headers"] == "true"
    assert "js_render" not in captured["params"]
    assert captured["headers"]["User-Agent"]
    assert captured["headers"]["Accept-Language"]


def test_fetch_search_results_accepts_the_sale_url_explicitly(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        return httpx.Response(
            200, text=_REAL_SALE_CARD_WITH_NEIGHBORHOOD, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    items = list(fetch_search_results(SALE_SEARCH_PAGE_URL))

    assert len(items) == 1
    assert items[0]["id"] == "253432"
    assert captured["params"]["url"] == SALE_SEARCH_PAGE_URL
    assert captured["params"]["custom_headers"] == "true"


def test_zenrows_error_body_raises_with_code_and_title(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    error_body = '{"code":"AUTH004","title":"Usage exceeded (AUTH004)"}'

    def fake_get(url, params, headers, timeout):
        return httpx.Response(200, text=error_body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(HomelessFetchError, match="AUTH004"):
        list(fetch_search_results())


def test_resp001_error_body_raises_with_code_and_title(monkeypatch):
    # The real, confirmed-live failure mode this rewrite was built to work around — kept as a
    # regression guard that the error itself is still surfaced clearly if it ever recurs (e.g. for
    # the still-untested detail-page fetch, or if Homeless changes something again).
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    error_body = (
        '{"code":"RESP001","title":"Could not get content. try enabling javascript '
        'rendering for a higher success rate (RESP001)"}'
    )

    def fake_get(url, params, headers, timeout):
        return httpx.Response(200, text=error_body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(HomelessFetchError, match="RESP001"):
        list(fetch_search_results())


def test_non_200_status_raises_homeless_fetch_error(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, headers, timeout):
        return httpx.Response(500, text="internal error", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(HomelessFetchError, match="http_status=500"):
        list(fetch_search_results())


def test_network_failure_fails_soft_as_homeless_fetch_error(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, headers, timeout):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(HomelessFetchError):
        list(fetch_search_results())


# --- fetch_listing_description (2026-09-13, unaffected by the 2026-09-24 search-page redesign) --


def test_fetch_listing_description_extracts_the_real_confirmed_description(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        return httpx.Response(
            200, text=_REAL_DETAIL_PAGE_HTML, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    # fetch_listing_description takes the listing's own real URL (as returned by
    # fetch_search_results/_parse_cards), not a bare id — a bare id can no longer be reconstructed
    # into the right URL, since brokered ("Tivuch") listings use a different path prefix
    # (/RentTivuch/ vs /rent/) that isn't derivable from the id alone.
    real_url = "https://www.homeless.co.il/rent/viewad,746758.aspx"
    description = fetch_listing_description(real_url)

    assert description == (
        "דירה להשכרה בתל אביב, דרך השלום מודעה 746758 -  הכניסה מרחוב הורודצקי. "
        "זו הכניסה השקטה של הבניין."
    )
    assert captured["params"]["url"] == real_url
    # Still the plain (cheaper) tier — not yet confirmed whether the detail page also needs
    # js_render after the search page's own 2026-09-24 redesign (see module docstring).
    assert "js_render" not in captured["params"]


def test_fetch_listing_description_missing_meta_tags_returns_none(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, headers, timeout):
        return httpx.Response(200, text="<html><body>no meta here</body></html>", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    assert fetch_listing_description("https://www.homeless.co.il/rent/viewad,746758.aspx") is None


def test_fetch_listing_description_rejects_the_sites_own_generic_description(monkeypatch):
    """2026-09-21: real bug found live (owner's Telegram screenshots) — 6 of a real 30-listing
    sample had the site's own generic <meta name="Description"> as their "description" instead of
    a real per-listing one, confirmed via a live DB dump. Must return None, not the boilerplate."""
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")
    generic_html = (
        '<html><head><meta name="Description" content="מחפש ? בלוח הומלס מחכה לך '
        'ועוד הרבה נדלן אחרות מתוך אינסוף מודעות עדכניות. הומלס - הרבה יותר מלוחות."></head></html>'
    )

    def fake_get(url, params, headers, timeout):
        return httpx.Response(200, text=generic_html, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    assert fetch_listing_description("https://www.homeless.co.il/rent/viewad,746758.aspx") is None


def test_fetch_listing_description_missing_api_key_returns_none_not_raises(monkeypatch):
    # Unlike fetch_search_results (which raises), this is genuinely optional enrichment — never
    # raises, same defensive contract as komo_client.fetch_listing_detail.
    monkeypatch.delenv(ZENROWS_API_KEY_ENV_VAR, raising=False)
    assert fetch_listing_description("https://www.homeless.co.il/rent/viewad,746758.aspx") is None


def test_fetch_listing_description_network_failure_returns_none_not_raises(monkeypatch):
    monkeypatch.setenv(ZENROWS_API_KEY_ENV_VAR, "fake-key")

    def fake_get(url, params, headers, timeout):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "get", fake_get)

    assert fetch_listing_description("https://www.homeless.co.il/rent/viewad,746758.aspx") is None

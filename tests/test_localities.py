"""2026-10-13 (owner request: "all the cities, moshavim, settlements, villages and areas"): every official locality
(Central Bureau of Statistics list, scripts/build_localities.py) and area can be chosen, typed and matched."""
from __future__ import annotations

from todira_common import cities
from todira_common.search_text import match_city_reply, parse, suggest_cities


def test_the_full_list_starts_with_the_major_cities_unchanged_and_has_no_duplicates():
    assert cities.LOCALITIES[: len(cities.CITIES)] == cities.CITIES  # old bot buttons carry these indexes
    assert len(cities.LOCALITIES) == len(set(cities.LOCALITIES)) > 1200
    assert "קדר" in cities.LOCALITY_SET and "כפר ורדים" in cities.LOCALITY_SET


def test_any_spelling_resolves_to_the_one_stored_name():
    assert cities.resolve_locality("תל אביב - יפו") == "תל אביב יפו"
    assert cities.resolve_locality('ת"א') == "תל אביב יפו"
    assert cities.resolve_locality("קרית מוצקין") == "קריית מוצקין"
    assert cities.resolve_locality("נצרת עילית / נוף הגליל") == "נוף הגליל"
    assert cities.resolve_locality("עפרה") == "עופרה"
    assert cities.resolve_locality("ג&rsquo;סר א זרקא") == cities.resolve_locality("ג'סר א-זרקא")
    assert cities.resolve_locality("יוקרה אסטייט") is None  # an agency name in the city field, not a place


def test_new_listings_are_stored_under_that_name():
    assert cities.canonicalize_city("תל אביב - יפו") == "תל אביב יפו"
    assert cities.canonicalize_city("בחולון") == "חולון"  # 2026-10-19: "in Holon" is read too (resolve_messy_city)
    assert cities.canonicalize_city("דירת גן") == "דירת גן"  # unknown text is left as it was


def test_areas_hold_their_localities():
    assert "אלון שבות" in cities.REGIONS["גוש עציון"]
    assert set(cities.REGIONS["הקריות"]) == {"קריית אתא", "קריית ביאליק", "קריית מוצקין", "קריית ים"}
    assert all(member in cities.LOCALITY_SET for members in cities.REGIONS.values() for member in members)


def test_a_sentence_names_multi_word_localities_and_areas_but_not_everyday_words():
    assert parse("דירה בגבעת זאב עד 6000")["cities"] == ["גבעת זאב"]
    assert "אלון שבות" in parse("שכירות בגוש עציון")["cities"]
    assert len(parse("מחפש בגליל העליון")["cities"]) > 20
    assert parse("דירה ברחוב שקט בחיפה")["cities"] == ["חיפה"]  # "רחוב" is also a moshav
    assert parse("אני שרון ומחפשת בחיפה")["cities"] == ["חיפה"]  # a first name, not the Sharon


def test_a_reply_to_which_city_takes_any_locality_or_area():
    assert match_city_reply("קדר") == ["קדר"]
    assert match_city_reply("בקדר") == ["קדר"]
    assert "אלון שבות" in match_city_reply("גוש עציון")
    assert suggest_cities("קידר")[0] == "קדר"


def test_typed_search_in_the_filter_finds_small_localities():
    assert cities.find_matches("קדר")[0] == "קדר"
    assert "כפר ורדים" in cities.find_matches("כפר ורד")


def test_a_whole_area_in_the_bot_filter_stays_within_telegrams_100_buttons():
    import keyboards as kb
    from handlers.filter_conversation import _default_draft

    draft = _default_draft()
    draft["cities"] = list(cities.REGIONS["יהודה ושומרון"])
    markup = kb.location_keyboard(draft, "he")
    assert sum(len(row) for row in markup.inline_keyboard) <= 100
    assert "+" in kb.render_root_summary(draft, "he")  # "8 names +170", not 178 names

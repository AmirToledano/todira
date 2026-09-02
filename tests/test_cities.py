"""Unit tests for dorin_common/cities.py's find_matches() - fuzzy city-name suggestion used in the
/filter conversation - and canonicalize_city() - the scraper-side spelling fixup applied to every
listing's raw city text. Pure, dependency-free string matching, but with real documented bug
history (the "ב"ש" alias was found missing only via manual testing against the live bot; Yad2's
own "קרית מוצקין" spelling vs. this list's "קריית מוצקין" was found missing via a live DB query
2026-09-02) - worth locking down so a future edit to the alias/spelling-normalization logic
doesn't silently regress either.
"""
from dorin_common.cities import CITIES, canonicalize_city, find_matches


def test_empty_query_returns_no_matches():
    assert find_matches("") == []
    assert find_matches("   ") == []


def test_substring_match_against_full_city_list():
    results = find_matches("רמת")
    assert "רמת גן" in results
    assert "רמת השרון" in results


def test_no_match_returns_empty_list():
    assert find_matches("עיר שלא קיימת בכלל") == []


def test_alias_bash_resolves_to_beer_sheva_first():
    # the exact real-world bug this function was patched for: "ב"ש" isn't a literal substring of
    # "באר שבע" at all, so a plain containment check alone can never catch it
    results = find_matches('ב"ש')
    assert results[0] == "באר שבע"


def test_alias_matching_is_quote_style_agnostic():
    # ASCII quote, Hebrew geresh, and no quote at all should all resolve to the same alias
    assert find_matches('ב"ש')[0] == "באר שבע"
    assert find_matches("ב׳ש")[0] == "באר שבע"
    assert find_matches("בש")[0] == "באר שבע"


def test_all_documented_aliases_resolve():
    assert find_matches('ת"א')[0] == find_matches("תא")[0] == "תל אביב יפו"
    assert find_matches('פ"ת')[0] == find_matches("פת")[0] == "פתח תקווה"
    assert find_matches('ר"ג')[0] == find_matches("רג")[0] == "רמת גן"


def test_newly_added_aliases_resolve():
    # Expanded 2026-09-02 from the original 4 (בש/תא/פת/רג) after an explicit ask to cover every
    # common Israeli city abbreviation, not just the ones a bug report happened to surface -
    # "ראשל\"צ" for ראשון לציון was the one named explicitly.
    assert find_matches('ראשל"צ')[0] == find_matches("ראשלצ")[0] == "ראשון לציון"
    assert find_matches('כ"ס')[0] == find_matches("כס")[0] == "כפר סבא"
    assert find_matches('ק"א')[0] == find_matches("קא")[0] == "קריית אתא"
    assert find_matches('ק"ג')[0] == find_matches("קג")[0] == "קריית גת"
    assert find_matches('ק"מ')[0] == find_matches("קמ")[0] == "קריית מוצקין"
    assert find_matches('ק"ב')[0] == find_matches("קב")[0] == "קריית ביאליק"
    assert find_matches('רמה"ש')[0] == find_matches("רמהש")[0] == "רמת השרון"
    assert find_matches('ב"ב')[0] == find_matches("בב")[0] == "בני ברק"


def test_alias_result_has_no_duplicate_of_canonical_city():
    # "רג" -> "רמת גן" canonical - "רמת גן" itself must not also appear a second time via the
    # plain substring pass over CITIES
    results = find_matches("רג")
    assert results.count("רמת גן") == 1


def test_limit_caps_number_of_results():
    results = find_matches("ר", limit=2)
    assert len(results) == 2


def test_default_limit_is_six():
    # "ק" (Kiryat-*) matches several cities in the bundled list - confirms the default cap
    results = find_matches("ק")
    assert len(results) <= 6


def test_defective_yud_spelling_matches_full_spelling_city():
    # "קרית" (1 yud, כתיב חסר) is a very common alternate spelling of the bundled list's "קריית
    # מוצקין" (2 yuds, כתיב מלא) - a real user's typo this exact way returned zero matches before
    # find_matches normalized doubled letters (2026-09-02).
    assert "קריית מוצקין" in find_matches("קרית מוצקין")


def test_defective_vav_spelling_matches_full_spelling_city():
    # same doubled-letter normalization, for vav: "תקוה" (1 vav) vs the bundled list's "תקווה"
    # (2 vavs) in "פתח תקווה".
    assert "פתח תקווה" in find_matches("פתח תקוה")


def test_full_canonical_spelling_still_matches_itself():
    # normalization must not break the already-working exact-spelling case
    assert "קריית אתא" in find_matches("קריית אתא")


def test_canonicalize_city_fixes_confirmed_yad2_spelling():
    # confirmed live 2026-09-02 via a real production DB query: every one of 81 real Kiryat
    # Motzkin listings used Yad2's own "קרית מוצקין" (1 yud) - this is the exact case
    # canonicalize_city exists to fix, not a hypothetical.
    assert canonicalize_city("קרית מוצקין") == "קריית מוצקין"


def test_canonicalize_city_leaves_already_canonical_spelling_unchanged():
    assert canonicalize_city("קריית מוצקין") == "קריית מוצקין"


def test_canonicalize_city_leaves_unrecognized_city_unchanged():
    # a real city not in the bundled list must never be mapped to something else
    assert canonicalize_city("כפר יונה") == "כפר יונה"


def test_canonicalize_city_passes_through_none():
    assert canonicalize_city(None) is None


def test_canonicalize_city_passes_through_empty_string():
    assert canonicalize_city("") == ""


def test_canonicalize_city_never_returns_a_name_outside_its_input_or_the_bundled_list():
    # every bundled city, defective-spelling-typo'd, must resolve back to exactly that same
    # bundled city - never to some other entry
    for city in CITIES:
        typo = city.replace("יי", "י").replace("וו", "ו")
        if typo != city:
            assert canonicalize_city(typo) == city

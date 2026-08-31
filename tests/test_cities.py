"""Unit tests for dorin_common/cities.py's find_matches() - fuzzy city-name suggestion used in the
/filter conversation. Pure, dependency-free string matching, but with real documented bug
history (the "ב"ש" alias was found missing only via manual testing against the live bot) - worth
locking down so a future edit to the alias/quote-stripping logic doesn't silently regress it.
"""
from dorin_common.cities import find_matches


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

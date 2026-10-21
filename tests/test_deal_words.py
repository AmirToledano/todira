"""2026-10-21 (owner: "אני רוצה השכרה" was not understood): the many ways people write the kind of deal."""
from __future__ import annotations

import pytest

from todira_common import search_text

CASES = {
    "rent": ["אני רוצה השכרה", "מחפש שכירות בחיפה", "דירה לשכור בתל אביב", "בשכירות", "להשכרה", "השכרת דירה",
             "שכר דירה עד 5000", "שכ\"ד 4000", "שוכרת דירה", "rent in Haifa", "снять квартиру", "аренда",
             "louer à Haïfa", "إيجار في حيفا"],
    "sale": ["לקנות דירה", "קניה בירושלים", "קנייה", "לקנייה", "רכישת דירה", "דירה להשקעה", "יש לי משכנתא",
             "למכירה", "buy in Tel Aviv", "купить квартиру", "acheter un appartement", "شراء شقة"],
    "sublet": ["סאבלט לחודש", "סבלט", "סב לט", "sublet", "субаренда", "שכירות לטווח קצר", "sous-location"],
}


@pytest.mark.parametrize("deal, text", [(deal, text) for deal, texts in CASES.items() for text in texts])
def test_the_kind_of_deal_is_understood(deal, text):
    assert search_text._deal_type(text) == deal


@pytest.mark.parametrize("text", ["3 חדרים בחיפה עד 6000", "קרוב לקניות ולמרכז", "דירה מושקעת עם מרפסת", "location: Haifa"])
def test_words_that_are_not_about_the_deal_say_nothing(text):
    assert search_text._deal_type(text) is None


def test_both_kinds_at_once_are_left_for_the_question():
    assert search_text._deal_type("שכירות או קנייה") is None

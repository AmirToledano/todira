"""2026-10-31: a parking space in Jerusalem came to the owner as a one-room flat, "70% below the area price"."""
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import Integer, Text, create_engine, literal, select

from test_matching import make_filter, make_listing
from todira_common.matching import evaluate
from todira_common.non_home import non_home_kind, not_non_home_sql

THE_AD = (
    "חניה לשכרות בבניין יוקראתי ומפואר ברחוב אלבק חנוך 4 במקום שקרוב למירכז העיר, מתחם התחנה, מתחם כספי, "
    "איזור תלפיות, חניה מקורא אם שער אלקטרוני מאוד בטיחותי שמורה, בשתף 14 מטר במחיר אטרקטיבי"
)


@pytest.mark.parametrize(
    ("description", "deal_type", "price", "size", "expected"),
    [
        (THE_AD, "rent", 650, 14, "parking"),
        ("להשכרה חניה מקורה ליד הקניון", "rent", 400, None, "parking"),
        ("📢 מקום חנייה בטאבו", "sale", 180_000, None, "parking"),
        ("מחסן 6 מ\"ר בקומת קרקע", "rent", 300, 6, "storage"),
        ("להשכרה מחסן גדול", "rent", None, None, "storage"),
        # a flat that mentions its parking first
        ("חניה צמודה ומחסן, דירת 4 חדרים משופצת", "rent", 6500, 95, None),
        ("חנייה בטאבו, 5 חדרים עם נוף", "sale", 2_400_000, 120, None),
        # parking mentioned, but not first
        ("דירת סטודיו קטנה כולל חניה", "rent", 1800, 22, None),
        ("", "rent", 500, 14, None),
        (None, "rent", 500, 14, None),
    ],
)
def test_non_home_kind(description, deal_type, price, size, expected):
    assert non_home_kind(description, deal_type, price, size) == expected


def test_a_parking_space_matches_no_search():
    parking = make_listing(description=THE_AD, price=650, size_sqm=14, rooms=1)
    result = evaluate(make_filter(), parking)
    assert not result.matched
    assert "not_a_home" in result.failed_hard_filters
    assert evaluate(make_filter(), make_listing(description="חניה צמודה, 4 חדרים", price=6500)).matched


@pytest.mark.skipif(not os.environ.get("TODIRA_TEST_DATABASE_URL"), reason="needs a real Postgres")
def test_the_sql_condition_agrees_with_python():
    cases = [
        (THE_AD, "rent", 650, 14),
        ("להשכרה מחסן גדול", "rent", None, None),
        ("📢 מקום חנייה בטאבו", "sale", 180_000, None),
        ("חניה צמודה ומחסן, דירת 4 חדרים משופצת", "rent", 6500, 95),
        ("דירת סטודיו קטנה כולל חניה", "rent", 1800, 22),
        (None, "rent", 500, 14),
    ]
    engine = create_engine(os.environ["TODIRA_TEST_DATABASE_URL"])
    with engine.connect() as conn:
        for description, deal_type, price, size in cases:
            fake = SimpleNamespace(
                description=literal(description, Text), deal_type=literal(deal_type, Text),
                price=literal(price, Integer), size_sqm=literal(size, Integer),
            )
            keeps = conn.execute(select(not_non_home_sql(fake))).scalar_one()
            assert keeps == (non_home_kind(description, deal_type, price, size) is None), description

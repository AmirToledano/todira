"""2026-11-01: prices that fit the other deal type (todira_common/price_sanity.py). The cases are real ads from the live
database (7 days to 2026-11-01)."""
from __future__ import annotations

import pytest

from todira_common.price_sanity import corrected


@pytest.mark.parametrize(
    ("source", "deal_type", "price", "expected"),
    [
        ("yad2", "rent", 16_500_000, ("sale", 16_500_000)),  # 7 rooms, Mazkeret Batya
        ("komo", "rent", 1_300_000, ("sale", 1_300_000)),
        ("facebook_groups", "rent", 450_000, ("sale", 450_000)),
        ("facebook_groups", "rent", 90_000, ("rent", None)),  # 4 rooms in Tel Aviv: a typo or a short sale price
        ("yad2", "rent", 68_000, ("rent", 68_000)),  # 8 rooms, 1,100 m² in Kfar Shmaryahu: real
        ("facebook_groups", "rent", 50, ("rent", None)),
        ("komo", "rent", 120, ("rent", None)),
        ("yad2", "rent", 650, ("rent", 650)),  # parking or storage; the non-home test handles those
        ("facebook_groups", "sale", 4_300, ("rent", 4_300)),  # 2.5 rooms in Bat Yam, in a sale group
        ("facebook_groups", "sale", 12_000, ("rent", 12_000)),
        ("facebook_groups", "sale", 500, ("sale", None)),
        ("yad2", "sale", 11_111, ("sale", None)),  # a placeholder price
        ("yad2", "sale", 1_850_000, ("sale", 1_850_000)),
        ("komo", "sale", 150_000, ("sale", 150_000)),  # a share or a plot: left alone
        ("yad2", "rent", None, ("rent", None)),
        ("yad2", "sublet", 100, ("sublet", 100)),
        ("owner", "rent", 6_000, ("rent", 6_000)),
    ],
)
def test_prices_that_fit_the_other_deal_type(source, deal_type, price, expected):
    assert corrected(source, deal_type, price) == expected

"""Prices that fit the other deal type, or no monthly rent at all (2026-11-01, owner: "find everything that is wrong").

Measured on the 23,876 ads first seen in the 7 days before: rentals priced ₪290,000 to ₪16,500,000 (sales posted in a
rental group, or a rental category), sales priced ₪2,500 to ₪12,000 (rentals posted in a sale group), sales "for"
₪10,000 / ₪11,111 (a placeholder price on a structured site), and rentals for ₪50 to ₪250. A sale stored as a rental is
missed by every sale search; a "₪50 rental" passes every rental search's price limit and goes out as an alert.

- A rental of RENT_IS_SALE_FROM or more is a sale, whatever the source (no flat in Israel rents for that a month).
- From a source whose deal type and price are read from free text (Facebook), a rental above RENT_TEXT_DOUBTFUL_FROM is
  not trusted (a typo or a sale price written short): the price is dropped; and a sale between SALE_TEXT_IS_RENT_FROM and
  SALE_TEXT_IS_RENT_UNDER is a rental.
- Anywhere else, a sale under SALE_PLACEHOLDER_UNDER has a placeholder price, and a rental under RENT_MIN is not a monthly
  rent: the price is dropped (the ad stays, as one without a price).
"""
from __future__ import annotations

from todira_common.enums import DealType, Source

TEXT_SOURCES = frozenset({Source.FACEBOOK_GROUPS, Source.FACEBOOK_MARKETPLACE})
RENT_IS_SALE_FROM = 200_000
RENT_TEXT_DOUBTFUL_FROM = 40_000
RENT_MIN = 300
SALE_TEXT_IS_RENT_FROM = 1_000
SALE_TEXT_IS_RENT_UNDER = 30_000
SALE_PLACEHOLDER_UNDER = 20_000


def corrected(source: str, deal_type: str, price: int | None) -> tuple[str, int | None]:
    """(deal type, price) after the rules above; unchanged when nothing applies."""
    if price is None:
        return deal_type, price
    if deal_type == DealType.RENT:
        if price >= RENT_IS_SALE_FROM:
            return DealType.SALE, price
        if source in TEXT_SOURCES and price > RENT_TEXT_DOUBTFUL_FROM:
            return deal_type, None
        if price < RENT_MIN:
            return deal_type, None
    elif deal_type == DealType.SALE:
        if source in TEXT_SOURCES and SALE_TEXT_IS_RENT_FROM <= price < SALE_TEXT_IS_RENT_UNDER:
            return DealType.RENT, price
        if price < SALE_PLACEHOLDER_UNDER:
            return deal_type, None
    return deal_type, price

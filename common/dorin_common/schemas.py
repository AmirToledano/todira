"""Pydantic validation models. `FilterData` validates user input in the bot's filter-editing
conversation before it's written to the `filters` table; `NormalizedListing` validates a raw
source payload in scraper/normalize.py before it's upserted into `listings`.

The Literal types below must stay in sync with the string constants in enums.py — duplicated
here (rather than built dynamically from enums.ALL tuples) because typing.Literal needs static
values for type-checkers/IDEs to work.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DealType = Literal["sublet", "sale", "rent"]
PropertyType = Literal[
    "apartment",
    "garden_apartment",
    "penthouse",
    "studio",
    "housing_unit",
    "private_house",
    "shared_room",
]
SafeRoomPref = Literal["safe_room_only", "safe_room_or_shelter", "any"]
SafeRoomType = Literal["safe_room", "building_shelter", "none"]
FurniturePref = Literal["furnished", "unfurnished", "any"]
Furniture = Literal["furnished", "unfurnished"]


class FilterData(BaseModel):
    """Validated shape of a user's filter — mirrors the `filters` table columns."""

    deal_type: DealType = "rent"
    property_types: list[PropertyType] = Field(default_factory=list)

    cities: list[str] = Field(default_factory=list)
    neighborhoods_include: list[str] = Field(default_factory=list)
    neighborhoods_exclude: list[str] = Field(default_factory=list)
    streets_include: list[str] = Field(default_factory=list)
    streets_exclude: list[str] = Field(default_factory=list)

    price_min: int | None = None
    price_max: int | None = None
    require_price: bool = False

    rooms_min: float | None = None
    rooms_max: float | None = None

    floor_min: int | None = None
    floor_max: int | None = None
    ground_floor_only: bool = False

    require_parking: bool = False
    require_elevator: bool = False
    require_balcony: bool = False
    require_pets_allowed: bool = False
    require_renovated: bool = False
    require_has_photos: bool = False
    require_roommate_friendly: bool = False

    safe_room_pref: SafeRoomPref = "any"
    furniture_pref: FurniturePref = "any"

    min_area_sqm: int | None = None
    no_brokers: bool = False
    flexible_match: bool = False

    keywords: list[str] = Field(default_factory=list)

    move_in_earliest: dt.date | None = None
    move_in_latest: dt.date | None = None

    @field_validator("price_max")
    @classmethod
    def _price_max_gte_min(cls, v: int | None, info) -> int | None:
        price_min = info.data.get("price_min")
        if v is not None and price_min is not None and v < price_min:
            raise ValueError("price_max must be >= price_min")
        return v

    @field_validator("rooms_max")
    @classmethod
    def _rooms_max_gte_min(cls, v: float | None, info) -> float | None:
        rooms_min = info.data.get("rooms_min")
        if v is not None and rooms_min is not None and v < rooms_min:
            raise ValueError("rooms_max must be >= rooms_min")
        return v

    @field_validator("floor_max")
    @classmethod
    def _floor_max_gte_min(cls, v: int | None, info) -> int | None:
        floor_min = info.data.get("floor_min")
        if v is not None and floor_min is not None and v < floor_min:
            raise ValueError("floor_max must be >= floor_min")
        return v

    @field_validator("move_in_latest")
    @classmethod
    def _move_in_latest_gte_earliest(cls, v: dt.date | None, info) -> dt.date | None:
        earliest = info.data.get("move_in_earliest")
        if v is not None and earliest is not None and v < earliest:
            raise ValueError("move_in_latest must be >= move_in_earliest")
        return v


class NormalizedListing(BaseModel):
    """Shape produced by scraper/normalize.py from a raw source payload, before it's upserted
    into the `listings` table. Deliberately permissive (most fields optional) — a source may not
    expose every attribute cleanly, and normalize.py should degrade to NULL rather than drop the
    whole listing when one field is missing."""

    source: str
    external_id: str
    url: str
    deal_type: DealType
    property_type: PropertyType | None = None

    price: int | None = None
    rooms: float | None = None
    floor: int | None = None
    floor_total: int | None = None
    size_sqm: int | None = None

    city: str | None = None
    neighborhood: str | None = None
    street: str | None = None

    has_parking: bool | None = None
    has_elevator: bool | None = None
    has_balcony: bool | None = None
    pets_allowed: bool | None = None
    is_renovated: bool | None = None
    is_roommate_friendly: bool | None = None

    safe_room_type: SafeRoomType | None = None
    furniture: Furniture | None = None
    is_broker_listing: bool | None = None

    move_in_date: dt.date | None = None
    description: str | None = None
    image_urls: list[str] = Field(default_factory=list)

    posted_at: dt.datetime | None = None
    raw_payload: dict | None = None

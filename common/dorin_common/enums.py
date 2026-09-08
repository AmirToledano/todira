"""Enum-like string constants shared by the scraper, matcher, and bot.

Plain str constants (not `enum.Enum`) on purpose: they're stored directly as Postgres `text`
columns and passed straight through Telegram callback_data strings, so keeping them as plain
strings avoids constant .value unwrapping at every boundary.
"""


class DealType:
    SUBLET = "sublet"
    SALE = "sale"
    RENT = "rent"

    ALL = (SUBLET, SALE, RENT)


class PropertyType:
    APARTMENT = "apartment"
    GARDEN_APARTMENT = "garden_apartment"
    PENTHOUSE = "penthouse"
    STUDIO = "studio"
    HOUSING_UNIT = "housing_unit"
    PRIVATE_HOUSE = "private_house"
    SHARED_ROOM = "shared_room"

    ALL = (
        APARTMENT,
        GARDEN_APARTMENT,
        PENTHOUSE,
        STUDIO,
        HOUSING_UNIT,
        PRIVATE_HOUSE,
        SHARED_ROOM,
    )


class SafeRoomPref:
    SAFE_ROOM_ONLY = "safe_room_only"
    SAFE_ROOM_OR_SHELTER = "safe_room_or_shelter"
    ANY = "any"

    ALL = (SAFE_ROOM_ONLY, SAFE_ROOM_OR_SHELTER, ANY)


class SafeRoomType:
    SAFE_ROOM = "safe_room"
    BUILDING_SHELTER = "building_shelter"
    NONE = "none"

    ALL = (SAFE_ROOM, BUILDING_SHELTER, NONE)


class FurniturePref:
    FURNISHED = "furnished"
    UNFURNISHED = "unfurnished"
    ANY = "any"

    ALL = (FURNISHED, UNFURNISHED, ANY)


class Furniture:
    FURNISHED = "furnished"
    UNFURNISHED = "unfurnished"

    ALL = (FURNISHED, UNFURNISHED)


class Source:
    YAD2 = "yad2"
    KOMO = "komo"
    FACEBOOK_MARKETPLACE = "facebook_marketplace"
    FACEBOOK_GROUPS = "facebook_groups"
    # Added 2026-09-08 — the owner sent real screenshots of the reference bot dorin.app showing
    # its own per-card source badges (Yad2/Facebook/Komo/Homeless), confirming homeless.co.il as a
    # 4th real source to eventually cover, not a guess. See PROJECT_STATE.md for scraping status.
    HOMELESS = "homeless"

    ALL = (YAD2, KOMO, FACEBOOK_MARKETPLACE, FACEBOOK_GROUPS, HOMELESS)


class NotificationReason:
    """Why a given `sent_notifications` row exists — lets the same (user, listing) pair be
    notified more than once for genuinely different reasons (a brand-new match, then later a
    price change on that same listing)."""

    NEW = "new"
    PRICE_DROP = "price_drop"
    PRICE_INCREASE = "price_increase"

    ALL = (NEW, PRICE_DROP, PRICE_INCREASE)


class ListingAction:
    LIKED = "liked"
    HIDDEN = "hidden"
    FOUND_APARTMENT = "found_apartment"

    ALL = (LIKED, HIDDEN, FOUND_APARTMENT)


# The 7 mandatory-feature booleans that both `filters` and `listings` carry, used by the
# matcher (Section 4 of the plan) to build the flexible-match failure count. Each tuple element
# is (filter_column_name, listing_column_name).
MANDATORY_FEATURE_COLUMNS = (
    ("require_parking", "has_parking"),
    ("require_elevator", "has_elevator"),
    ("require_balcony", "has_balcony"),
    ("require_pets_allowed", "pets_allowed"),
    ("require_renovated", "is_renovated"),
    ("require_has_photos", None),  # derived from len(listing.image_urls) > 0, no listing column
    ("require_roommate_friendly", "is_roommate_friendly"),
)

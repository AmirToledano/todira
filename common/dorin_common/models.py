"""SQLAlchemy 2.0 ORM models — the shared schema for `users`, `filters`, `listings`,
`sent_notifications`, and `user_listing_actions`. See plan Section 2 for the field-by-field
rationale (why arrays instead of join tables, why filters is one-to-one with users, etc).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Both nullable — a user has exactly one of the two, never both, never neither
    # (dorin_common/users.py's two get_or_create_*_user helpers each set only their own).
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    whatsapp_phone_number: Mapped[str | None] = mapped_column(Text, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)
    # A Google account LINKED to an existing Telegram/WhatsApp-created user — not a third
    # standalone identity like the two above (a Google-only visitor has no filter/account yet,
    # same restriction the Telegram Login flow already has), just an extra way back into the SAME
    # account for a persistent browser session. Set once via /auth/google/callback's link flow
    # (website/main.py) when a user first signs in with Google while viewing a page via their own
    # ?uid= deep link; every later "Sign in with Google" then resolves straight to this same row.
    google_sub: Mapped[str | None] = mapped_column(Text, unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # soft "paused / found apartment" flag (Dorin's "🎉 מצאתי דירה!") — matcher skips inactive users
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    # In-progress WhatsApp onboarding state across stateless webhook calls — see migration
    # 0003_whatsapp_users. None once no onboarding is in progress (not started, or completed).
    pending_onboarding_state: Mapped[dict | None] = mapped_column(JSONB)

    filter: Mapped["Filter | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Filter(Base):
    """One row per user (one-to-one) — Dorin conceptually has a single active filter per user."""

    __tablename__ = "filters"
    __table_args__ = (
        # matcher queries `WHERE cities && ARRAY[listing.city]` — GIN supports array-overlap
        Index("ix_filters_cities_gin", "cities", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    deal_type: Mapped[str] = mapped_column(Text, default="rent", server_default="rent")
    property_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    cities: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    neighborhoods_include: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    neighborhoods_exclude: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    streets_include: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    streets_exclude: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )

    price_min: Mapped[int | None] = mapped_column(Integer)
    price_max: Mapped[int | None] = mapped_column(Integer)
    require_price: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    rooms_min: Mapped[float | None] = mapped_column(Numeric(3, 1))
    rooms_max: Mapped[float | None] = mapped_column(Numeric(3, 1))

    floor_min: Mapped[int | None] = mapped_column(Integer)
    floor_max: Mapped[int | None] = mapped_column(Integer)
    ground_floor_only: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    require_parking: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    require_elevator: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    require_balcony: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    require_pets_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    require_renovated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    require_has_photos: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    require_roommate_friendly: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    safe_room_pref: Mapped[str] = mapped_column(Text, default="any", server_default="any")
    furniture_pref: Mapped[str] = mapped_column(Text, default="any", server_default="any")

    min_area_sqm: Mapped[int | None] = mapped_column(Integer)
    no_brokers: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    flexible_match: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")

    move_in_earliest: Mapped[dt.date | None] = mapped_column(Date)
    move_in_latest: Mapped[dt.date | None] = mapped_column(Date)

    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="filter")


class Listing(Base):
    """Source-agnostic: `source` + `external_id` is the dedup key, so Phase 3 sources (Komo,
    Facebook) slot in without a schema change."""

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_listings_source_external_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    deal_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    property_type: Mapped[str | None] = mapped_column(Text)

    price: Mapped[int | None] = mapped_column(Integer)
    rooms: Mapped[float | None] = mapped_column(Numeric(3, 1))
    floor: Mapped[int | None] = mapped_column(Integer)
    floor_total: Mapped[int | None] = mapped_column(Integer)
    size_sqm: Mapped[int | None] = mapped_column(Integer)

    city: Mapped[str | None] = mapped_column(Text, index=True)
    neighborhood: Mapped[str | None] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(Text)

    # tri-state: NULL = source didn't say, not "false"
    has_parking: Mapped[bool | None] = mapped_column(Boolean)
    has_elevator: Mapped[bool | None] = mapped_column(Boolean)
    has_balcony: Mapped[bool | None] = mapped_column(Boolean)
    pets_allowed: Mapped[bool | None] = mapped_column(Boolean)
    is_renovated: Mapped[bool | None] = mapped_column(Boolean)
    is_roommate_friendly: Mapped[bool | None] = mapped_column(Boolean)

    safe_room_type: Mapped[str | None] = mapped_column(Text)
    furniture: Mapped[str | None] = mapped_column(Text)
    is_broker_listing: Mapped[bool | None] = mapped_column(Boolean)

    move_in_date: Mapped[dt.date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    image_urls: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")

    posted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # set when a full scrape run no longer sees this listing on the source site — see
    # scraper/main.py's _mark_delisted. /apartments and /liked filter these out.
    is_delisted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    delisted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    # original source JSON/HTML snapshot — cheap insurance for debugging/re-normalizing without
    # re-scraping, while the scraper is still immature
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)


class SentNotification(Base):
    """Prevents re-notifying the same user for the same (listing, reason) pair. `reason` lets
    the same (user, listing) get a second, genuinely different notification later — e.g. a
    'new' match notification, then a 'price_drop' one if that same listing gets cheaper."""

    __tablename__ = "sent_notifications"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "listing_id", "reason", name="uq_sent_notifications_user_listing_reason"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="new", server_default="new")
    sent_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserListingAction(Base):
    """Backs /liked and hide — user-driven, kept separate from the system-driven
    sent_notifications table."""

    __tablename__ = "user_listing_actions"
    __table_args__ = (
        UniqueConstraint("user_id", "listing_id", "action", name="uq_user_listing_actions"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    listing_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ContactMessage(Base):
    """Backs two channels that both funnel into this one table: the website's /contact form
    (website/main.py) and the Telegram bot's free-text fallback (bot/handlers/contact_fallback.py,
    added 2026-09-01). No relationship/FK to User on purpose: most website visitors filling this
    out are anonymous (found the site organically, no ?uid= yet) — telegram_user_id is best-effort
    there, only populated when the form was submitted from a page that already had ?uid= in the
    URL (the bot fallback always has a real Telegram user, so always sets it). Always persisted
    here regardless of whether the best-effort Telegram notification to the owner succeeds, so no
    message is ever silently lost to a transient network/API failure.

    `source` distinguishes the two channels for the admin inbox (website/templates/
    admin_messages.html) — added instead of trying to infer it from which other fields happen to
    be set, since both channels can legitimately have a name and a telegram_user_id, making that
    ambiguous rather than a reliable signal."""

    __tablename__ = "contact_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    notified_owner: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # "website" or "telegram_bot" — nullable only because rows written before this column existed
    # have no value; every new row sets it explicitly (see website/main.py's contact_submit and
    # bot/handlers/contact_fallback.py's _save_contact_message_sync).
    source: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

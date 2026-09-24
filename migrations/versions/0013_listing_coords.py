"""listing coordinates for the /apartments map view — 2026-09-24

Adds nullable latitude/longitude to listings so /apartments can plot real pins on a map
(dorin.app-style layout the owner asked for). Real, confirmed-live coordinate sources wired in
the same change: Komo's adscoordinates endpoint (real lat/lng per id, confirmed nationwide for
BOTH rent and sale — see komo_client.py's own module docstring) and Yad2's map-markers API
(address.coords.lat/lon, confirmed live — see yad2_client.py's _REAL_MARKER test fixture — but
only for REGIONS_ON_MAP_API, rent only; the regular search-page/forsale mechanism does not carry
coordinates). Homeless and Facebook have no coordinate source at all — those listings simply keep
NULL lat/lng and show in the list without a pin, never a guessed/approximated location.

Revision ID: 0013_listing_coords
Revises: 0012_subscription_billing
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_listing_coords"
down_revision = "0012_subscription_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("listings", sa.Column("longitude", sa.Numeric(9, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "longitude")
    op.drop_column("listings", "latitude")

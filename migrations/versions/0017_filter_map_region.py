"""filters.map_region_* — 2026-09-28

Real owner request (backlog #79): let a visitor draw a rectangle or circle directly on /apartments'
own map to narrow the listing set to that area, on top of the existing city filter. See
models.Filter's own comment on these columns and matching.py's evaluate() for how they're read.

Revision ID: 0017_filter_map_region
Revises: 0016_user_language
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_filter_map_region"
down_revision = "0016_user_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filters", sa.Column("map_region_kind", sa.Text(), nullable=True))
    op.add_column("filters", sa.Column("map_center_lat", sa.Numeric(9, 6), nullable=True))
    op.add_column("filters", sa.Column("map_center_lng", sa.Numeric(9, 6), nullable=True))
    op.add_column("filters", sa.Column("map_radius_m", sa.Integer(), nullable=True))
    op.add_column("filters", sa.Column("map_sw_lat", sa.Numeric(9, 6), nullable=True))
    op.add_column("filters", sa.Column("map_sw_lng", sa.Numeric(9, 6), nullable=True))
    op.add_column("filters", sa.Column("map_ne_lat", sa.Numeric(9, 6), nullable=True))
    op.add_column("filters", sa.Column("map_ne_lng", sa.Numeric(9, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("filters", "map_ne_lng")
    op.drop_column("filters", "map_ne_lat")
    op.drop_column("filters", "map_sw_lng")
    op.drop_column("filters", "map_sw_lat")
    op.drop_column("filters", "map_radius_m")
    op.drop_column("filters", "map_center_lng")
    op.drop_column("filters", "map_center_lat")
    op.drop_column("filters", "map_region_kind")

"""search and ratings

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02 21:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.add_column('listings', sa.Column('rating', sa.Numeric(precision=3, scale=2), nullable=True))
    op.add_column('listings', sa.Column('review_count', sa.Integer(), server_default=sa.text('0'), nullable=False))
    # Generated from the coordinates, so the two can never disagree.
    op.execute(
        "ALTER TABLE listings ADD COLUMN location geography(Point,4326) "
        "GENERATED ALWAYS AS ((ST_SetSRID(ST_MakePoint(longitude::double precision, "
        "latitude::double precision), 4326))::geography) STORED"
    )
    op.create_index('ix_listings_location', 'listings', ['location'], unique=False, postgresql_using='gist')
    op.create_index('ix_listings_amenities', 'listings', ['amenities'], unique=False, postgresql_using='gin')

    op.drop_index(op.f('ix_bookings_guest_id'), table_name='bookings')
    op.create_index('ix_bookings_guest_id_created_at', 'bookings', ['guest_id', 'created_at', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_bookings_guest_id_created_at', table_name='bookings')
    op.create_index(op.f('ix_bookings_guest_id'), 'bookings', ['guest_id'], unique=False)

    op.drop_index('ix_listings_amenities', table_name='listings', postgresql_using='gin')
    op.drop_index('ix_listings_location', table_name='listings', postgresql_using='gist')
    op.drop_column('listings', 'location')
    op.drop_column('listings', 'review_count')
    op.drop_column('listings', 'rating')

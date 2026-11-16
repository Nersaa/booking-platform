"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-30 19:05:00.543788
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Needed for exclusion constraints that mix "=" on uuid with "&&" on ranges.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table('listings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('host_id', sa.Uuid(), nullable=False),
    sa.Column('is_listed', sa.Boolean(), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('property_type', sa.String(length=20), nullable=False),
    sa.Column('country', sa.String(length=2), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('latitude', sa.Numeric(precision=9, scale=6), nullable=False),
    sa.Column('longitude', sa.Numeric(precision=9, scale=6), nullable=False),
    sa.Column('max_guests', sa.SmallInteger(), nullable=False),
    sa.Column('bedrooms', sa.SmallInteger(), nullable=False),
    sa.Column('beds', sa.SmallInteger(), nullable=False),
    sa.Column('bathrooms', sa.SmallInteger(), nullable=False),
    sa.Column('amenities', postgresql.ARRAY(sa.String(length=50)), nullable=False),
    sa.Column('cover_photo_url', sa.String(length=500), nullable=True),
    sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_listings'))
    )
    op.create_index(op.f('ix_listings_host_id'), 'listings', ['host_id'], unique=False)
    op.create_table('availability_blocks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('listing_id', sa.Uuid(), nullable=False),
    sa.Column('period', postgresql.DATERANGE(), nullable=False),
    sa.Column('note', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    postgresql.ExcludeConstraint((sa.column('listing_id'), '='), (sa.column('period'), '&&'), using='gist', name='availability_blocks_no_overlap'),
    sa.CheckConstraint('NOT isempty(period)', name=op.f('ck_availability_blocks_period_not_empty')),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], name=op.f('fk_availability_blocks_listing_id_listings'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_availability_blocks'))
    )
    op.create_table('listing_pricing',
    sa.Column('listing_id', sa.Uuid(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('nightly_price', sa.Integer(), nullable=False),
    sa.Column('weekend_price', sa.Integer(), nullable=True, comment='Friday and Saturday nights'),
    sa.Column('cleaning_fee', sa.Integer(), nullable=False),
    sa.Column('min_nights', sa.SmallInteger(), nullable=False),
    sa.Column('max_nights', sa.SmallInteger(), nullable=False),
    sa.Column('weekly_discount_percent', sa.SmallInteger(), nullable=False),
    sa.Column('monthly_discount_percent', sa.SmallInteger(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('cleaning_fee >= 0', name=op.f('ck_listing_pricing_cleaning_fee_non_negative')),
    sa.CheckConstraint('min_nights >= 1 AND max_nights >= min_nights', name=op.f('ck_listing_pricing_nights_range')),
    sa.CheckConstraint('monthly_discount_percent BETWEEN 0 AND 90', name=op.f('ck_listing_pricing_monthly_discount')),
    sa.CheckConstraint('nightly_price > 0', name=op.f('ck_listing_pricing_nightly_price_positive')),
    sa.CheckConstraint('weekend_price IS NULL OR weekend_price > 0', name=op.f('ck_listing_pricing_weekend_price_positive')),
    sa.CheckConstraint('weekly_discount_percent BETWEEN 0 AND 90', name=op.f('ck_listing_pricing_weekly_discount')),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], name=op.f('fk_listing_pricing_listing_id_listings'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('listing_id', name=op.f('pk_listing_pricing'))
    )
    op.create_table('seasonal_rates',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('listing_id', sa.Uuid(), nullable=False),
    sa.Column('period', postgresql.DATERANGE(), nullable=False),
    sa.Column('nightly_price', sa.Integer(), nullable=False),
    postgresql.ExcludeConstraint((sa.column('listing_id'), '='), (sa.column('period'), '&&'), using='gist', name='seasonal_rates_no_overlap'),
    sa.CheckConstraint('NOT isempty(period)', name=op.f('ck_seasonal_rates_period_not_empty')),
    sa.CheckConstraint('nightly_price > 0', name=op.f('ck_seasonal_rates_nightly_price_positive')),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], name=op.f('fk_seasonal_rates_listing_id_listings'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_seasonal_rates'))
    )


def downgrade() -> None:
    op.drop_table('seasonal_rates')
    op.drop_table('listing_pricing')
    op.drop_table('availability_blocks')
    op.drop_index(op.f('ix_listings_host_id'), table_name='listings')
    op.drop_table('listings')

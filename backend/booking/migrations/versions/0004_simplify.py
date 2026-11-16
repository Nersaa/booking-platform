"""drop idempotency keys and the refund queue

Booking writes are protected by database constraints instead of idempotency keys, and
refunds are sent to the provider during the cancellation.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table('refunds')
    op.drop_table('idempotency_keys')


def downgrade() -> None:
    op.create_table('idempotency_keys',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('status_code', sa.SmallInteger(), nullable=True),
    sa.Column('response_body', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('user_id', 'key', name=op.f('pk_idempotency_keys'))
    )
    op.create_index(op.f('ix_idempotency_keys_created_at'), 'idempotency_keys', ['created_at'], unique=False)
    op.create_table('refunds',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('booking_id', sa.Uuid(), nullable=False),
    sa.Column('payment_id', sa.Uuid(), nullable=False),
    sa.Column('provider_refund_id', sa.String(length=100), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('attempts', sa.SmallInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'submitted', 'succeeded', 'failed')", name=op.f('ck_refunds_status_valid')),
    sa.CheckConstraint('amount > 0', name=op.f('ck_refunds_amount_positive')),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], name=op.f('fk_refunds_booking_id_bookings')),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], name=op.f('fk_refunds_payment_id_payments')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refunds')),
    sa.UniqueConstraint('provider_refund_id', name=op.f('uq_refunds_provider_refund_id'))
    )
    op.create_index(op.f('ix_refunds_booking_id'), 'refunds', ['booking_id'], unique=False)
    op.create_index('ix_refunds_pending', 'refunds', ['created_at'], unique=False, postgresql_where=sa.text("status = 'pending'"))

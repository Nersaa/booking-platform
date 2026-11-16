"""bookings and payments

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02 17:22:31.903332
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
    op.create_table('outbox',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('routing_key', sa.String(length=100), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox'))
    )
    op.create_index(op.f('ix_outbox_published_at'), 'outbox', ['published_at'], unique=False)
    op.create_table('processed_webhooks',
    sa.Column('event_id', sa.String(length=100), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('event_id', name=op.f('pk_processed_webhooks'))
    )
    op.create_table('bookings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('listing_id', sa.Uuid(), nullable=False),
    sa.Column('guest_id', sa.Uuid(), nullable=False),
    sa.Column('host_id', sa.Uuid(), nullable=False),
    sa.Column('period', postgresql.DATERANGE(), nullable=False),
    sa.Column('guests', sa.SmallInteger(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('subtotal', sa.Integer(), nullable=False),
    sa.Column('discount', sa.Integer(), nullable=False),
    sa.Column('cleaning_fee', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('refund_amount', sa.Integer(), nullable=False),
    sa.Column('hold_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_by', sa.String(length=10), nullable=True),
    sa.Column('cancellation_reason', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    postgresql.ExcludeConstraint((sa.column('listing_id'), '='), (sa.column('period'), '&&'), where=sa.text("status IN ('pending_payment', 'confirmed')"), using='gist', name='bookings_no_overlap'),
    sa.CheckConstraint("status IN ('pending_payment', 'confirmed', 'cancelled', 'expired', 'completed')", name=op.f('ck_bookings_status_valid')),
    sa.CheckConstraint('NOT isempty(period)', name=op.f('ck_bookings_period_not_empty')),
    sa.CheckConstraint('guests >= 1', name=op.f('ck_bookings_guests_positive')),
    sa.CheckConstraint('refund_amount BETWEEN 0 AND total', name=op.f('ck_bookings_refund_amount')),
    sa.CheckConstraint('total >= 0 AND total = subtotal - discount + cleaning_fee', name=op.f('ck_bookings_total')),
    sa.ForeignKeyConstraint(['listing_id'], ['listings.id'], name=op.f('fk_bookings_listing_id_listings')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bookings'))
    )
    op.create_index(op.f('ix_bookings_guest_id'), 'bookings', ['guest_id'], unique=False)
    op.create_index(op.f('ix_bookings_host_id'), 'bookings', ['host_id'], unique=False)
    op.create_index('ix_bookings_pending_holds', 'bookings', ['hold_expires_at'], unique=False, postgresql_where=sa.text("status = 'pending_payment'"))
    op.create_table('payments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('booking_id', sa.Uuid(), nullable=False),
    sa.Column('provider_payment_id', sa.String(length=100), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('checkout_url', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'succeeded', 'failed')", name=op.f('ck_payments_status_valid')),
    sa.CheckConstraint('amount > 0', name=op.f('ck_payments_amount_positive')),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], name=op.f('fk_payments_booking_id_bookings')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
    sa.UniqueConstraint('provider_payment_id', name=op.f('uq_payments_provider_payment_id'))
    )
    op.create_index(op.f('ix_payments_booking_id'), 'payments', ['booking_id'], unique=False)
    op.create_index('uq_payments_one_success_per_booking', 'payments', ['booking_id'], unique=True, postgresql_where=sa.text("status = 'succeeded'"))
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


def downgrade() -> None:
    op.drop_index('ix_refunds_pending', table_name='refunds', postgresql_where=sa.text("status = 'pending'"))
    op.drop_index(op.f('ix_refunds_booking_id'), table_name='refunds')
    op.drop_table('refunds')
    op.drop_index('uq_payments_one_success_per_booking', table_name='payments', postgresql_where=sa.text("status = 'succeeded'"))
    op.drop_index(op.f('ix_payments_booking_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index('ix_bookings_pending_holds', table_name='bookings', postgresql_where=sa.text("status = 'pending_payment'"))
    op.drop_index(op.f('ix_bookings_host_id'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_guest_id'), table_name='bookings')
    op.drop_table('bookings')
    op.drop_table('processed_webhooks')
    op.drop_index(op.f('ix_outbox_published_at'), table_name='outbox')
    op.drop_table('outbox')
    op.drop_index(op.f('ix_idempotency_keys_created_at'), table_name='idempotency_keys')
    op.drop_table('idempotency_keys')

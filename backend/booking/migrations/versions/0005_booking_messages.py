"""messages between guest and host

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('booking_messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('booking_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('text', sa.String(length=2000), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], name=op.f('fk_booking_messages_booking_id_bookings'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_booking_messages'))
    )
    op.create_index(op.f('ix_booking_messages_booking_id'), 'booking_messages', ['booking_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_booking_messages_booking_id'), table_name='booking_messages')
    op.drop_table('booking_messages')

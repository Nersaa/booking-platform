"""booking requests: hosts may accept every booking first

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "'pending_payment', 'confirmed', 'cancelled', 'expired', 'completed'"
NEW_STATUSES = OLD_STATUSES + ", 'awaiting_host', 'declined'"


def _rebuild(statuses: str, holding: str, active: str) -> None:
    op.drop_constraint('status_valid', 'bookings', type_='check')
    op.create_check_constraint('status_valid', 'bookings', f"status IN ({statuses})")

    op.drop_index('ix_bookings_pending_holds', table_name='bookings')
    op.create_index(
        'ix_bookings_pending_holds', 'bookings', ['hold_expires_at'],
        postgresql_where=sa.text(f"status IN ({holding})"),
    )

    # A request holds its dates too, so the guarantee against double bookings covers it.
    op.drop_constraint('bookings_no_overlap', 'bookings')
    op.create_exclude_constraint(
        'bookings_no_overlap', 'bookings',
        ('listing_id', '='), ('period', '&&'),
        using='gist', where=sa.text(f"status IN ({active})"),
    )


def upgrade() -> None:
    op.add_column(
        'listing_pricing',
        sa.Column('instant_book', sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    _rebuild(
        NEW_STATUSES,
        holding="'awaiting_host', 'pending_payment'",
        active="'awaiting_host', 'pending_payment', 'confirmed'",
    )


def downgrade() -> None:
    op.execute("UPDATE bookings SET status = 'expired', hold_expires_at = NULL "
               "WHERE status = 'awaiting_host'")
    op.execute("UPDATE bookings SET status = 'cancelled' WHERE status = 'declined'")
    _rebuild(
        OLD_STATUSES,
        holding="'pending_payment'",
        active="'pending_payment', 'confirmed'",
    )
    op.drop_column('listing_pricing', 'instant_book')


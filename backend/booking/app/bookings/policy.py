"""Cancellation policy. Pure function, all amounts in minor units."""

from datetime import date

from contracts import CancelledBy

FULL_REFUND_DAYS = 7
HALF_REFUND_DAYS = 1


def refund_amount(*, total: int, check_in: date, today: date, cancelled_by: CancelledBy) -> int:
    """Host cancellations are always refunded in full. Guests get everything back a week
    or more before check-in, half up to the day before, nothing on the day itself."""
    if cancelled_by is CancelledBy.HOST:
        return total
    days_left = (check_in - today).days
    if days_left >= FULL_REFUND_DAYS:
        return total
    if days_left >= HALF_REFUND_DAYS:
        return total // 2
    return 0

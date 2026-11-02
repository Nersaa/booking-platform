from datetime import date, timedelta

import pytest
from contracts import CancelledBy

from app.bookings.policy import refund_amount
from app.payments import webhooks

CHECK_IN = date(2030, 8, 10)


@pytest.mark.parametrize(
    ("days_before", "expected"),
    [(30, 10_001), (7, 10_001), (6, 5_000), (1, 5_000), (0, 0)],
)
def test_guest_refund_depends_on_notice(days_before: int, expected: int) -> None:
    today = CHECK_IN - timedelta(days=days_before)

    assert (
        refund_amount(total=10_001, check_in=CHECK_IN, today=today, cancelled_by=CancelledBy.GUEST)
        == expected
    )


def test_host_cancellation_is_always_refunded_in_full() -> None:
    assert (
        refund_amount(
            total=10_001, check_in=CHECK_IN, today=CHECK_IN, cancelled_by=CancelledBy.HOST
        )
        == 10_001
    )


def test_webhook_signature_roundtrip() -> None:
    header = webhooks.sign("secret", b"{}", 1_000)

    webhooks.verify("secret", b"{}", header, now=1_100)
    with pytest.raises(webhooks.InvalidSignatureError, match="does not match"):
        webhooks.verify("secret", b'{"tampered":1}', header, now=1_100)
    with pytest.raises(webhooks.InvalidSignatureError, match="tolerance"):
        webhooks.verify("secret", b"{}", header, now=1_000 + 301)
    with pytest.raises(webhooks.InvalidSignatureError, match="Malformed"):
        webhooks.verify("secret", b"{}", "garbage", now=1_000)

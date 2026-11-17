from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from contracts import ListingEvent, ListingEventType, ListingSnapshot

from app.payments.provider import PaymentProviderError, ProviderPayment

PRICING: dict[str, Any] = {
    "currency": "EUR",
    "nightly_price": 10_000,
    "weekend_price": 14_000,
    "cleaning_fee": 2_500,
    "min_nights": 2,
    "max_nights": 30,
    "weekly_discount_percent": 10,
    "monthly_discount_percent": 20,
}


class FakePaymentProvider:
    """Records calls; behaves like the real provider including idempotency keys."""

    def __init__(self) -> None:
        self.payments: dict[str, dict[str, Any]] = {}
        self.refunds: dict[str, dict[str, Any]] = {}
        self.down = False

    async def create_payment(
        self,
        *,
        amount: int,
        currency: str,
        reference: str,
        idempotency_key: str,
        description: str = "",
        return_url: str | None = None,
    ) -> ProviderPayment:
        if self.down:
            raise PaymentProviderError("provider is down")
        payment = self.payments.setdefault(
            idempotency_key,
            {
                "id": f"pay_{len(self.payments)}",
                "amount": amount,
                "reference": reference,
                "description": description,
                "return_url": return_url,
            },
        )
        return ProviderPayment(id=payment["id"], checkout_url=f"http://pay/{payment['id']}")

    async def create_refund(
        self, *, payment_id: str, amount: int, reference: str, idempotency_key: str
    ) -> str:
        if self.down:
            raise PaymentProviderError("provider is down")
        refund = self.refunds.setdefault(
            idempotency_key,
            {"id": f"re_{len(self.refunds)}", "payment_id": payment_id, "amount": amount},
        )
        return str(refund["id"])


def snapshot(**fields: Any) -> ListingSnapshot:
    data: dict[str, Any] = {
        "id": uuid4(),
        "version": 2,
        "host_id": uuid4(),
        "is_listed": True,
        "title": "Sunny apartment",
        "property_type": "apartment",
        "country": "PT",
        "city": "Lisbon",
        "latitude": Decimal("38.710000"),
        "longitude": Decimal("-9.137000"),
        "max_guests": 4,
        "bedrooms": 2,
        "beds": 2,
        "bathrooms": 1,
        "amenities": ("wifi", "kitchen"),
        "cover_photo_url": "http://testserver/media/public/listings/1/1/thumb.webp",
    }
    data.update(fields)
    return ListingSnapshot(**data)


def listing_event(
    listing: ListingSnapshot, event_type: ListingEventType = ListingEventType.PUBLISHED
) -> ListingEvent:
    return ListingEvent(
        event_id=uuid4(), event_type=event_type, occurred_at=datetime.now(UTC), listing=listing
    )

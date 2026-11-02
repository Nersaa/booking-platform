import json

import httpx
import pytest

from app.payments.provider import HttpPaymentProvider, PaymentProviderError


def provider_with(handler: httpx.MockTransport) -> HttpPaymentProvider:
    client = httpx.AsyncClient(
        transport=handler, base_url="http://provider", headers={"Authorization": "Bearer k"}
    )
    return HttpPaymentProvider(client)


async def test_calls_carry_auth_and_idempotency_key() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/v1/payments":
            return httpx.Response(201, json={"id": "pay_1", "checkout_url": "http://c/pay_1"})
        return httpx.Response(201, json={"id": "re_1"})

    provider = provider_with(httpx.MockTransport(handle))

    payment = await provider.create_payment(
        amount=500, currency="EUR", reference="p-1", idempotency_key="p-1"
    )
    refund = await provider.create_refund(
        payment_id="pay_1", amount=200, reference="r-1", idempotency_key="r-1"
    )

    assert (payment.id, payment.checkout_url, refund) == ("pay_1", "http://c/pay_1", "re_1")
    assert [r.url.path for r in seen] == ["/v1/payments", "/v1/payments/pay_1/refunds"]
    assert [r.headers["Idempotency-Key"] for r in seen] == ["p-1", "r-1"]
    assert seen[0].headers["Authorization"] == "Bearer k"
    assert json.loads(seen[1].content) == {"amount": 200, "reference": "r-1"}


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(200, content=b"not json")],
    ids=["server error", "bad body"],
)
async def test_failures_become_provider_errors(response: httpx.Response) -> None:
    provider = provider_with(httpx.MockTransport(lambda _: response))

    with pytest.raises(PaymentProviderError):
        await provider.create_payment(amount=1, currency="EUR", reference="r", idempotency_key="k")

"""Client of the payment provider's API (a mock locally, see backend/payment-mock).

Every call carries an idempotency key derived from our own record id, so retrying a call
after a timeout can never charge or refund twice.
"""

from dataclasses import dataclass
from typing import Annotated, Any, Protocol

import httpx
from fastapi import Depends, Request


class PaymentProviderError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ProviderPayment:
    id: str
    checkout_url: str


class PaymentProvider(Protocol):
    async def create_payment(
        self, *, amount: int, currency: str, reference: str, idempotency_key: str
    ) -> ProviderPayment: ...

    async def create_refund(
        self, *, payment_id: str, amount: int, reference: str, idempotency_key: str
    ) -> str: ...


class HttpPaymentProvider:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @classmethod
    def build(cls, base_url: str, api_key: str) -> "HttpPaymentProvider":
        return cls(
            httpx.AsyncClient(
                base_url=base_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_payment(
        self, *, amount: int, currency: str, reference: str, idempotency_key: str
    ) -> ProviderPayment:
        data = await self._post(
            "/v1/payments",
            {"amount": amount, "currency": currency, "reference": reference},
            idempotency_key,
        )
        return ProviderPayment(id=data["id"], checkout_url=data["checkout_url"])

    async def create_refund(
        self, *, payment_id: str, amount: int, reference: str, idempotency_key: str
    ) -> str:
        data = await self._post(
            f"/v1/payments/{payment_id}/refunds",
            {"amount": amount, "reference": reference},
            idempotency_key,
        )
        return str(data["id"])

    async def _post(self, path: str, body: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        try:
            response = await self._client.post(
                path, json=body, headers={"Idempotency-Key": idempotency_key}
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PaymentProviderError(f"Payment provider call {path} failed: {exc}") from exc
        return data


def get_provider(request: Request) -> PaymentProvider:
    provider: PaymentProvider = request.app.state.payments
    return provider


ProviderDep = Annotated[PaymentProvider, Depends(get_provider)]

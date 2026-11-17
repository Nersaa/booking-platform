"""A stand-in for a card payment provider (think Stripe), for local development and demos.

It implements only what Booking uses:
- POST /v1/payments                create a payment, get a hosted checkout URL
- GET  /checkout/{id}              the hosted page where the guest pays with a test card
- POST /v1/payments/{id}/refunds   refund (part of) a succeeded payment
and reports outcomes with HMAC-signed webhooks, retried with backoff like real providers.
After a successful payment the guest is sent back to the shop's `return_url`.
State lives in memory and is lost on restart.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections.abc import Callable, Coroutine
from dataclasses import asdict, dataclass
from functools import cache
from typing import Annotated, Any, Literal

import httpx
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings

from payment_mock import checkout

logger = logging.getLogger("payment_mock")

WEBHOOK_ATTEMPTS = 6


class Settings(BaseSettings):
    api_key: str
    webhook_secret: str
    webhook_url: str
    public_url: str = "http://localhost:8090"


@cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment


@dataclass
class Payment:
    id: str
    amount: int
    currency: str
    reference: str
    description: str = ""
    return_url: str | None = None
    status: Literal["requires_action", "succeeded", "failed"] = "requires_action"
    refunded: int = 0


@dataclass
class Refund:
    id: str
    payment_id: str
    amount: int
    reference: str
    status: Literal["succeeded"] = "succeeded"


class PaymentIn(BaseModel):
    amount: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    reference: str = Field(max_length=100)
    description: str = Field("", max_length=200, description="Shown on the checkout page.")
    return_url: HttpUrl | None = Field(None, description="Where the guest goes after paying.")


class RefundIn(BaseModel):
    amount: int = Field(gt=0)
    reference: str = Field(max_length=100)


def sign(secret: str, body: bytes, timestamp: int) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


Sender = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class Provider:
    def __init__(self, settings: Settings, send_webhook: Sender | None = None) -> None:
        self.settings = settings
        self.payments: dict[str, Payment] = {}
        self.refunds: dict[str, Refund] = {}
        self.idempotent: dict[tuple[str, str], dict[str, Any]] = {}
        self._send = send_webhook or self.deliver
        self._tasks: set[asyncio.Task[None]] = set()

    def notify(self, event_type: str, obj: Payment | Refund) -> None:
        event = {"id": f"evt_{secrets.token_hex(12)}", "type": event_type, "data": asdict(obj)}
        task = asyncio.create_task(self._send(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def deliver(self, event: dict[str, Any]) -> None:
        """At-least-once delivery with exponential backoff, like real providers."""
        body = json.dumps(event).encode()
        async with httpx.AsyncClient(timeout=10) as client:
            for attempt in range(WEBHOOK_ATTEMPTS):
                signature = sign(self.settings.webhook_secret, body, int(time.time()))
                try:
                    response = await client.post(
                        self.settings.webhook_url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "Webhook-Signature": signature,
                        },
                    )
                    if response.is_success:
                        logger.info("Webhook %s %s delivered", event["type"], event["id"])
                        return
                    logger.warning("Webhook %s rejected: %s", event["id"], response.status_code)
                except httpx.HTTPError as exc:
                    logger.warning("Webhook %s failed: %s", event["id"], exc)
                await asyncio.sleep(2**attempt)
        logger.error("Webhook %s given up after %d attempts", event["id"], WEBHOOK_ATTEMPTS)


def get_provider(request: Request) -> Provider:
    provider: Provider = request.app.state.provider
    return provider


ProviderDep = Annotated[Provider, Depends(get_provider)]


def authenticate(provider: ProviderDep, authorization: Annotated[str, Header()] = "") -> Provider:
    expected = f"Bearer {provider.settings.api_key}"
    if not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key.")
    return provider


MerchantDep = Annotated[Provider, Depends(authenticate)]
KeyHeader = Annotated[str, Header(alias="Idempotency-Key", min_length=1)]


def create_app(provider: Provider | None = None) -> FastAPI:
    """`uvicorn payment_mock.main:create_app --factory`; tests pass their own provider."""
    app = FastAPI(title="Payment provider (mock)", docs_url="/docs", redoc_url=None)
    app.state.provider = provider or Provider(get_settings())

    @app.post("/v1/payments", status_code=status.HTTP_201_CREATED)
    async def create_payment(
        body: PaymentIn, provider: MerchantDep, key: KeyHeader
    ) -> dict[str, Any]:
        if (stored := provider.idempotent.get(("payment", key))) is not None:
            return stored
        payment = Payment(
            id=f"pay_{secrets.token_hex(12)}",
            amount=body.amount,
            currency=body.currency,
            reference=body.reference,
            description=body.description,
            return_url=str(body.return_url) if body.return_url else None,
        )
        provider.payments[payment.id] = payment
        response = {
            **asdict(payment),
            "checkout_url": f"{provider.settings.public_url}/checkout/{payment.id}",
        }
        provider.idempotent[("payment", key)] = response
        return response

    @app.get("/v1/payments/{payment_id}")
    async def get_payment(payment_id: str, provider: MerchantDep) -> dict[str, Any]:
        return asdict(_payment(provider, payment_id))

    @app.post("/v1/payments/{payment_id}/refunds", status_code=status.HTTP_201_CREATED)
    async def create_refund(
        payment_id: str, body: RefundIn, provider: MerchantDep, key: KeyHeader
    ) -> dict[str, Any]:
        if (stored := provider.idempotent.get(("refund", key))) is not None:
            return stored
        payment = _payment(provider, payment_id)
        if payment.status != "succeeded":
            raise HTTPException(status.HTTP_409_CONFLICT, "Only succeeded payments are refunded.")
        if body.amount > payment.amount - payment.refunded:
            raise HTTPException(status.HTTP_409_CONFLICT, "Refund exceeds the paid amount.")
        refund = Refund(
            id=f"re_{secrets.token_hex(12)}",
            payment_id=payment.id,
            amount=body.amount,
            reference=body.reference,
        )
        payment.refunded += refund.amount
        provider.refunds[refund.id] = refund
        provider.idempotent[("refund", key)] = asdict(refund)
        provider.notify("refund.succeeded", refund)
        return asdict(refund)

    @app.get("/checkout/{payment_id}", response_class=HTMLResponse)
    async def checkout_page(payment_id: str, provider: ProviderDep) -> str:
        return checkout.render(_payment(provider, payment_id))

    @app.post("/checkout/{payment_id}", response_model=None)
    async def pay(
        payment_id: str, provider: ProviderDep, card_number: Annotated[str, Form()] = ""
    ) -> HTMLResponse | RedirectResponse:
        payment = _payment(provider, payment_id)
        if payment.status == "requires_action":
            # The card number only picks the outcome; it is never stored or logged.
            outcome = checkout.TEST_CARDS.get(re.sub(r"\D", "", card_number))
            if outcome is None:
                error = "Use one of the test cards below. This page never charges real cards."
                return HTMLResponse(checkout.render(payment, error), status.HTTP_400_BAD_REQUEST)
            payment.status = "succeeded" if outcome == "succeeded" else "failed"
            provider.notify(f"payment.{payment.status}", payment)
        if payment.status == "succeeded" and payment.return_url:
            return RedirectResponse(payment.return_url, status.HTTP_303_SEE_OTHER)
        return HTMLResponse(checkout.render(payment))

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _payment(provider: Provider, payment_id: str) -> Payment:
    payment = provider.payments.get(payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found.")
    return payment

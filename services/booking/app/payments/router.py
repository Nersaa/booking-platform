from fastapi import APIRouter, Request, status
from pydantic import ValidationError

from app.db import SessionDep
from app.errors import DomainError
from app.payments import webhooks
from app.payments.service import handle_webhook

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def payment_webhook(request: Request, session: SessionDep) -> None:
    """Called by the payment provider. Authenticated by HMAC signature, not by JWT."""
    body = await request.body()
    webhooks.verify(
        request.app.state.settings.payment_webhook_secret,
        body,
        request.headers.get(webhooks.SIGNATURE_HEADER),
    )
    try:
        event = webhooks.WebhookEvent.model_validate_json(body)
    except ValidationError as exc:
        raise DomainError("Malformed webhook payload.") from exc
    await handle_webhook(session, event)

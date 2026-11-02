# 7. Payments through a provider with signed webhooks

Status: accepted

## Context

Card payments are handled by an external provider (Stripe-like). The guest pays on the
provider's hosted page; the provider tells us the outcome asynchronously. Calls to the
provider can time out, and webhooks can arrive late, twice or never in order.

## Decision

- **Provider API.** Booking creates a payment for the booking total and returns the
  provider's checkout URL. Every call carries an idempotency key equal to our own record
  id, so retries never charge or refund twice. Locally the provider is
  `services/payment-mock`, a small FastAPI app with the same contract.
- **Webhooks are authenticated by HMAC**, not by JWT: header
  `Webhook-Signature: t=<unix>,v1=<hex(HMAC-SHA256(secret, "<t>.<raw body>"))>`. The
  signature is compared in constant time and the timestamp must be within 5 minutes,
  which stops replays. The webhook endpoint is not exposed through the public gateway.
- **Webhooks are processed once.** The provider's event id is inserted into
  `processed_webhooks` in the same transaction as the effect; a redelivery is a no-op.
  Webhook objects carry our own payment/refund id (`reference`), so a webhook that
  arrives before we stored the provider's id still finds its record.
- **Late payments are refunded.** If a payment succeeds after the booking expired or the
  guest cancelled, the money is refunded automatically instead of confirming a booking
  whose dates may be gone.
- **Cancellation policy** (pure function): host cancels, full refund; guest cancels 7+
  days before check-in, full refund; 1 to 6 days before, half; on the day, none.
- **Refunds go through the database first.** Cancelling records a `Refund` row in the
  same transaction; a worker job submits pending refunds to the provider and retries on
  failure. A provider outage never blocks a cancellation or loses a refund.
- **Notifications.** Booking publishes `booking.confirmed`, `booking.cancelled` and
  `booking.completed` through its own transactional outbox (ADR 4). Catalog, which owns
  contact details, consumes them and emails guest and host (Mailpit locally). Booking
  never stores emails.

## Consequences

- Booking state follows the provider's webhooks, so local development needs the mock
  running; tests use an in-memory fake with the same interface.
- The mock keeps its state in memory and is for development only.

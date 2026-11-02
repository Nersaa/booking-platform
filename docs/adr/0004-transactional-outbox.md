# 4. Transactional outbox for domain events

Status: accepted

## Context

Booking keeps a read model of listings (ADR 1). Catalog has to tell it about every
change. Publishing to RabbitMQ straight from a request handler has two failure modes:
the database commit succeeds but the publish fails (Booking never learns about the
change), or the publish succeeds and the commit is rolled back (Booking learns about a
change that never happened).

## Decision

- Catalog writes events to an `outbox` table in the same transaction as the change.
  `outbox_add` refuses to run outside a transaction.
- A separate process, `manage.py relay_outbox`, publishes pending rows in order and
  marks them as published. Rows are locked with `FOR UPDATE SKIP LOCKED`, so several
  relays can run at once. It polls every 0.5 s when idle and backs off exponentially
  while the broker is down.
- Messages are persistent and published with publisher confirms and `mandatory`. A
  message that no queue would receive is returned by the broker and stays in the outbox,
  so events published before Booking first starts are not lost.
- Events carry a full snapshot of the listing and its `version` (event-carried state
  transfer). The consumer applies a snapshot with a single
  `INSERT ... ON CONFLICT DO UPDATE ... WHERE version < excluded.version`, so redelivered
  and reordered messages are harmless.
- Message schemas live in `libs/contracts` (Pydantic), shared by producer and consumer.
  Changes must be backward compatible: optional fields only, or a new event type.
- The consumer queue is a quorum queue with a delivery limit; messages that keep failing
  go to a dead-letter queue instead of blocking the stream.
- Published rows are purged after 7 days by a Celery beat task.

## Consequences

- Delivery is at least once, and consumers must be idempotent (they are, by version).
- Listing changes reach Booking within about a second, not instantly.
- The relay is one more process to run. PostgreSQL `LISTEN/NOTIFY` or CDC (Debezium)
  could replace polling if latency or load ever require it.

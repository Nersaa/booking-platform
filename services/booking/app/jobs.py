"""Background jobs run by the worker process.

Every job is safe to run in several worker replicas at once: rows are claimed with
SKIP LOCKED or changed by single conditional UPDATE statements.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app import idempotency, outbox
from app.bookings.service import complete_finished_stays, expire_stale_holds
from app.db import Database
from app.payments.provider import PaymentProvider
from app.payments.service import submit_pending_refunds

logger = logging.getLogger(__name__)

Job = Callable[[], Awaitable[int]]


class BackgroundJobs:
    def __init__(self, db: Database, provider: PaymentProvider, publish: outbox.Publish) -> None:
        self._db = db
        self._provider = provider
        self._publish = publish
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        schedule: dict[str, tuple[Job, float]] = {
            "relay outbox": (self.relay_outbox, 0.5),
            "expire holds": (self.expire_holds, 30),
            "submit refunds": (self.submit_refunds, 15),
            "complete stays": (self.complete_stays, 600),
            "purge old records": (self.purge, 3600),
        }
        self._tasks = [
            asyncio.create_task(self._every(seconds, job, name), name=name)
            for name, (job, seconds) in schedule.items()
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def relay_outbox(self) -> int:
        return await outbox.relay_batch(self._db.sessions, self._publish)

    async def expire_holds(self) -> int:
        async with self._db.sessions.begin() as session:
            return await expire_stale_holds(session)

    async def submit_refunds(self) -> int:
        return await submit_pending_refunds(self._db.sessions, self._provider)

    async def complete_stays(self) -> int:
        async with self._db.sessions.begin() as session:
            return await complete_finished_stays(session)

    async def purge(self) -> int:
        async with self._db.sessions.begin() as session:
            return await outbox.purge_published(session) + await idempotency.purge_expired(session)

    @staticmethod
    async def _every(seconds: float, job: Job, name: str) -> None:
        while True:
            try:
                if done := await job():
                    logger.info("%s: %d", name, done)
            except Exception:
                # One failing run (database restart, broker down) must not kill the loop.
                logger.warning("Job '%s' failed", name, exc_info=True)
            await asyncio.sleep(seconds)

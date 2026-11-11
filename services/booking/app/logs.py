"""JSON logs that carry a request id.

The gateway gives every request an `X-Request-ID`; services log it with every line and
return it, so one request can be followed from the Nginx access log through the service
that handled it. Consumers use the event id instead.

The configuration lives in `logging.json`: uvicorn loads it with `--log-config`, the
worker with `configure_logging()`. Uvicorn's access log is off there: the gateway already
logs every request, with the same id.
"""

import json
import logging.config
import re
import uuid
from contextvars import ContextVar
from pathlib import Path

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LOG_CONFIG_FILE = Path(__file__).resolve().parent.parent / "logging.json"
REQUEST_ID_HEADER = "X-Request-ID"
# Anything else from a client could forge log lines or blow up their size.
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(json.loads(LOG_CONFIG_FILE.read_text(encoding="utf-8")))
    logging.getLogger().setLevel(level)


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.lower().encode(), b"").decode()
        current = incoming if VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = current
            await send(message)

        token = request_id.set(current)
        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id.reset(token)

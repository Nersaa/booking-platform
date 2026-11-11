"""JSON logs that carry a request id; see Booking's `app/logs.py` for the idea."""

import logging
import re
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse

REQUEST_ID_HEADER = "X-Request-ID"
# Anything else from a client could forge log lines or blow up their size.
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

request_id: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        current = incoming if VALID_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id.set(current)
        try:
            response = self.get_response(request)
        finally:
            request_id.reset(token)
        response[REQUEST_ID_HEADER] = current
        return response

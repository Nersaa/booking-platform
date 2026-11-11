import io
import json
import logging
from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from app.logs import REQUEST_ID_HEADER, configure_logging, request_id


@pytest.fixture
def json_log() -> Iterator[io.StringIO]:
    """The production logging config, writing to a buffer instead of stdout."""
    root = logging.getLogger()
    saved = root.handlers[:], root.level
    configure_logging()
    stream = io.StringIO()
    handler = root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(stream)
    yield stream
    root.handlers, root.level = saved[0], saved[1]


async def test_gateway_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={REQUEST_ID_HEADER: "abc-123"})

    assert response.headers[REQUEST_ID_HEADER] == "abc-123"


@pytest.mark.parametrize("sent", [None, "x" * 200, "evil\nINFO forged line"])
async def test_missing_or_unsafe_ids_are_replaced(client: AsyncClient, sent: str | None) -> None:
    headers = {REQUEST_ID_HEADER: sent} if sent else {}

    response = await client.get("/no/such/path", headers=headers)

    assert response.status_code == 404
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_log_lines_are_json_with_the_request_id(json_log: io.StringIO) -> None:
    token = request_id.set("req-42")
    try:
        logging.getLogger("app.test").warning("Hold %s expired", "b-1")
    finally:
        request_id.reset(token)

    line = json.loads(json_log.getvalue().splitlines()[-1])
    assert line["message"] == "Hold b-1 expired"
    assert line["level"] == "WARNING"
    assert line["logger"] == "app.test"
    assert line["request_id"] == "req-42"
    assert "time" in line

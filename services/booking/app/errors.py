"""Domain errors and RFC 9457 (Problem Details) responses, same shape as in Catalog."""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"


class DomainError(Exception):
    """A business rule was violated. Raised by services, translated to HTTP here."""

    status_code: int = HTTPStatus.BAD_REQUEST
    code = "domain_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    status_code = HTTPStatus.NOT_FOUND
    code = "not_found"


class ConflictError(DomainError):
    status_code = HTTPStatus.CONFLICT
    code = "conflict"


class NotAuthenticatedError(DomainError):
    status_code = HTTPStatus.UNAUTHORIZED
    code = "not_authenticated"


class PermissionDeniedError(DomainError):
    status_code = HTTPStatus.FORBIDDEN
    code = "permission_denied"


class ServiceUnavailableError(DomainError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "service_unavailable"


def problem(status: int, detail: str, **extra: Any) -> JSONResponse:
    body = {"type": "about:blank", "title": HTTPStatus(status).phrase, "status": status}
    body["detail"] = detail
    body.update(extra)
    headers = {"WWW-Authenticate": "Bearer"} if status == HTTPStatus.UNAUTHORIZED else None
    return JSONResponse(
        jsonable_encoder(body), status_code=status, media_type=PROBLEM_CONTENT_TYPE, headers=headers
    )


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)  # noqa: S101 - registered for DomainError only
    return problem(exc.status_code, exc.detail, code=exc.code)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return problem(HTTPStatus.UNPROCESSABLE_ENTITY, "Request validation failed.", errors=errors)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)  # noqa: S101
    return problem(exc.status_code, str(exc.detail))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)

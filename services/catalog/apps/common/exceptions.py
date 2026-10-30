"""Domain errors and an RFC 9457 (Problem Details) exception handler for DRF."""

from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

PROBLEM_CONTENT_TYPE = "application/problem+json"


class DomainError(Exception):
    """A business rule was violated. Raised by services, translated to HTTP here."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code = "domain_error"


class InvalidStateTransitionError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    code = "invalid_state_transition"


class PermissionDeniedError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"


def _as_api_exception(exc: DomainError) -> APIException:
    api_exc = APIException(detail=str(exc), code=exc.code)
    api_exc.status_code = exc.status_code
    return api_exc


def problem_details_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        exc = _as_api_exception(exc)

    response = exception_handler(exc, context)
    if response is None:
        return None

    problem: dict[str, Any] = {
        "type": "about:blank",
        "title": response.status_text,
        "status": response.status_code,
    }
    if isinstance(exc, ValidationError):
        problem["detail"] = "Request validation failed."
        problem["errors"] = response.data
    elif isinstance(exc, APIException):
        problem["detail"] = str(exc.detail)
        codes = exc.get_codes()
        if isinstance(codes, str):
            problem["code"] = codes

    response.data = problem
    response.content_type = PROBLEM_CONTENT_TYPE
    return response

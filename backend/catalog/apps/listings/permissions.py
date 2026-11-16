from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request


class IsHost(BasePermission):
    message = "Only hosts can manage listings."

    def has_permission(self, request: Request, view: Any) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_host)

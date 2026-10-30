from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register


@register(Tags.security)
def jwt_signing_key_check(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    if settings.SIMPLE_JWT.get("SIGNING_KEY"):
        return []
    return [
        Error(
            "JWT signing key is not configured.",
            hint="Run `manage.py generate_jwt_keys` and set JWT_PRIVATE_KEY_FILE.",
            id="users.E001",
        )
    ]

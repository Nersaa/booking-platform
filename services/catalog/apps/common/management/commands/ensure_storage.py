from typing import Any

from django.core.management.base import BaseCommand

from apps.common import storage


class Command(BaseCommand):
    help = "Create the photo bucket and its public-read policy (idempotent)."
    requires_system_checks: list[str] = []

    def handle(self, *args: Any, **options: Any) -> None:
        storage.ensure_bucket()
        self.stdout.write(self.style.SUCCESS("Object storage is ready."))

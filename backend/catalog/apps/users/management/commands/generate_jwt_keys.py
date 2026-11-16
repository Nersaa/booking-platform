import os
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Generate an RSA private key used to sign JWTs."
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--path", default=os.environ.get("JWT_PRIVATE_KEY_FILE"))
        parser.add_argument("--if-missing", action="store_true")
        parser.add_argument("--bits", type=int, default=3072)

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["path"]:
            raise CommandError("Pass --path or set JWT_PRIVATE_KEY_FILE.")
        path = Path(options["path"])
        if path.exists():
            if options["if_missing"]:
                self.stdout.write("JWT key already exists, skipping.")
                return
            raise CommandError(f"{path} already exists.")

        key = rsa.generate_private_key(public_exponent=65537, key_size=options["bits"])
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(pem)
        self.stdout.write(self.style.SUCCESS(f"JWT key written to {path}"))

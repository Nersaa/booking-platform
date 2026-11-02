"""Create or update .env from .env.example.

Every `change-me` becomes a random secret. An existing .env keeps its values; only keys
added to the template since then are appended, so upgrading never rotates live passwords.
"""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / ".env.example"
TARGET = ROOT / ".env"
PLACEHOLDER = "change-me"


def filled(line: str) -> str:
    key, sep, value = line.partition("=")
    return f"{key}={secrets.token_urlsafe(48)}" if sep and value == PLACEHOLDER else line


def key_of(line: str) -> str | None:
    key, sep, _ = line.partition("=")
    return key.strip() if sep and not line.lstrip().startswith("#") else None


def main() -> int:
    template = TEMPLATE.read_text(encoding="utf-8").splitlines()

    if not TARGET.exists():
        TARGET.write_text("\n".join(filled(line) for line in template) + "\n", encoding="utf-8")
        print("Created .env with generated secrets.")
        return 0

    existing = TARGET.read_text(encoding="utf-8")
    present = {key_of(line) for line in existing.splitlines()}
    missing = [filled(line) for line in template if key_of(line) and key_of(line) not in present]
    if not missing:
        print(".env is up to date.")
        return 0

    with TARGET.open("a", encoding="utf-8") as env_file:
        env_file.write(("" if existing.endswith("\n") else "\n") + "\n".join(missing) + "\n")
    print("Added to .env: " + ", ".join(line.partition("=")[0] for line in missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())

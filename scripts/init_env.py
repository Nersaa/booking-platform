"""Create .env from .env.example, replacing every `change-me` with a random secret."""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / ".env.example"
TARGET = ROOT / ".env"
PLACEHOLDER = "change-me"


def main() -> int:
    if TARGET.exists():
        print(".env already exists, leaving it untouched.")
        return 0

    lines = []
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and value == PLACEHOLDER:
            line = f"{key}={secrets.token_urlsafe(48)}"
        lines.append(line)

    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Created .env with generated secrets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

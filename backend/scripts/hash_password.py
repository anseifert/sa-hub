#!/usr/bin/env python3
"""Generate a bcrypt hash for AUTH_PASSWORD_HASH or secrets/auth_password_hash."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.app_auth import hash_password  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/hash_password.py 'your password'", file=sys.stderr)
        print("       docker compose exec backend python scripts/hash_password.py 'your password'")
        sys.exit(1)
    print(hash_password(sys.argv[1]))


if __name__ == "__main__":
    main()

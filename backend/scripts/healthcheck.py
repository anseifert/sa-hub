#!/usr/bin/env python3
"""Container health probe — exits 0 when /health responds."""
import sys

import httpx


def main() -> None:
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=8.0)
        r.raise_for_status()
    except Exception as exc:
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

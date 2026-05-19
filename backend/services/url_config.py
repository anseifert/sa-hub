import os
import logging

logger = logging.getLogger(__name__)


def normalize_base_url(value: str | None, default: str) -> str:
    """Strip whitespace and common copy-paste typos (e.g. trailing '}' from Caddy/README)."""
    url = (value or default).strip()
    if url.endswith("}"):
        logger.warning("Stripped trailing '}' from URL env value — fix .env: %r", url)
        url = url[:-1].strip()
    return url.rstrip("/")


def get_frontend_url() -> str:
    return normalize_base_url(
        os.getenv("FRONTEND_URL") or os.getenv("PUBLIC_URL"),
        "http://localhost:3000",
    )


def get_public_url() -> str:
    return normalize_base_url(os.getenv("PUBLIC_URL"), "http://localhost:3000")

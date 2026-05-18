import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from fastapi import HTTPException, Request, Response
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

COOKIE_NAME = "sa_hub_session"
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Return a bcrypt hash suitable for AUTH_PASSWORD_HASH or a secrets file."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _read_password_hash() -> str:
    path = os.getenv("AUTH_PASSWORD_HASH_FILE", "").strip()
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return os.getenv("AUTH_PASSWORD_HASH", "").strip()


def auth_enabled() -> bool:
    user = os.getenv("AUTH_USERNAME", "").strip()
    if not user:
        return False
    return bool(_read_password_hash() or os.getenv("AUTH_PASSWORD", "").strip())


def _secret() -> str:
    key = os.getenv("SECRET_KEY", "").strip()
    if auth_enabled() and not key:
        raise RuntimeError(
            "SECRET_KEY is required when AUTH_USERNAME and AUTH_PASSWORD_HASH are set"
        )
    return key or "dev-insecure-secret"


def verify_credentials(username: str, password: str) -> bool:
    expected_user = os.getenv("AUTH_USERNAME", "").strip()
    if not secrets.compare_digest(username, expected_user):
        return False

    stored_hash = _read_password_hash()
    if stored_hash:
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"),
                stored_hash.encode("utf-8"),
            )
        except ValueError:
            logger.error("Invalid AUTH_PASSWORD_HASH — run: python scripts/hash_password.py")
            return False

    legacy = os.getenv("AUTH_PASSWORD", "")
    if legacy:
        logger.warning(
            "AUTH_PASSWORD in plain text is deprecated; use AUTH_PASSWORD_HASH instead "
            "(see README or: python scripts/hash_password.py 'your password')"
        )
        return secrets.compare_digest(password, legacy)

    return False


def create_session_token(username: str) -> str:
    days = int(os.getenv("AUTH_SESSION_DAYS", "30"))
    expire = datetime.now(timezone.utc) + timedelta(days=days)
    return jwt.encode({"sub": username, "exp": expire}, _secret(), algorithm=ALGORITHM)


def decode_session_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def set_session_cookie(response: Response, token: str) -> None:
    days = int(os.getenv("AUTH_SESSION_DAYS", "30"))
    secure = os.getenv("PUBLIC_URL", "").strip().lower().startswith("https://")
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=days * 24 * 3600,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    secure = os.getenv("PUBLIC_URL", "").strip().lower().startswith("https://")
    response.delete_cookie(key=COOKIE_NAME, path="/", secure=secure, samesite="lax")


async def require_user(request: Request) -> str:
    if not auth_enabled():
        return "local"
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = decode_session_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return username

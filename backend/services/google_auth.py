import asyncio
import logging
import os
import json
from datetime import datetime, timedelta, timezone
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.db import OAuthToken
from services.url_config import normalize_base_url, get_public_url
from services.db_util import commit_with_retry

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

def get_redirect_uri() -> str:
    explicit = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if explicit:
        return normalize_base_url(explicit, explicit)
    return f"{get_public_url()}/api/auth/google/callback"


def _google_redirect_uri() -> str:
    return get_redirect_uri()


def _client_config():
    redirect_uri = _google_redirect_uri()
    return {
        "web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def _ensure_google_oauth_configured() -> None:
    if not os.getenv("GOOGLE_CLIENT_ID", "").strip():
        raise ValueError("GOOGLE_CLIENT_ID is not set")
    if not os.getenv("GOOGLE_CLIENT_SECRET", "").strip():
        raise ValueError("GOOGLE_CLIENT_SECRET is not set")


def get_flow():
    _ensure_google_oauth_configured()
    redirect_uri = _google_redirect_uri()
    return Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def _utc_expiry(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def credentials_from_token(token: OAuthToken) -> Credentials:
    """Build Credentials with expiry so we refresh before API 401s."""
    return Credentials(
        token=token.access_token,
        refresh_token=token.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=json.loads(token.scopes) if token.scopes else SCOPES,
        expiry=_utc_expiry(token.token_expiry),
    )


def credentials_need_refresh(creds: Credentials, *, skew_minutes: int = 5) -> bool:
    if not creds.refresh_token:
        return False
    if creds.expired:
        return True
    if creds.expiry is None:
        return True
    return creds.expiry <= datetime.now(timezone.utc) + timedelta(minutes=skew_minutes)


async def refresh_credentials(db: AsyncSession, creds: Credentials) -> Credentials:
    """Refresh access token and persist to DB."""
    logger.info("Refreshing Google access token")
    await asyncio.to_thread(creds.refresh, Request())
    await save_token(db, creds)
    return creds


async def save_token(db: AsyncSession, credentials: Credentials):
    result = await db.execute(select(OAuthToken).where(OAuthToken.provider == "google"))
    token = result.scalar_one_or_none()
    token_data = {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_expiry": credentials.expiry,
        "scopes": json.dumps(list(credentials.scopes or SCOPES)),
    }
    if token:
        for k, v in token_data.items():
            setattr(token, k, v)
        token.updated_at = datetime.utcnow()
    else:
        token = OAuthToken(provider="google", **token_data)
        db.add(token)
    await commit_with_retry(db)


async def get_credentials(db: AsyncSession) -> Credentials | None:
    result = await db.execute(select(OAuthToken).where(OAuthToken.provider == "google"))
    token = result.scalar_one_or_none()
    if not token:
        return None
    creds = credentials_from_token(token)
    if credentials_need_refresh(creds):
        try:
            creds = await refresh_credentials(db, creds)
        except Exception as exc:
            logger.error("Google token refresh failed: %s", exc)
            raise
    return creds


async def is_connected(db: AsyncSession) -> bool:
    creds = await get_credentials(db)
    return creds is not None

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import get_db
from models.db import SyncLog
from services.google_auth import get_flow, save_token, is_connected, get_redirect_uri
from services.url_config import get_frontend_url
from services.app_auth import (
    auth_enabled,
    clear_session_cookie,
    create_session_token,
    decode_session_token,
    require_user,
    set_session_cookie,
    verify_credentials,
    COOKIE_NAME,
)
import os

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.get("/session")
async def app_session(request: Request):
    if not auth_enabled():
        return {"auth_required": False, "authenticated": True}
    token = request.cookies.get(COOKIE_NAME)
    username = decode_session_token(token) if token else None
    return {
        "auth_required": True,
        "authenticated": bool(username),
        "username": username,
    }


@router.post("/login")
async def app_login(body: LoginBody, response: Response):
    if not auth_enabled():
        raise HTTPException(status_code=400, detail="App login is not configured")
    if not verify_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_session_token(body.username)
    set_session_cookie(response, token)
    return {"ok": True, "username": body.username}


@router.post("/logout")
async def app_logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/google")
async def google_login(_user: str = Depends(require_user)):
    try:
        flow = get_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(require_user),
):
    flow = get_flow()
    flow.fetch_token(code=code)
    await save_token(db, flow.credentials)
    return RedirectResponse(f"{get_frontend_url()}?connected=true")


@router.get("/status")
async def auth_status(db: AsyncSession = Depends(get_db), _user: str = Depends(require_user)):
    from services.slack_service import is_connected as slack_connected

    async def _last_sync(sync_type: str):
        result = await db.execute(
            select(SyncLog)
            .where(SyncLog.sync_type == sync_type)
            .order_by(SyncLog.started_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        return {
            "status": row.status,
            "message": row.message,
            "started_at": row.started_at.isoformat() if row.started_at else None,
        }

    return {
        "google": await is_connected(db),
        "slack": await slack_connected(),
        "gmail_sync": await _last_sync("gmail"),
        "drive_sync": await _last_sync("drive"),
        "google_redirect_uri": get_redirect_uri(),
    }

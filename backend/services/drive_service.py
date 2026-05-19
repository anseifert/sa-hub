import asyncio
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import SyncLog
from services.google_auth import get_credentials
from services.db_util import commit_with_retry, rollback_session
from datetime import datetime

logger = logging.getLogger(__name__)

GOOGLE_DOC_MIME = "application/vnd.google-apps.document"


def _format_drive_error(exc: Exception) -> str:
    if isinstance(exc, HttpError):
        content = ""
        if exc.content:
            try:
                content = exc.content.decode("utf-8")
            except Exception:
                content = str(exc.content)
        if exc.resp.status == 403 and "accessNotConfigured" in content:
            return (
                "Google Drive API is not enabled for this Cloud project. "
                "Enable it at console.cloud.google.com → APIs & Services → Library → Google Drive API."
            )
        if exc.resp.status == 403:
            return f"Drive access denied: {content[:300] or str(exc)}"
        return f"Drive API error {exc.resp.status}: {content[:300] or str(exc)}"
    return str(exc)


def _fetch_drive_docs_blocking(creds, max_docs: int) -> str:
    service = build("drive", "v3", credentials=creds)
    results = service.files().list(
        q=f"mimeType='{GOOGLE_DOC_MIME}' and trashed=false",
        orderBy="modifiedTime desc",
        pageSize=max_docs,
        fields="files(id, name, modifiedTime)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    files = results.get("files", [])
    combined_text = []

    for f in files:
        try:
            raw = service.files().export(
                fileId=f["id"],
                mimeType="text/plain",
            ).execute()
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            if text.strip():
                combined_text.append(f"## {f['name']}\n{text[:1000]}")
        except Exception as e:
            logger.warning("Drive export failed for %s: %s", f.get("name"), e)

    return "\n\n".join(combined_text)


async def fetch_recent_docs(db: AsyncSession, max_docs: int = 10) -> str:
    """Fetch text from recent Google Docs via Drive export (drive.readonly only)."""
    log = SyncLog(sync_type="drive", status="running", started_at=datetime.utcnow())
    db.add(log)
    await commit_with_retry(db)

    try:
        creds = await get_credentials(db)
        if not creds:
            raise Exception("Google not connected")

        combined_text = await asyncio.to_thread(_fetch_drive_docs_blocking, creds, max_docs)

        from services.google_auth import save_token
        await save_token(db, creds)

        doc_count = combined_text.count("## ") if combined_text else 0

        log.status = "success"
        log.message = f"Fetched {doc_count} docs"
        log.finished_at = datetime.utcnow()
        await commit_with_retry(db)

        return combined_text

    except Exception as e:
        msg = _format_drive_error(e)
        logger.error("Drive sync failed: %s", msg)
        await rollback_session(db)
        await db.refresh(log)
        log.status = "error"
        log.message = msg
        log.finished_at = datetime.utcnow()
        try:
            await commit_with_retry(db)
        except Exception:
            logger.exception("Could not persist drive sync error log")
        return ""

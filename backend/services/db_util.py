"""SQLite helpers — retries and safe rollback for concurrent sync + API traffic."""
import asyncio
import logging

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _is_locked(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "sqlite_busy" in msg or "locked" in msg


async def rollback_session(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception:
        pass


async def commit_with_retry(db: AsyncSession, retries: int = 6) -> None:
    """Commit with exponential backoff when SQLite reports a lock."""
    last: BaseException | None = None
    for attempt in range(retries):
        try:
            await db.commit()
            return
        except (OperationalError, DBAPIError) as exc:
            last = exc
            if not _is_locked(exc):
                raise
            await rollback_session(db)
            delay = min(0.05 * (2**attempt), 2.0)
            logger.debug("SQLite busy, retry %s/%s (%.2fs)", attempt + 1, retries, delay)
            await asyncio.sleep(delay)
    if last:
        raise last

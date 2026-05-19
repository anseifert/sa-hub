from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from models.database import SessionLocal
from services.gmail_service import sync_gmail
from services.drive_service import fetch_recent_docs
from services.slack_service import fetch_recent_messages
from services.ai_service import enrich_contacts, generate_one_pager
from services.db_util import rollback_session
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def run_full_sync():
    from services.sync_state import is_sync_running
    if is_sync_running():
        logger.info("Sync already in progress, skipping")
        return

    from services.sync_state import run_sync_guarded

    async def _do_sync():
        logger.info("Starting sync...")
        await _run_sync_body()

    await run_sync_guarded(_do_sync)


async def _run_sync_step(step_name: str, fn):
    """Each step uses its own DB session so a lock in one step cannot poison the next."""
    async with SessionLocal() as db:
        try:
            return await fn(db)
        except Exception:
            logger.exception("%s failed", step_name)
            await rollback_session(db)
            return None


async def _run_sync_body():
    logger.info("Sync body started")

    await _run_sync_step("Gmail sync", sync_gmail)
    logger.info("Gmail sync step finished")

    await _run_sync_step("Contact enrichment", enrich_contacts)
    logger.info("Contact enrichment step finished")

    docs_content = await _run_sync_step("Drive sync", fetch_recent_docs) or ""
    logger.info("Drive sync step finished")

    slack_content = await _run_sync_step("Slack sync", fetch_recent_messages) or ""
    logger.info("Slack sync step finished")

    async def _one_pager(db):
        await generate_one_pager(db, docs_content, slack_content)

    await _run_sync_step("One-pager generation", _one_pager)
    logger.info("Sync body finished")


async def run_one_pager_only():
    """Refresh Drive/Slack context and regenerate the one-pager."""
    from services.sync_state import run_sync_guarded

    async def _do():
        docs_content = await _run_sync_step("Drive sync (one-pager)", fetch_recent_docs) or ""
        slack_content = await _run_sync_step("Slack sync (one-pager)", fetch_recent_messages) or ""

        async def _gen(db):
            await generate_one_pager(db, docs_content, slack_content)

        await _run_sync_step("One-pager generation", _gen)

    await run_sync_guarded(_do)


def start_scheduler():
    scheduler.add_job(
        run_full_sync,
        trigger=IntervalTrigger(hours=1),
        id="hourly_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler started — sync every hour (skips if already running)")


def stop_scheduler():
    scheduler.shutdown()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from models.database import SessionLocal
from services.gmail_service import sync_gmail
from services.drive_service import fetch_recent_docs
from services.slack_service import fetch_recent_messages
from services.ai_service import enrich_contacts, generate_one_pager
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
        async with SessionLocal() as db:
            await _run_sync_body(db)

    await run_sync_guarded(_do_sync)


async def _run_sync_body(db):
    logger.info("Sync body started")
    try:
        await sync_gmail(db)
        logger.info("Gmail sync complete")
    except Exception:
        logger.exception("Gmail sync failed")

    try:
        await enrich_contacts(db)
        logger.info("Contact enrichment complete")
    except Exception:
        logger.exception("Contact enrichment failed")

    docs_content = ""
    slack_content = ""

    try:
        docs_content = await fetch_recent_docs(db)
        logger.info("Drive sync complete")
    except Exception:
        logger.exception("Drive sync failed")

    try:
        slack_content = await fetch_recent_messages(db)
        logger.info("Slack sync complete")
    except Exception:
        logger.exception("Slack sync failed")

    try:
        await generate_one_pager(db, docs_content, slack_content)
        logger.info("One-pager generation complete")
    except Exception:
        logger.exception("One-pager generation failed")

    logger.info("Sync body finished")


def start_scheduler():
    scheduler.add_job(
        run_full_sync,
        trigger=IntervalTrigger(hours=1),
        id="hourly_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started - hourly sync active")


def stop_scheduler():
    scheduler.shutdown()

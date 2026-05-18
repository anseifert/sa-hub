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
    logger.info("Starting hourly sync...")
    async with SessionLocal() as db:
        try:
            # 1. Pull Gmail (contacts + follow-ups)
            await sync_gmail(db)
            logger.info("Gmail sync complete")
        except Exception as e:
            logger.error(f"Gmail sync failed: {e}")

        try:
            # 2. Enrich contacts with AI (company/title inference)
            await enrich_contacts(db)
            logger.info("Contact enrichment complete")
        except Exception as e:
            logger.error(f"Contact enrichment failed: {e}")

        docs_content = ""
        slack_content = ""

        try:
            # 3. Pull Google Docs
            docs_content = await fetch_recent_docs(db)
            logger.info("Drive sync complete")
        except Exception as e:
            logger.error(f"Drive sync failed: {e}")

        try:
            # 4. Pull Slack (if connected)
            slack_content = await fetch_recent_messages(db)
            logger.info("Slack sync complete")
        except Exception as e:
            logger.error(f"Slack sync failed: {e}")

        try:
            # 5. Generate one-pager
            await generate_one_pager(db, docs_content, slack_content)
            logger.info("One-pager generation complete")
        except Exception as e:
            logger.error(f"One-pager generation failed: {e}")

    logger.info("Hourly sync finished")


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

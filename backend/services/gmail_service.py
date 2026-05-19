import asyncio
import logging
import os
import re
from datetime import datetime

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.db import Contact, FollowUp, SyncLog
from services.google_auth import get_credentials, credentials_need_refresh, refresh_credentials
from services.db_util import commit_with_retry, rollback_session

logger = logging.getLogger(__name__)

REDHAT_DOMAINS = {"redhat.com", "red-hat.com"}

# Limit initial/hourly sync — unbounded "all sent mail" blocks the server for minutes
GMAIL_SYNC_QUERY = os.getenv("GMAIL_SYNC_QUERY", "newer_than:730d")
GMAIL_SYNC_MAX_PAGES = int(os.getenv("GMAIL_SYNC_MAX_PAGES", "20"))


def _is_internal(email_addr: str) -> bool:
    domain = email_addr.split("@")[-1].lower()
    return domain in REDHAT_DOMAINS


def _extract_email_name(header: str):
    match = re.match(r'"?([^"<]+)"?\s*<([^>]+)>', header)
    if match:
        return match.group(1).strip(), match.group(2).strip().lower()
    return None, header.strip().lower()


def _parse_date(date_str: str) -> datetime | None:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        return None


def _fetch_gmail_data(creds: Credentials) -> dict:
    """Blocking Gmail API work — run via asyncio.to_thread only."""
    if credentials_need_refresh(creds):
        logger.info("Refreshing Google token during Gmail sync")
        creds.refresh(Request())

    service = build("gmail", "v1", credentials=creds)
    contacts_map: dict[str, dict] = {}
    follow_ups: list[dict] = []
    total_processed = 0
    page_token = None
    pages = 0

    list_query = f"in:sent {GMAIL_SYNC_QUERY}".strip()

    while pages < GMAIL_SYNC_MAX_PAGES:
        kwargs = {
            "userId": "me",
            "labelIds": ["SENT"],
            "q": GMAIL_SYNC_QUERY,
            "maxResults": 500,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        results = service.users().messages().list(**kwargs).execute()
        messages = results.get("messages", [])

        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me",
                id=msg_ref["id"],
                format="metadata",
                metadataHeaders=["To", "Cc", "Subject", "Date", "Message-ID", "In-Reply-To"],
            ).execute()

            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            date = _parse_date(headers.get("Date", ""))

            for field in ["To", "Cc"]:
                raw = headers.get(field, "")
                for part in raw.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    name, addr = _extract_email_name(part)
                    if not addr or "@" not in addr or _is_internal(addr):
                        continue
                    domain = addr.split("@")[-1]
                    existing = contacts_map.get(addr, {})
                    contacts_map[addr] = {
                        "email": addr,
                        "name": name or existing.get("name"),
                        "domain": domain,
                        "last_contact": max(
                            filter(None, [date, existing.get("last_contact")]),
                            default=date,
                        ),
                        "email_count": existing.get("email_count", 0) + 1,
                    }

            total_processed += 1

        pages += 1
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    logger.info(
        "Gmail list query=%r pages=%s messages=%s contacts=%s",
        list_query,
        pages,
        total_processed,
        len(contacts_map),
    )

    # Follow-ups: recent sent threads only
    results = service.users().messages().list(
        userId="me",
        labelIds=["SENT"],
        q=f"newer_than:90d",
        maxResults=200,
    ).execute()

    thread_ids = {m.get("threadId") for m in results.get("messages", []) if m.get("threadId")}
    now = datetime.utcnow()

    for thread_id in list(thread_ids)[:100]:
        thread = service.users().threads().get(
            userId="me",
            id=thread_id,
            format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()
        msgs = thread.get("messages", [])
        if not msgs:
            continue

        last_msg = msgs[-1]
        headers = {
            h["name"]: h["value"]
            for h in last_msg.get("payload", {}).get("headers", [])
        }
        _, from_email = _extract_email_name(headers.get("From", ""))

        if not _is_internal(from_email):
            continue

        date = _parse_date(headers.get("Date", ""))
        if not date:
            continue

        days_waiting = (now - date).days
        if days_waiting < 7:
            continue

        to_header = headers.get("To", "")
        _, to_email = _extract_email_name(to_header.split(",")[0])
        if _is_internal(to_email):
            continue

        follow_ups.append({
            "thread_id": thread_id,
            "contact_email": to_email,
            "subject": headers.get("Subject", "(no subject)"),
            "sent_at": date,
            "days_waiting": days_waiting,
        })

    return {
        "contacts_map": contacts_map,
        "follow_ups": follow_ups,
        "total_processed": total_processed,
    }


async def _persist_gmail_data(db: AsyncSession, data: dict) -> None:
    for addr, row in data["contacts_map"].items():
        result = await db.execute(select(Contact).where(Contact.email == addr))
        contact = result.scalar_one_or_none()
        if contact:
            contact.name = row["name"] or contact.name
            contact.domain = row["domain"]
            contact.last_contact = row["last_contact"]
            contact.email_count = (contact.email_count or 0) + row["email_count"]
            contact.updated_at = datetime.utcnow()
        else:
            db.add(Contact(**row))

    await commit_with_retry(db)

    for fu in data["follow_ups"]:
        result = await db.execute(
            select(FollowUp).where(
                FollowUp.source_id == fu["thread_id"],
                FollowUp.resolved == False,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.days_waiting = fu["days_waiting"]
            existing.updated_at = datetime.utcnow()
        else:
            db.add(FollowUp(
                source="email",
                source_id=fu["thread_id"],
                contact_email=fu["contact_email"],
                subject=fu["subject"],
                sent_at=fu["sent_at"],
                days_waiting=fu["days_waiting"],
            ))

    await commit_with_retry(db)


async def sync_gmail(db: AsyncSession):
    log = SyncLog(sync_type="gmail", status="running", started_at=datetime.utcnow())
    db.add(log)
    await commit_with_retry(db)

    try:
        creds = await get_credentials(db)
        if not creds:
            raise Exception("Google not connected")

        # Run blocking Google HTTP in a thread so /health and login stay responsive
        data = await asyncio.to_thread(_fetch_gmail_data, creds)

        from services.google_auth import save_token
        await save_token(db, creds)

        await _persist_gmail_data(db, data)

        log.status = "success"
        log.message = (
            f"Processed {data['total_processed']} sent messages, "
            f"{len(data['contacts_map'])} contacts"
        )
        log.finished_at = datetime.utcnow()
        await commit_with_retry(db)

    except Exception as e:
        logger.exception("Gmail sync failed")
        await rollback_session(db)
        await db.refresh(log)
        log.status = "error"
        log.message = str(e)
        log.finished_at = datetime.utcnow()
        try:
            await commit_with_retry(db)
        except Exception:
            logger.exception("Could not persist Gmail sync error log")


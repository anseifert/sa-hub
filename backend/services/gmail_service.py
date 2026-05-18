import re
import base64
import email as email_lib
from datetime import datetime, timezone
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from models.db import Contact, FollowUp, SyncLog
from services.google_auth import get_credentials

REDHAT_DOMAINS = {"redhat.com", "red-hat.com"}


def _is_internal(email_addr: str) -> bool:
    domain = email_addr.split("@")[-1].lower()
    return domain in REDHAT_DOMAINS


def _extract_email_name(header: str):
    """Parse 'Name <email>' or 'email' format."""
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


async def sync_gmail(db: AsyncSession):
    log = SyncLog(sync_type="gmail", status="running", started_at=datetime.utcnow())
    db.add(log)
    await db.commit()

    try:
        creds = await get_credentials(db)
        if not creds:
            raise Exception("Google not connected")

        service = build("gmail", "v1", credentials=creds)

        # Fetch all sent messages to extract customer contacts
        contacts_map: dict[str, dict] = {}
        follow_up_threads: list[dict] = []

        page_token = None
        total_processed = 0

        while True:
            kwargs = {"userId": "me", "labelIds": ["SENT"], "maxResults": 500}
            if page_token:
                kwargs["pageToken"] = page_token

            results = service.users().messages().list(**kwargs).execute()
            messages = results.get("messages", [])

            for msg_ref in messages:
                msg = service.users().messages().get(
                    userId="me", id=msg_ref["id"], format="metadata",
                    metadataHeaders=["To", "Cc", "Subject", "Date", "Message-ID", "In-Reply-To"]
                ).execute()

                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                date = _parse_date(headers.get("Date", ""))
                subject = headers.get("Subject", "(no subject)")
                thread_id = msg.get("threadId")

                # Extract recipients
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

            page_token = results.get("nextPageToken")
            if not page_token:
                break

        # Upsert contacts
        for addr, data in contacts_map.items():
            result = await db.execute(select(Contact).where(Contact.email == addr))
            contact = result.scalar_one_or_none()
            if contact:
                contact.name = data["name"] or contact.name
                contact.domain = data["domain"]
                contact.last_contact = data["last_contact"]
                contact.email_count = (contact.email_count or 0) + data["email_count"]
                contact.updated_at = datetime.utcnow()
            else:
                db.add(Contact(**data))

        await db.commit()

        # Now detect follow-ups: sent threads with no reply in 7+ days
        await _detect_follow_ups(db, service)

        log.status = "success"
        log.message = f"Processed {total_processed} sent messages, {len(contacts_map)} contacts"
        log.finished_at = datetime.utcnow()
        await db.commit()

    except Exception as e:
        log.status = "error"
        log.message = str(e)
        log.finished_at = datetime.utcnow()
        await db.commit()
        raise


async def _detect_follow_ups(db: AsyncSession, service):
    from datetime import timedelta

    now = datetime.utcnow()
    threshold = timedelta(days=7)

    # Get recent sent messages (last 90 days for performance)
    results = service.users().messages().list(
        userId="me", labelIds=["SENT"],
        q="newer_than:90d", maxResults=200
    ).execute()

    messages = results.get("messages", [])
    thread_ids = set()

    for msg_ref in messages:
        thread_ids.add(msg_ref.get("threadId"))

    for thread_id in list(thread_ids)[:100]:  # cap to avoid rate limits
        thread = service.users().threads().get(userId="me", id=thread_id, format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"]).execute()
        msgs = thread.get("messages", [])
        if not msgs:
            continue

        last_msg = msgs[-1]
        headers = {h["name"]: h["value"] for h in last_msg.get("payload", {}).get("headers", [])}
        from_addr = headers.get("From", "")
        _, from_email = _extract_email_name(from_addr)

        # Only flag if WE sent the last message
        if not _is_internal(from_email):
            continue

        date = _parse_date(headers.get("Date", ""))
        if not date:
            continue

        days_waiting = (now - date).days
        if days_waiting < 7:
            continue

        # Get customer in the thread
        to_header = headers.get("To", "")
        _, to_email = _extract_email_name(to_header.split(",")[0])
        if _is_internal(to_email):
            continue

        # Check if already tracked
        result = await db.execute(
            select(FollowUp).where(FollowUp.source_id == thread_id, FollowUp.resolved == False)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.days_waiting = days_waiting
            existing.updated_at = datetime.utcnow()
        else:
            db.add(FollowUp(
                source="email",
                source_id=thread_id,
                contact_email=to_email,
                subject=headers.get("Subject", "(no subject)"),
                sent_at=date,
                days_waiting=days_waiting,
            ))

    await db.commit()

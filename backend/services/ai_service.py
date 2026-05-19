import logging
import os
import json
import httpx
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.db import Contact, Account, OnePager, FollowUp, SyncLog

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://ollama:11434/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
ENRICH_CONTACTS = os.getenv("ENRICH_CONTACTS", "true").lower() in ("1", "true", "yes")
ENRICH_MAX_CONTACTS = int(os.getenv("ENRICH_MAX_CONTACTS", "150"))
SYNC_AI_ENABLED = os.getenv("SYNC_AI_ENABLED", "true").lower() in ("1", "true", "yes")


def _format_error(exc: BaseException) -> str:
    msg = str(exc).strip()
    if msg:
        return f"{type(exc).__name__}: {msg}"
    return f"{type(exc).__name__} (no message)"


def _ollama_root() -> str:
    return LLM_BASE_URL.replace("/v1", "").rstrip("/")


async def check_llm_available() -> str | None:
    """Return a human-readable error if Ollama/model is unavailable, else None."""
    root = _ollama_root()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{root}/api/tags")
            r.raise_for_status()
            names = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception as exc:
        return f"Cannot reach Ollama at {root} — {_format_error(exc)}"

    if not names:
        return f"No models in Ollama. On the host run: podman exec -it sa-hub-ollama ollama pull {LLM_MODEL}"

    model_base = LLM_MODEL.split(":")[0]
    if not any(model_base in name for name in names):
        return (
            f"Model {LLM_MODEL!r} not loaded. Available: {', '.join(names[:5])}. "
            f"Run: podman exec -it sa-hub-ollama ollama pull {LLM_MODEL}"
        )
    return None

ONE_PAGER_SECTIONS = [
    {"key": "priorities", "title": "Current Priorities & Focus Areas", "order": 0},
    {"key": "active_accounts", "title": "Active Accounts & Status", "order": 1},
    {"key": "follow_ups", "title": "Pending Follow-Ups", "order": 2},
    {"key": "ideas", "title": "Ideas & Notes from Slack/Docs", "order": 3},
    {"key": "wins", "title": "Recent Wins & Progress", "order": 4},
]


async def chat_completion(system: str, user: str, max_tokens: int = 2000) -> str:
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        if response.status_code >= 400:
            body = response.text[:500]
            raise RuntimeError(
                f"LLM HTTP {response.status_code} from {LLM_BASE_URL}: {body or '(empty body)'}"
            )
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected LLM response shape: {_format_error(exc)}") from exc


def _parse_json_array(text: str) -> list:
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


async def enrich_contacts(db: AsyncSession):
    """Use local LLM to infer company names and group contacts into accounts."""
    if not ENRICH_CONTACTS or not SYNC_AI_ENABLED:
        logger.info("Contact enrichment skipped (ENRICH_CONTACTS / SYNC_AI_ENABLED)")
        return

    llm_err = await check_llm_available()
    if llm_err:
        raise RuntimeError(llm_err)

    result = await db.execute(select(Contact).where(Contact.company == None))
    contacts = result.scalars().all()

    if not contacts:
        return

    if len(contacts) > ENRICH_MAX_CONTACTS:
        logger.info(
            "Limiting enrichment to %s of %s contacts (set ENRICH_MAX_CONTACTS to raise)",
            ENRICH_MAX_CONTACTS,
            len(contacts),
        )
        contacts = contacts[:ENRICH_MAX_CONTACTS]

    system_prompt = """You are a data enrichment assistant. Given a list of contacts with email addresses,
infer the company name and job title if possible from the email domain and name.
Return ONLY a JSON array with objects: {email, company, title}
Use the domain to infer company (e.g. boeing.com -> Boeing, ford.com -> Ford).
If you cannot determine title, use null. Be concise."""

    for i in range(0, len(contacts), 50):
        batch = contacts[i:i + 50]
        contact_list = [
            {"email": c.email, "name": c.name, "domain": c.domain}
            for c in batch
        ]

        enriched = None
        for attempt in range(2):
            try:
                text = await chat_completion(
                    system_prompt,
                    json.dumps(contact_list),
                    max_tokens=2000,
                )
                enriched = _parse_json_array(text)
                break
            except (json.JSONDecodeError, KeyError, IndexError) as exc:
                logger.warning(
                    "Enrichment JSON parse failed (batch %s, attempt %s): %s",
                    i // 50,
                    attempt + 1,
                    _format_error(exc),
                )
                if attempt == 1:
                    enriched = None
            except httpx.HTTPError as exc:
                raise RuntimeError(f"LLM request failed: {_format_error(exc)}") from exc

        if not enriched:
            continue

        for item in enriched:
            email = item.get("email")
            for contact in batch:
                if contact.email == email:
                    contact.company = item.get("company")
                    contact.title = item.get("title")
                    contact.updated_at = datetime.utcnow()
                    break

    await db.commit()
    await _build_accounts(db)


async def _build_accounts(db: AsyncSession):
    """Group contacts by company into the accounts table."""
    result = await db.execute(select(Contact).where(Contact.company != None))
    contacts = result.scalars().all()

    company_map: dict[str, list] = {}
    for c in contacts:
        company_map.setdefault(c.company, []).append(c)

    for company, members in company_map.items():
        last_activity = max((m.last_contact for m in members if m.last_contact), default=None)
        result = await db.execute(select(Account).where(Account.company == company))
        account = result.scalar_one_or_none()
        domain = members[0].domain if members else None
        if account:
            account.contact_count = len(members)
            account.last_activity = last_activity
            account.domain = domain
            account.updated_at = datetime.utcnow()
        else:
            db.add(Account(
                company=company,
                domain=domain,
                contact_count=len(members),
                last_activity=last_activity,
            ))

    await db.commit()


async def generate_one_pager(db: AsyncSession, docs_content: str = "", slack_content: str = ""):
    """Generate/refresh unpinned one-pager sections using the local LLM."""
    if not SYNC_AI_ENABLED:
        logger.info("One-pager generation skipped (SYNC_AI_ENABLED=false)")
        return

    log = SyncLog(sync_type="one_pager", status="running", started_at=datetime.utcnow())
    db.add(log)
    await db.commit()

    try:
        llm_err = await check_llm_available()
        if llm_err:
            raise RuntimeError(llm_err)

        followups_result = await db.execute(
            select(FollowUp).where(FollowUp.resolved == False).limit(20)
        )
        follow_ups = followups_result.scalars().all()
        followup_text = "\n".join([
            f"- {f.contact_email} | {f.subject} | {f.days_waiting} days waiting"
            for f in follow_ups
        ])

        accounts_result = await db.execute(select(Account).order_by(Account.last_activity.desc()).limit(10))
        accounts = accounts_result.scalars().all()
        accounts_text = "\n".join([
            f"- {a.company} ({a.contact_count} contacts, last activity: {a.last_activity})"
            for a in accounts
        ])

        context = f"""
PENDING FOLLOW-UPS:
{followup_text or "None"}

ACTIVE ACCOUNTS (recent activity):
{accounts_text or "None"}

GOOGLE DOCS CONTENT:
{docs_content or "No docs content available yet"}

SLACK CONTENT:
{slack_content or "No Slack content available yet"}
"""

        pinned_result = await db.execute(select(OnePager).where(OnePager.pinned == True))
        pinned_keys = {r.section_key for r in pinned_result.scalars().all()}

        for section in ONE_PAGER_SECTIONS:
            if section["key"] in pinned_keys:
                continue

            system_prompt = f"""You are an assistant helping a Red Hat Solutions Architect stay organized.
Generate the "{section['title']}" section of their one-page status document.
Be concise, actionable, and specific. Use bullet points. Max 200 words.
Base your response only on the context provided."""

            content = await chat_completion(system_prompt, context, max_tokens=500)

            result = await db.execute(
                select(OnePager).where(OnePager.section_key == section["key"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.content = content
                existing.last_ai_generated = datetime.utcnow()
                existing.updated_at = datetime.utcnow()
            else:
                db.add(OnePager(
                    section_key=section["key"],
                    title=section["title"],
                    content=content,
                    sort_order=section["order"],
                    last_ai_generated=datetime.utcnow(),
                ))

        await db.commit()
        log.status = "success"
        log.message = f"Generated {len(ONE_PAGER_SECTIONS) - len(pinned_keys)} sections"
        log.finished_at = datetime.utcnow()
        await db.commit()

    except Exception as e:
        log.status = "error"
        log.message = str(e)
        log.finished_at = datetime.utcnow()
        await db.commit()
        raise

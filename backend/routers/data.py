from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, update
from sqlalchemy.orm import selectinload
from models.database import get_db
from models.db import Contact, Account, FollowUp, OnePager, SyncLog
from services.app_auth import require_user
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

router = APIRouter(tags=["data"], dependencies=[Depends(require_user)])


# ── Contacts ──────────────────────────────────────────────

@router.get("/contacts")
async def get_contacts(
    q: str = Query(default=""),
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Contact).order_by(Contact.last_contact.desc())
    if q:
        stmt = stmt.where(
            or_(
                Contact.name.ilike(f"%{q}%"),
                Contact.email.ilike(f"%{q}%"),
                Contact.company.ilike(f"%{q}%"),
                Contact.title.ilike(f"%{q}%"),
            )
        )
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    contacts = result.scalars().all()
    total = await db.execute(select(func.count(Contact.id)))
    return {
        "contacts": [_contact_dict(c) for c in contacts],
        "total": total.scalar(),
    }


def _contact_dict(c: Contact):
    return {
        "id": c.id,
        "email": c.email,
        "name": c.name,
        "company": c.company,
        "title": c.title,
        "domain": c.domain,
        "last_contact": c.last_contact.isoformat() if c.last_contact else None,
        "email_count": c.email_count,
    }


# ── Accounts ──────────────────────────────────────────────

@router.get("/accounts")
async def get_accounts(
    q: str = Query(default=""),
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Account).order_by(Account.last_activity.desc())
    if q:
        stmt = stmt.where(
            or_(
                Account.company.ilike(f"%{q}%"),
                Account.domain.ilike(f"%{q}%"),
            )
        )
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    accounts = result.scalars().all()

    out = []
    for a in accounts:
        # Get contacts for this account
        contacts_result = await db.execute(
            select(Contact).where(Contact.company == a.company).limit(20)
        )
        contacts = contacts_result.scalars().all()
        out.append({
            "id": a.id,
            "company": a.company,
            "domain": a.domain,
            "contact_count": a.contact_count,
            "last_activity": a.last_activity.isoformat() if a.last_activity else None,
            "contacts": [_contact_dict(c) for c in contacts],
        })

    total_result = await db.execute(select(func.count(Account.id)))
    return {"accounts": out, "total": total_result.scalar()}


# ── Follow-ups ────────────────────────────────────────────

@router.get("/follow-ups")
async def get_follow_ups(
    resolved: bool = False,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(FollowUp).where(FollowUp.resolved == resolved).order_by(FollowUp.days_waiting.desc())
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": f.id,
            "source": f.source,
            "contact_email": f.contact_email,
            "contact_name": f.contact_name,
            "subject": f.subject,
            "snippet": f.snippet,
            "sent_at": f.sent_at.isoformat() if f.sent_at else None,
            "days_waiting": f.days_waiting,
            "resolved": f.resolved,
            "manually_flagged": f.manually_flagged,
        }
        for f in items
    ]


@router.patch("/follow-ups/{follow_up_id}/resolve")
async def resolve_follow_up(follow_up_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FollowUp).where(FollowUp.id == follow_up_id))
    fu = result.scalar_one_or_none()
    if not fu:
        raise HTTPException(status_code=404, detail="Not found")
    fu.resolved = True
    fu.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


# ── One-Pager ─────────────────────────────────────────────

@router.get("/one-pager")
async def get_one_pager(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OnePager).order_by(OnePager.sort_order))
    sections = result.scalars().all()
    return [
        {
            "id": s.id,
            "section_key": s.section_key,
            "title": s.title,
            "content": s.content,
            "pinned": s.pinned,
            "sort_order": s.sort_order,
            "last_ai_generated": s.last_ai_generated.isoformat() if s.last_ai_generated else None,
        }
        for s in sections
    ]


class SectionUpdate(BaseModel):
    content: Optional[str] = None
    pinned: Optional[bool] = None


@router.patch("/one-pager/{section_key}")
async def update_section(
    section_key: str,
    body: SectionUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OnePager).where(OnePager.section_key == section_key))
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if body.content is not None:
        section.content = body.content
    if body.pinned is not None:
        section.pinned = body.pinned
    section.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True}


# ── Sync ──────────────────────────────────────────────────

@router.post("/sync")
async def trigger_sync():
    from services.scheduler import run_full_sync
    import asyncio
    asyncio.create_task(run_full_sync())
    return {"ok": True, "message": "Sync started in background"}


@router.get("/sync/logs")
async def get_sync_logs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SyncLog).order_by(SyncLog.started_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "sync_type": l.sync_type,
            "status": l.status,
            "message": l.message,
            "started_at": l.started_at.isoformat() if l.started_at else None,
            "finished_at": l.finished_at.isoformat() if l.finished_at else None,
        }
        for l in logs
    ]

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id = Column(Integer, primary_key=True)
    provider = Column(String, unique=True, nullable=False)  # google, slack
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text)
    token_expiry = Column(DateTime)
    scopes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String)
    company = Column(String)
    title = Column(String)
    domain = Column(String)
    last_contact = Column(DateTime)
    email_count = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    company = Column(String, unique=True, nullable=False)
    domain = Column(String)
    contact_count = Column(Integer, default=0)
    last_activity = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FollowUp(Base):
    __tablename__ = "follow_ups"
    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False)  # email, slack
    source_id = Column(String)              # gmail thread id or slack channel+ts
    contact_email = Column(String)
    contact_name = Column(String)
    subject = Column(String)
    snippet = Column(Text)
    sent_at = Column(DateTime)
    days_waiting = Column(Integer)
    resolved = Column(Boolean, default=False)
    manually_flagged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OnePager(Base):
    __tablename__ = "one_pager"
    id = Column(Integer, primary_key=True)
    section_key = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text)
    pinned = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    last_ai_generated = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SyncLog(Base):
    __tablename__ = "sync_log"
    id = Column(Integer, primary_key=True)
    sync_type = Column(String)   # gmail, drive, slack, contacts, follow_ups, one_pager
    status = Column(String)      # running, success, error
    message = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)

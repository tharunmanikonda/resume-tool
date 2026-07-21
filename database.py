"""Database configuration and ORM models for persisted extension draft state."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    configured = os.getenv("DATABASE_URL", "").strip()
    if configured:
        if configured.startswith("postgres://"):
            return configured.replace("postgres://", "postgresql+psycopg://", 1)
        if configured.startswith("postgresql://") and "+psycopg" not in configured:
            return configured.replace("postgresql://", "postgresql+psycopg://", 1)
        return configured
    local_path = Path(os.getenv("LOCAL_DATABASE_PATH", "config/resume_tool.db"))
    local_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{local_path}"


class Base(DeclarativeBase):
    pass


class ResumeDraft(Base):
    __tablename__ = "resume_drafts"
    __table_args__ = (
        Index("ix_resume_drafts_source_lookup", "source", "external_job_id"),
        Index("ix_resume_drafts_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), default="linkedin", nullable=False)
    external_job_id: Mapped[str] = mapped_column(String(160), nullable=True)
    source_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=True)
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    role_title: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str] = mapped_column(String(300), nullable=True)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    description_hash: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    latest_description_hash: Mapped[str] = mapped_column(String(80), nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(60), default="queued", nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(80), default="waiting", nullable=False)
    duplicate_decision: Mapped[str] = mapped_column(String(30), nullable=True)
    identity_id: Mapped[str] = mapped_column(String(80), nullable=True)
    enabled_experience_keys: Mapped[list] = mapped_column(JSON, default=list)
    profile_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    contact_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    experience_history_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    title_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    skills: Mapped[dict] = mapped_column(JSON, default=dict)
    experience_recent: Mapped[dict] = mapped_column(JSON, default=dict)
    experience_older: Mapped[dict] = mapped_column(JSON, default=dict)
    resume_content: Mapped[str] = mapped_column(Text, nullable=True)
    resume_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    pdf_path: Mapped[str] = mapped_column(Text, nullable=True)
    docx_path: Mapped[str] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str] = mapped_column(Text, nullable=True)
    pdf_status_path: Mapped[str] = mapped_column(Text, nullable=True)
    pdf_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resume_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pdf_revision: Mapped[int] = mapped_column(Integer, nullable=True)
    pdf_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    application_id: Mapped[str] = mapped_column(String(80), nullable=True, index=True)
    error_stage: Mapped[str] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ResumeDraftTask(Base):
    __tablename__ = "resume_draft_tasks"
    __table_args__ = (
        Index("ix_resume_draft_tasks_queue", "status", "requested_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("resume_drafts.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), default="generate", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(80), default="waiting", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)


engine = create_engine(database_url(), future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if "resume_drafts" not in inspect(engine).get_table_names():
        return
    columns = {column["name"] for column in inspect(engine).get_columns("resume_drafts")}
    additions = {
        "resume_revision": "INTEGER NOT NULL DEFAULT 1",
        "pdf_revision": "INTEGER",
        "pdf_generated_at": "DATETIME",
    }
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE resume_drafts ADD COLUMN {name} {definition}"))
        connection.execute(text(
            "UPDATE resume_drafts "
            "SET pdf_revision = resume_revision, pdf_generated_at = updated_at "
            "WHERE status IN ('pdf_ready', 'applied') AND pdf_stale = 0 AND pdf_path IS NOT NULL "
            "AND (pdf_revision IS NULL OR pdf_generated_at IS NULL)"
        ))


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

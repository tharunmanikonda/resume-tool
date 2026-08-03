"""Database configuration and ORM models for persisted extension draft state."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    column,
    inspect,
    table,
    text,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.schema import CreateColumn
from sqlalchemy.sql import quoted_name


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
    resume_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    active_resume_version: Mapped[str] = mapped_column(String(40), nullable=True)
    pdf_path: Mapped[str] = mapped_column(Text, nullable=True)
    docx_path: Mapped[str] = mapped_column(Text, nullable=True)
    output_dir: Mapped[str] = mapped_column(Text, nullable=True)
    pdf_status_path: Mapped[str] = mapped_column(Text, nullable=True)
    pdf_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resume_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pdf_revision: Mapped[int] = mapped_column(Integer, nullable=True)
    pdf_generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_status: Mapped[str] = mapped_column(String(40), default="not_started", nullable=False)
    audit_result: Mapped[dict] = mapped_column(JSON, nullable=True)
    audit_proposal: Mapped[dict] = mapped_column(JSON, nullable=True)
    audit_base_revision: Mapped[int] = mapped_column(Integer, nullable=True)
    audit_base_hash: Mapped[str] = mapped_column(String(80), nullable=True)
    audit_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
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


def _resume_draft_migration_columns() -> tuple[Column, ...]:
    return (
        Column("resume_revision", Integer, nullable=False, server_default=text("1"), quote=True),
        Column("resume_versions", JSON, nullable=True, quote=True),
        Column("active_resume_version", String(40), nullable=True, quote=True),
        Column("pdf_revision", Integer, nullable=True, quote=True),
        Column("pdf_generated_at", DateTime(timezone=True), nullable=True, quote=True),
        Column("audit_status", String(40), nullable=False, server_default="not_started", quote=True),
        Column("audit_result", JSON, nullable=True, quote=True),
        Column("audit_proposal", JSON, nullable=True, quote=True),
        Column("audit_base_revision", Integer, nullable=True, quote=True),
        Column("audit_base_hash", String(80), nullable=True, quote=True),
        Column("audit_created_at", DateTime(timezone=True), nullable=True, quote=True),
        Column("audit_applied_at", DateTime(timezone=True), nullable=True, quote=True),
    )


def _resume_draft_addition_statements(dialect, existing_columns: set[str]) -> list[str]:
    table_name = dialect.identifier_preparer.quote_identifier(ResumeDraft.__tablename__)
    return [
        f"ALTER TABLE {table_name} ADD COLUMN {CreateColumn(column).compile(dialect=dialect)}"
        for column in _resume_draft_migration_columns()
        if column.name not in existing_columns
    ]


def _resume_draft_pdf_backfill_statement():
    migration_table = table(
        quoted_name(ResumeDraft.__tablename__, quote=True),
        column(quoted_name("status", quote=True), String(60)),
        column(quoted_name("pdf_stale", quote=True), Boolean),
        column(quoted_name("pdf_path", quote=True), Text),
        column(quoted_name("resume_revision", quote=True), Integer),
        column(quoted_name("pdf_revision", quote=True), Integer),
        column(quoted_name("pdf_generated_at", quote=True), DateTime(timezone=True)),
        column(quoted_name("updated_at", quote=True), DateTime(timezone=True)),
    )
    return (
        update(migration_table)
        .where(
            migration_table.c.status.in_(("pdf_ready", "applied")),
            migration_table.c.pdf_stale.is_(False),
            migration_table.c.pdf_path.is_not(None),
            (
                migration_table.c.pdf_revision.is_(None)
                | migration_table.c.pdf_generated_at.is_(None)
            ),
        )
        .values(
            pdf_revision=migration_table.c.resume_revision,
            pdf_generated_at=migration_table.c.updated_at,
        )
    )


def _apply_resume_draft_migration(connection, existing_columns: set[str]) -> None:
    for statement in _resume_draft_addition_statements(connection.dialect, existing_columns):
        connection.execute(text(statement))
    connection.execute(_resume_draft_pdf_backfill_statement())


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if ResumeDraft.__tablename__ not in inspector.get_table_names():
        return
    columns = {
        column["name"]
        for column in inspector.get_columns(ResumeDraft.__tablename__)
    }
    with engine.begin() as connection:
        _apply_resume_draft_migration(connection, columns)


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

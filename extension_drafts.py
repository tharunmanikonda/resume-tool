"""Persistence helpers for LinkedIn extension resume drafts."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse, urlunparse

from sqlalchemy import delete, select

from database import ResumeDraft, ResumeDraftTask, session_scope, utcnow


RUNNING_DRAFT_STATUSES = {"analyzing", "generating_core", "generating_experience", "reviewing"}
EDITABLE_DRAFT_STATUSES = {"queued", "failed", "ready", "pdf_ready", "skipped"}


def clean_text(value) -> str:
    return str(value or "").strip()


def description_hash(value: str) -> str:
    normalized = re.sub(r"\s+", " ", clean_text(value))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def linkedin_job_id(value: str, url: str = "") -> str:
    explicit = clean_text(value)
    if explicit:
        return explicit
    parsed = urlparse(clean_text(url))
    path_match = re.search(r"/jobs/view/(\d+)", parsed.path)
    if path_match:
        return path_match.group(1)
    return clean_text(parse_qs(parsed.query).get("currentJobId", [""])[0])


def canonical_job_url(value: str, external_job_id: str = "") -> str:
    parsed = urlparse(clean_text(value))
    if external_job_id:
        return f"https://www.linkedin.com/jobs/view/{external_job_id}/"
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") + "/", "", "", ""))


def normalize_context(payload: dict) -> dict:
    source = clean_text(payload.get("source")) or "linkedin"
    raw_url = clean_text(payload.get("url") or payload.get("canonical_url"))
    external_id = linkedin_job_id(payload.get("external_job_id"), raw_url)
    url = canonical_job_url(raw_url, external_id)
    company = clean_text(payload.get("company_name"))
    title = clean_text(payload.get("role_title") or payload.get("title"))
    description = clean_text(payload.get("job_description") or payload.get("description"))
    digest = description_hash(description)
    fallback = "|".join((company.lower(), title.lower(), digest))
    source_key = f"{source}:{external_id or url or hashlib.sha256(fallback.encode('utf-8')).hexdigest()[:24]}"
    return {
        "source": source,
        "external_job_id": external_id,
        "source_key": source_key,
        "canonical_url": url,
        "company_name": company,
        "role_title": title,
        "location": clean_text(payload.get("location")),
        "job_description": description,
        "description_hash": digest,
        "source_metadata": payload.get("source_metadata") if isinstance(payload.get("source_metadata"), dict) else {},
    }


def validate_context(context: dict) -> list[str]:
    missing = []
    for key, label in (("company_name", "Company"), ("role_title", "Role title"), ("job_description", "Job description")):
        if not clean_text(context.get(key)):
            missing.append(f"{label} is required.")
    if context.get("job_description") and len(context["job_description"]) < 120:
        missing.append("The extracted job description is incomplete.")
    return missing


def serialize_draft(row: ResumeDraft, *, include_content: bool = True) -> dict:
    payload = {
        "id": row.id,
        "source": row.source,
        "external_job_id": row.external_job_id or "",
        "source_key": row.source_key,
        "canonical_url": row.canonical_url or "",
        "company_name": row.company_name,
        "role_title": row.role_title,
        "location": row.location or "",
        "description_hash": row.description_hash,
        "latest_description_hash": row.latest_description_hash or row.description_hash,
        "source_changed": bool(row.latest_description_hash and row.latest_description_hash != row.description_hash),
        "source_metadata": row.source_metadata or {},
        "status": row.status,
        "stage": row.stage,
        "duplicate_decision": row.duplicate_decision or "",
        "identity_id": row.identity_id or "",
        "enabled_experience_keys": row.enabled_experience_keys or [],
        "analysis": row.analysis or {},
        "resume_snapshot": row.resume_snapshot or {},
        "pdf_path": row.pdf_path or "",
        "docx_path": row.docx_path or "",
        "output_dir": row.output_dir or "",
        "pdf_status_path": row.pdf_status_path or "",
        "pdf_stale": bool(row.pdf_stale),
        "resume_revision": int(row.resume_revision or 1),
        "pdf_revision": int(row.pdf_revision) if row.pdf_revision is not None else None,
        "pdf_generated_at": (
            row.pdf_generated_at if row.pdf_generated_at and row.pdf_generated_at.tzinfo else row.pdf_generated_at.replace(tzinfo=timezone.utc)
        ).isoformat() if row.pdf_generated_at else "",
        "application_id": row.application_id or "",
        "error_stage": row.error_stage or "",
        "error_message": row.error_message or "",
        "locked": row.status == "applied" or bool(row.application_id),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }
    if include_content:
        payload.update({
            "job_description": row.job_description,
            "resume_content": row.resume_content or "",
            "profile_snapshot": row.profile_snapshot or {},
            "contact_snapshot": row.contact_snapshot or {},
            "experience_history_snapshot": row.experience_history_snapshot or [],
            "title_summary": row.title_summary or {},
            "skills": row.skills or {},
            "experience_recent": row.experience_recent or {},
            "experience_older": row.experience_older or {},
        })
    return payload


class ExtensionDraftStore:
    def resolve(self, context_payload: dict) -> tuple[dict, dict | None]:
        context = normalize_context(context_payload)
        with session_scope() as db:
            row = db.scalars(
                select(ResumeDraft)
                .where(ResumeDraft.source_key == context["source_key"])
                .order_by(ResumeDraft.updated_at.desc())
            ).first()
            if row and context["description_hash"]:
                row.latest_description_hash = context["description_hash"]
                row.source_metadata = {**(row.source_metadata or {}), **context["source_metadata"]}
                db.flush()
            return context, serialize_draft(row) if row else None

    def create(self, context_payload: dict, snapshot: dict, duplicate_count: int) -> dict:
        context = normalize_context(context_payload)
        issues = validate_context(context)
        if issues:
            raise ValueError(" ".join(issues))
        with session_scope() as db:
            existing = db.scalars(
                select(ResumeDraft)
                .where(ResumeDraft.source_key == context["source_key"])
                .order_by(ResumeDraft.updated_at.desc())
            ).first()
            if existing and existing.status != "applied":
                return serialize_draft(existing)

            status = "duplicate_review" if duplicate_count else "queued"
            row = ResumeDraft(
                id="draft-" + uuid.uuid4().hex,
                **context,
                latest_description_hash=context["description_hash"],
                status=status,
                stage="duplicate_review" if duplicate_count else "waiting",
                identity_id=clean_text(snapshot.get("identity_id")),
                enabled_experience_keys=list(snapshot.get("enabled_experience_keys") or []),
                profile_snapshot=snapshot.get("profile_snapshot") or {},
                contact_snapshot=snapshot.get("contact_snapshot") or {},
                experience_history_snapshot=list(snapshot.get("experience_history_snapshot") or []),
            )
            db.add(row)
            db.flush()
            if status == "queued":
                self._add_task(db, row.id)
            return serialize_draft(row)

    @staticmethod
    def _add_task(db, draft_id: str) -> ResumeDraftTask:
        task = ResumeDraftTask(id="task-" + uuid.uuid4().hex, draft_id=draft_id, status="queued", stage="waiting")
        db.add(task)
        return task

    def list(self, limit: int = 12) -> list[dict]:
        with session_scope() as db:
            rows = db.scalars(select(ResumeDraft).order_by(ResumeDraft.updated_at.desc()).limit(max(1, min(limit, 50)))).all()
            return [serialize_draft(row, include_content=False) for row in rows]

    def get(self, draft_id: str) -> dict | None:
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            return serialize_draft(row) if row else None

    def update(self, draft_id: str, values: dict, *, invalidate_pdf: bool = False) -> dict:
        allowed = {
            "company_name", "role_title", "identity_id", "enabled_experience_keys", "resume_content",
            "resume_snapshot", "title_summary", "skills", "analysis", "experience_recent", "experience_older",
            "status", "stage", "duplicate_decision", "pdf_path", "docx_path", "output_dir", "pdf_status_path",
            "pdf_stale", "resume_revision", "pdf_revision", "pdf_generated_at", "application_id", "error_stage", "error_message", "job_description", "description_hash",
            "latest_description_hash", "contact_snapshot", "experience_history_snapshot",
        }
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if row.status == "applied" and any(key not in {"latest_description_hash"} for key in values):
                raise ValueError("Applied resume drafts are locked.")
            changed = {
                key: value for key, value in values.items()
                if key in allowed and getattr(row, key) != value
            }
            for key, value in changed.items():
                setattr(row, key, value)
            content_changed = invalidate_pdf and bool(changed)
            if content_changed:
                row.resume_revision = int(row.resume_revision or 1) + 1
            if content_changed and row.pdf_path:
                row.pdf_stale = True
                if row.status == "pdf_ready":
                    row.status = "ready"
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def delete(self, draft_id: str) -> None:
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if row.status == "applied" or row.application_id:
                raise ValueError("Applied resume drafts cannot be deleted.")
            db.execute(delete(ResumeDraftTask).where(ResumeDraftTask.draft_id == draft_id))
            db.delete(row)

    def decide_duplicate(self, draft_id: str, decision: str) -> dict:
        normalized = clean_text(decision).lower()
        if normalized not in {"continue", "skip"}:
            raise ValueError("Decision must be continue or skip.")
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row or row.status != "duplicate_review":
                raise ValueError("This draft is not waiting for a duplicate decision.")
            row.duplicate_decision = normalized
            row.error_message = None
            if normalized == "skip":
                row.status = "skipped"
                row.stage = "complete"
            else:
                row.status = "queued"
                row.stage = "waiting"
                self._add_task(db, row.id)
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def retry(self, draft_id: str) -> dict:
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row or row.status != "failed":
                raise ValueError("Only failed drafts can be retried.")
            active = db.scalars(select(ResumeDraftTask).where(
                ResumeDraftTask.draft_id == draft_id,
                ResumeDraftTask.status.in_(("queued", "running")),
            )).first()
            if not active:
                self._add_task(db, row.id)
            row.status = "queued"
            row.error_message = None
            row.error_stage = None
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def queue(self, draft_id: str) -> dict:
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if row.status in {"queued", *RUNNING_DRAFT_STATUSES, "ready", "pdf_ready", "pdf_generating"}:
                return serialize_draft(row)
            if row.status == "applied":
                raise ValueError("Applied resume drafts are locked.")
            if row.status == "duplicate_review":
                return serialize_draft(row)
            active = db.scalars(select(ResumeDraftTask).where(
                ResumeDraftTask.draft_id == draft_id,
                ResumeDraftTask.status.in_(("queued", "running")),
            )).first()
            if not active:
                self._add_task(db, row.id)
            row.status = "queued"
            row.stage = row.stage if row.stage not in {"complete", "waiting"} else "waiting"
            row.error_stage = None
            row.error_message = None
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def regenerate(self, draft_id: str, context_payload: dict | None = None) -> dict:
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if row.status == "applied" or row.application_id:
                raise ValueError("Applied drafts require a new draft revision.")
            if context_payload:
                context = normalize_context(context_payload)
                issues = validate_context(context)
                if issues:
                    raise ValueError(" ".join(issues))
                row.company_name = context["company_name"]
                row.role_title = context["role_title"]
                row.location = context["location"]
                row.canonical_url = context["canonical_url"]
                row.job_description = context["job_description"]
                row.description_hash = context["description_hash"]
                row.latest_description_hash = context["description_hash"]
                row.source_metadata = context["source_metadata"]
            row.analysis = {}
            row.title_summary = {}
            row.skills = {}
            row.experience_recent = {}
            row.experience_older = {}
            row.resume_content = None
            row.resume_snapshot = {}
            row.pdf_path = None
            row.docx_path = None
            row.output_dir = None
            row.pdf_status_path = None
            row.pdf_stale = False
            row.resume_revision = int(row.resume_revision or 1) + 1
            row.pdf_revision = None
            row.pdf_generated_at = None
            row.status = "queued"
            row.stage = "waiting"
            row.error_stage = None
            row.error_message = None
            db.execute(delete(ResumeDraftTask).where(
                ResumeDraftTask.draft_id == draft_id,
                ResumeDraftTask.status.in_(("queued", "failed", "completed")),
            ))
            self._add_task(db, row.id)
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def recover_interrupted(self) -> None:
        with session_scope() as db:
            tasks = db.scalars(select(ResumeDraftTask).where(ResumeDraftTask.status == "running")).all()
            for task in tasks:
                task.status = "queued"
                task.started_at = None
                row = db.get(ResumeDraft, task.draft_id)
                if row and row.status in RUNNING_DRAFT_STATUSES:
                    row.status = "queued"
                    row.stage = task.stage or row.stage

    def has_duplicate_review(self) -> bool:
        with session_scope() as db:
            return db.scalars(select(ResumeDraft.id).where(ResumeDraft.status == "duplicate_review").limit(1)).first() is not None

    def next_task(self) -> dict | None:
        with session_scope() as db:
            task = db.scalars(
                select(ResumeDraftTask)
                .where(ResumeDraftTask.status == "queued")
                .order_by(ResumeDraftTask.requested_at.asc())
            ).first()
            if not task:
                return None
            task.status = "running"
            task.attempt_count += 1
            task.started_at = utcnow()
            row = db.get(ResumeDraft, task.draft_id)
            if not row:
                task.status = "failed"
                task.error_message = "Resume draft not found."
                return None
            db.flush()
            return {"task_id": task.id, "draft": serialize_draft(row), "stage": task.stage}

    def checkpoint(self, task_id: str, draft_id: str, stage: str, values: dict) -> dict:
        with session_scope() as db:
            task = db.get(ResumeDraftTask, task_id)
            row = db.get(ResumeDraft, draft_id)
            if not task or not row:
                raise KeyError("Draft task not found.")
            for key, value in values.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            row.stage = stage
            row.updated_at = utcnow()
            task.stage = stage
            db.flush()
            return serialize_draft(row)

    def complete_task(self, task_id: str, draft_id: str, values: dict) -> dict:
        with session_scope() as db:
            task = db.get(ResumeDraftTask, task_id)
            row = db.get(ResumeDraft, draft_id)
            if not task or not row:
                raise KeyError("Draft task not found.")
            for key, value in values.items():
                if hasattr(row, key):
                    setattr(row, key, value)
            row.status = "ready"
            row.stage = "complete"
            row.error_stage = None
            row.error_message = None
            row.updated_at = utcnow()
            task.status = "completed"
            task.stage = "complete"
            task.completed_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def fail_task(self, task_id: str, draft_id: str, stage: str, message: str) -> None:
        with session_scope() as db:
            task = db.get(ResumeDraftTask, task_id)
            row = db.get(ResumeDraft, draft_id)
            if task:
                task.status = "failed"
                task.stage = stage
                task.error_message = message
                task.completed_at = utcnow()
            if row:
                row.status = "failed"
                row.stage = stage
                row.error_stage = stage
                row.error_message = message
                row.updated_at = utcnow()

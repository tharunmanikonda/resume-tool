"""Persistence helpers for LinkedIn extension resume drafts."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse, urlunparse

from sqlalchemy import delete, select

from database import ResumeDraft, ResumeDraftTask, session_scope, utcnow


RUNNING_DRAFT_STATUSES = {"analyzing", "generating_core", "generating_experience", "reviewing"}
EDITABLE_DRAFT_STATUSES = {"queued", "failed", "ready", "pdf_ready", "skipped"}
UNRESOLVED_AUDIT_STATUSES = {"changes_suggested", "manual_attention"}
STALEABLE_AUDIT_STATUSES = {
    "approved", "changes_suggested", "manual_attention",
    "kept_current", "applied", "technical_failed",
}
RESUME_AFFECTING_FIELDS = {
    "company_name", "role_title", "identity_id", "enabled_experience_keys",
    "resume_content", "resume_snapshot", "title_summary", "skills", "analysis",
    "experience_recent", "experience_older", "job_description", "description_hash",
    "contact_snapshot", "experience_history_snapshot",
}
RESUME_VERSION_NAMES = {"original", "luna_reviewed", "manual"}
RESUME_VERSION_FIELDS = (
    "title_summary",
    "skills",
    "experience_recent",
    "experience_older",
    "resume_content",
    "resume_snapshot",
)


class AuditStaleError(ValueError):
    pass


class ActiveDraftTaskError(ValueError):
    pass


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


def _iso_datetime(value: datetime | None) -> str:
    if not value:
        return ""
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.isoformat()


def _has_versionable_resume(row: ResumeDraft) -> bool:
    return bool(
        clean_text(row.resume_content)
        or row.title_summary
        or row.skills
        or row.experience_recent
        or row.experience_older
        or row.resume_snapshot
    )


def _resume_version_snapshot(
    row: ResumeDraft,
    *,
    created_at: datetime | None = None,
) -> dict:
    return {
        "title_summary": deepcopy(row.title_summary or {}),
        "skills": deepcopy(row.skills or {}),
        "experience_recent": deepcopy(row.experience_recent or {}),
        "experience_older": deepcopy(row.experience_older or {}),
        "resume_content": row.resume_content or "",
        "resume_snapshot": deepcopy(row.resume_snapshot or {}),
        "revision": int(row.resume_revision or 1),
        "created_at": _iso_datetime(created_at or utcnow()),
    }


def _save_resume_version(
    row: ResumeDraft,
    version_name: str,
    *,
    activate: bool = True,
    overwrite: bool = True,
) -> None:
    if version_name not in RESUME_VERSION_NAMES:
        raise ValueError(f"Unsupported resume version '{version_name}'.")
    versions = deepcopy(row.resume_versions) if isinstance(row.resume_versions, dict) else {}
    if overwrite or version_name not in versions:
        versions[version_name] = _resume_version_snapshot(row)
        row.resume_versions = versions
    if activate:
        row.active_resume_version = version_name


def _preserve_original_version(row: ResumeDraft) -> None:
    versions = row.resume_versions if isinstance(row.resume_versions, dict) else {}
    if "original" not in versions and _has_versionable_resume(row):
        _save_resume_version(row, "original", activate=False, overwrite=False)


def serialize_draft(row: ResumeDraft, *, include_content: bool = True) -> dict:
    audit_result = row.audit_result if isinstance(row.audit_result, dict) else row.audit_result
    audit_status = row.audit_status or "not_started"
    if audit_status == "failed":
        audit_status = "technical_failed"
    if (
        audit_status in {"changes_proposed", "blocked"}
        or (
            isinstance(audit_result, dict)
            and audit_result.get("decision")
            and str(audit_result.get("schema_version", "")) != "2"
        )
    ):
        audit_status = "stale"
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
        "resume_versions": deepcopy(row.resume_versions) if isinstance(row.resume_versions, dict) else {},
        "active_resume_version": row.active_resume_version or "",
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
        "audit_status": audit_status,
        "audit_result": audit_result,
        "audit_proposal": row.audit_proposal if audit_status == "changes_suggested" else None,
        "audit_base_revision": row.audit_base_revision,
        "audit_base_hash": row.audit_base_hash or "",
        "audit_created_at": (
            row.audit_created_at if row.audit_created_at and row.audit_created_at.tzinfo else row.audit_created_at.replace(tzinfo=timezone.utc)
        ).isoformat() if row.audit_created_at else "",
        "audit_applied_at": (
            row.audit_applied_at if row.audit_applied_at and row.audit_applied_at.tzinfo else row.audit_applied_at.replace(tzinfo=timezone.utc)
        ).isoformat() if row.audit_applied_at else "",
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
    _task_lock = threading.RLock()

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

    @staticmethod
    def _active_task(db, draft_id: str) -> ResumeDraftTask | None:
        return db.scalars(select(ResumeDraftTask).where(
            ResumeDraftTask.draft_id == draft_id,
            ResumeDraftTask.status.in_(("queued", "running")),
        )).first()

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
            "audit_status", "audit_result", "audit_proposal", "audit_base_revision",
            "audit_base_hash", "audit_created_at", "audit_applied_at",
        }
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if (row.status == "applied" or row.application_id) and any(key not in {"latest_description_hash"} for key in values):
                raise ValueError("Applied resume drafts are locked.")
            changed = {
                key: value for key, value in values.items()
                if key in allowed and getattr(row, key) != value
            }
            manual_resume_changed = (
                invalidate_pdf
                and bool(set(changed) & RESUME_AFFECTING_FIELDS)
            )
            if manual_resume_changed:
                _preserve_original_version(row)
            for key, value in changed.items():
                setattr(row, key, value)
            content_changed = invalidate_pdf and bool(changed)
            audit_invalidated = invalidate_pdf and bool(set(changed) & RESUME_AFFECTING_FIELDS)
            if audit_invalidated and row.audit_status in STALEABLE_AUDIT_STATUSES:
                row.audit_status = "kept_current"
                row.audit_proposal = None
            if content_changed:
                row.resume_revision = int(row.resume_revision or 1) + 1
            if manual_resume_changed and _has_versionable_resume(row):
                _save_resume_version(row, "manual")
            if content_changed and row.pdf_path:
                row.pdf_stale = True
                if row.status == "pdf_ready":
                    row.status = "ready"
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def materialize_pdf(self, draft_id: str, values: dict) -> dict:
        allowed = {
            "status", "stage", "resume_snapshot", "docx_path", "pdf_path", "output_dir",
            "pdf_status_path", "pdf_stale", "pdf_revision", "pdf_generated_at",
            "error_stage", "error_message",
        }
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if row.status == "applied" or row.application_id:
                raise ValueError("Applied resume drafts are locked.")
            for key, value in values.items():
                if key in allowed:
                    setattr(row, key, value)
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def start_audit(self, draft_id: str) -> dict:
        run_token = uuid.uuid4().hex
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if row.status == "applied" or row.application_id:
                raise ValueError("Applied resume drafts are locked.")
            if row.status not in {"ready", "pdf_ready"} or not row.resume_content:
                raise ValueError("The resume must finish generating before review.")
            row.audit_status = "running"
            row.audit_result = {"run_token": run_token}
            row.audit_proposal = None
            row.audit_base_revision = int(row.resume_revision or 1)
            row.audit_base_hash = None
            row.audit_created_at = utcnow()
            row.audit_applied_at = None
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    @staticmethod
    def _require_current_audit_run(row: ResumeDraft, run_token: str) -> None:
        active_result = row.audit_result if isinstance(row.audit_result, dict) else {}
        active_token = clean_text(active_result.get("run_token"))
        if row.audit_status != "running" or not active_token or active_token != clean_text(run_token):
            raise AuditStaleError("This quality review run is no longer current.")

    def save_audit_result(
        self,
        draft_id: str,
        result: dict,
        base_hash: str,
        base_revision: int,
        run_token: str,
    ) -> dict:
        decision = clean_text(result.get("decision"))
        if decision not in {"approved", "changes_suggested", "manual_attention"}:
            raise ValueError("Invalid audit decision.")
        stale = False
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            self._require_current_audit_run(row, run_token)
            if int(row.resume_revision or 1) != int(base_revision):
                row.audit_status = "stale"
                row.audit_proposal = None
                stale = True
            else:
                row.audit_status = decision
                row.audit_result = result
                row.audit_proposal = result.get("changes") if decision == "changes_suggested" else None
                row.audit_base_revision = int(base_revision)
                row.audit_base_hash = clean_text(base_hash)
                row.audit_created_at = utcnow()
                row.audit_applied_at = None
                _preserve_original_version(row)
                if decision == "approved" and _has_versionable_resume(row):
                    _save_resume_version(row, "luna_reviewed")
                row.updated_at = utcnow()
            db.flush()
            payload = serialize_draft(row)
        if stale:
            raise AuditStaleError("The resume changed while the review was running.")
        return payload

    def mark_audit_failure(
        self,
        draft_id: str,
        message: str,
        run_token: str,
        *,
        metadata: dict | None = None,
    ) -> dict:
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            self._require_current_audit_run(row, run_token)
            row.audit_status = "technical_failed"
            row.audit_result = {
                "schema_version": "2",
                "decision": "technical_failed",
                "error": clean_text(message),
                "error_kind": "quality_audit",
                **(metadata or {}),
            }
            row.audit_proposal = None
            row.audit_created_at = utcnow()
            row.audit_applied_at = None
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def keep_current_audit(self, draft_id: str) -> dict:
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if row.status == "applied" or row.application_id:
                raise ValueError("Applied resume drafts are locked.")
            if row.audit_status != "changes_suggested":
                raise ValueError("There is no unresolved audit to keep.")
            row.audit_status = "kept_current"
            row.audit_proposal = None
            row.updated_at = utcnow()
            db.flush()
            return serialize_draft(row)

    def apply_audit_proposal(
        self,
        draft_id: str,
        *,
        expected_revision: int,
        expected_hash: str,
        current_hash: str,
        values: dict,
    ) -> dict:
        return self.resolve_audit_decisions(
            draft_id,
            expected_revision=expected_revision,
            expected_hash=expected_hash,
            current_hash=current_hash,
            values=values,
        )

    def resolve_audit_decisions(
        self,
        draft_id: str,
        *,
        expected_revision: int,
        expected_hash: str,
        current_hash: str,
        values: dict | None,
        decisions: dict | None = None,
    ) -> dict:
        stale = False
        with session_scope() as db:
            row = db.get(ResumeDraft, draft_id)
            if not row:
                raise KeyError("Resume draft not found.")
            if row.status == "applied" or row.application_id:
                raise ValueError("Applied resume drafts are locked.")
            if (
                row.audit_status != "changes_suggested"
                or int(row.resume_revision or 1) != int(expected_revision)
                or int(row.audit_base_revision or 0) != int(expected_revision)
                or clean_text(row.audit_base_hash) != clean_text(expected_hash)
                or clean_text(current_hash) != clean_text(expected_hash)
            ):
                row.audit_status = "stale"
                row.audit_proposal = None
                stale = True
            elif values is None:
                row.audit_status = "kept_current"
                row.audit_proposal = None
                if isinstance(row.audit_result, dict):
                    row.audit_result = {
                        **row.audit_result,
                        "accepted_change_ids": [],
                        "rejected_change_ids": sorted((decisions or {}).keys()),
                    }
                row.updated_at = utcnow()
            else:
                _preserve_original_version(row)
                for key in (
                    "title_summary", "skills", "experience_recent", "experience_older",
                    "resume_content", "resume_snapshot",
                ):
                    setattr(row, key, values[key])
                row.resume_revision = int(row.resume_revision or 1) + 1
                _save_resume_version(row, "luna_reviewed")
                if row.pdf_path:
                    row.pdf_stale = True
                    if row.status == "pdf_ready":
                        row.status = "ready"
                row.audit_status = "applied"
                row.audit_proposal = None
                if isinstance(row.audit_result, dict):
                    row.audit_result = {
                        **row.audit_result,
                        "accepted_change_ids": sorted(
                            change_id for change_id, decision in (decisions or {}).items()
                            if decision == "accept"
                        ),
                        "rejected_change_ids": sorted(
                            change_id for change_id, decision in (decisions or {}).items()
                            if decision == "reject"
                        ),
                    }
                row.audit_applied_at = utcnow()
                row.updated_at = utcnow()
            db.flush()
            payload = serialize_draft(row)
        if stale:
            raise AuditStaleError("The resume changed after the quality audit was generated.")
        return payload

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
        with self._task_lock:
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
                    active = self._active_task(db, draft_id)
                    if not active:
                        self._add_task(db, row.id)
                    row.status = "queued"
                    row.stage = "waiting"
                row.updated_at = utcnow()
                db.flush()
                return serialize_draft(row)

    def retry(self, draft_id: str) -> dict:
        with self._task_lock:
            with session_scope() as db:
                row = db.get(ResumeDraft, draft_id)
                if not row or row.status != "failed":
                    raise ValueError("Only failed drafts can be retried.")
                active = self._active_task(db, draft_id)
                if not active:
                    self._add_task(db, row.id)
                row.status = "queued"
                row.error_message = None
                row.error_stage = None
                row.updated_at = utcnow()
                db.flush()
                return serialize_draft(row)

    def queue(self, draft_id: str) -> dict:
        with self._task_lock:
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
                active = self._active_task(db, draft_id)
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
        with self._task_lock:
            with session_scope() as db:
                row = db.get(ResumeDraft, draft_id)
                if not row:
                    raise KeyError("Resume draft not found.")
                if row.status == "applied" or row.application_id:
                    raise ValueError("Applied drafts require a new draft revision.")
                if self._active_task(db, draft_id):
                    raise ActiveDraftTaskError("This resume draft is already queued or generating. Wait for it to finish before regenerating.")
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
                row.resume_versions = {}
                row.active_resume_version = None
                row.pdf_path = None
                row.docx_path = None
                row.output_dir = None
                row.pdf_status_path = None
                row.pdf_stale = False
                row.resume_revision = int(row.resume_revision or 1) + 1
                row.pdf_revision = None
                row.pdf_generated_at = None
                row.audit_status = "not_started"
                row.audit_result = None
                row.audit_proposal = None
                row.audit_base_revision = None
                row.audit_base_hash = None
                row.audit_created_at = None
                row.audit_applied_at = None
                row.status = "queued"
                row.stage = "waiting"
                row.error_stage = None
                row.error_message = None
                db.execute(delete(ResumeDraftTask).where(
                    ResumeDraftTask.draft_id == draft_id,
                    ResumeDraftTask.status.in_(("failed", "completed")),
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
        with self._task_lock:
            with session_scope() as db:
                while True:
                    task = db.scalars(
                        select(ResumeDraftTask)
                        .where(ResumeDraftTask.status == "queued")
                        .order_by(ResumeDraftTask.requested_at.asc())
                    ).first()
                    if not task:
                        return None
                    running = db.scalars(select(ResumeDraftTask).where(
                        ResumeDraftTask.draft_id == task.draft_id,
                        ResumeDraftTask.status == "running",
                    )).first()
                    if running:
                        db.delete(task)
                        db.flush()
                        continue
                    db.execute(delete(ResumeDraftTask).where(
                        ResumeDraftTask.draft_id == task.draft_id,
                        ResumeDraftTask.status == "queued",
                        ResumeDraftTask.id != task.id,
                    ))
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
            _preserve_original_version(row)
            if _has_versionable_resume(row):
                versions = row.resume_versions if isinstance(row.resume_versions, dict) else {}
                if "original" in versions and not row.active_resume_version:
                    row.active_resume_version = "original"
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

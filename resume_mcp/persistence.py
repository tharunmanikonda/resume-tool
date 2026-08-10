"""Persistence for MCP orchestration state only."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from database import McpResumeWorkflow, session_scope, utcnow


def _serialize(row: McpResumeWorkflow) -> dict:
    return {
        "id": row.id,
        "poke_user_id": row.poke_user_id,
        "resume_draft_id": row.resume_draft_id or "",
        "status": row.status,
        "revision": int(row.revision or 1),
        "identity_id": row.identity_id or "",
        "job_description": row.job_description,
        "company_name": row.company_name or "",
        "role_title": row.role_title or "",
        "source_url": row.source_url or "",
        "pending_action": row.pending_action if isinstance(row.pending_action, dict) else None,
        "last_error": row.last_error if isinstance(row.last_error, dict) else None,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


class McpWorkflowStore:
    def create(
        self,
        *,
        poke_user_id: str,
        job_description: str,
        identity_id: str = "",
        company_name: str = "",
        role_title: str = "",
        source_url: str = "",
    ) -> dict:
        with session_scope() as db:
            row = McpResumeWorkflow(
                id="mcp-" + uuid.uuid4().hex,
                poke_user_id=poke_user_id,
                status="created",
                revision=1,
                identity_id=identity_id or None,
                job_description=job_description,
                company_name=company_name or None,
                role_title=role_title or None,
                source_url=source_url or None,
            )
            db.add(row)
            db.flush()
            return _serialize(row)

    def get_for_user(self, workflow_id: str, poke_user_id: str) -> dict | None:
        with session_scope() as db:
            row = db.scalars(select(McpResumeWorkflow).where(
                McpResumeWorkflow.id == workflow_id,
                McpResumeWorkflow.poke_user_id == poke_user_id,
            )).first()
            return _serialize(row) if row else None

    def update(self, workflow_id: str, poke_user_id: str, values: dict) -> dict:
        allowed = {
            "resume_draft_id", "status", "revision", "identity_id",
            "company_name", "role_title", "source_url", "pending_action", "last_error",
        }
        with session_scope() as db:
            row = db.scalars(select(McpResumeWorkflow).where(
                McpResumeWorkflow.id == workflow_id,
                McpResumeWorkflow.poke_user_id == poke_user_id,
            )).first()
            if not row:
                raise KeyError("Resume workflow not found.")
            for key, value in values.items():
                if key in allowed:
                    setattr(row, key, value)
            row.updated_at = utcnow()
            db.flush()
            return _serialize(row)

    def set_action(
        self,
        workflow_id: str,
        poke_user_id: str,
        *,
        action_type: str,
        question: str,
        choices: list[dict] | None = None,
        details: dict | None = None,
    ) -> dict:
        current = self.get_for_user(workflow_id, poke_user_id)
        if not current:
            raise KeyError("Resume workflow not found.")
        prior = current.get("pending_action") or {}
        action_id = (
            prior.get("action_id")
            if prior.get("type") == action_type and prior.get("action_id")
            else "action-" + uuid.uuid4().hex
        )
        action = {
            "action_id": action_id,
            "type": action_type,
            "question": question,
            "choices": choices or [],
            "details": details or {},
        }
        return self.update(workflow_id, poke_user_id, {
            "status": "action_required",
            "pending_action": action,
        })

    def clear_action(self, workflow_id: str, poke_user_id: str, *, status: str = "processing") -> dict:
        return self.update(workflow_id, poke_user_id, {
            "status": status,
            "pending_action": None,
            "last_error": None,
        })


workflows = McpWorkflowStore()

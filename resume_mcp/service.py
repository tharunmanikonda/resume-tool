"""MCP orchestration over the existing resume services."""

from __future__ import annotations

import copy
import os
import time
from typing import Iterable

os.environ.setdefault("RESUME_DISABLE_EXTENSION_WORKER", "1")
os.environ.setdefault("RESUME_PRESERVE_SESSION_PROFILE", "1")

import app as resume_app

from .contracts import ResumeChange
from .persistence import workflows
from .security import signed_download_urls


PROCESSING_STATUSES = {
    "queued", "analyzing", "generating_core", "generating_experience",
    "reviewing", "pdf_generating",
}
PREVIEW_AUDIT_STATUSES = {"approved", "applied", "kept_current"}


def identity_choices() -> list[dict]:
    return [
        {"value": item["id"], "label": item.get("label") or item["id"]}
        for item in resume_app.current_identity_profiles()
        if str(item.get("id", "")).strip()
    ]


def require_identity(identity_id: str) -> dict:
    normalized = str(identity_id or "").strip().lower()
    for identity in resume_app.current_identity_profiles():
        if str(identity.get("id", "")).strip().lower() == normalized:
            return identity
    raise ValueError(f"Unknown identity '{identity_id}'. Select one of the available identities.")


def _action_response(workflow: dict) -> dict:
    return {
        "status": "action_required",
        "draft_id": workflow["id"],
        "revision": int(workflow.get("revision") or 1),
        "action": workflow.get("pending_action"),
    }


def _set_identity_action(workflow: dict, message: str = "Which contact identity should this resume use?") -> dict:
    choices = identity_choices()
    if not choices:
        updated = workflows.set_action(
            workflow["id"],
            workflow["poke_user_id"],
            action_type="configure_contact_identity",
            question=(
                "No contact identities are configured. Add an email and phone identity "
                "in the local Profile, then ask me to check again."
            ),
            choices=[{"value": "check_again", "label": "Check again"}],
        )
        return _action_response(updated)
    updated = workflows.set_action(
        workflow["id"],
        workflow["poke_user_id"],
        action_type="select_contact_identity",
        question=message,
        choices=choices,
    )
    return _action_response(updated)


def _set_profile_action(workflow: dict, issues: list[str] | None = None) -> dict:
    updated = workflows.set_action(
        workflow["id"],
        workflow["poke_user_id"],
        action_type="complete_profile_setup",
        question="Complete the permanent resume profile in the local app, then ask me to check again.",
        choices=[{"value": "check_again", "label": "Check again"}],
        details={"issues": issues or []},
    )
    return _action_response(updated)


def _create_linked_draft(workflow: dict, identity_id: str) -> dict:
    require_identity(identity_id)
    snapshot = resume_app.extension_profile_snapshot(identity_id, None)
    duplicate_count = 0
    if workflow.get("company_name"):
        duplicate_count = int(
            resume_app.tracker_company_history(workflow["company_name"]).get("count", 0)
        )
    draft = resume_app.extension_drafts.create_mcp(
        {
            "job_description": workflow["job_description"],
            "company_name": workflow.get("company_name", ""),
            "role_title": workflow.get("role_title", ""),
            "url": workflow.get("source_url", ""),
            "source_metadata": {"poke_user_id": workflow["poke_user_id"]},
        },
        snapshot,
        workflow["id"],
        duplicate_count,
    )
    return workflows.update(workflow["id"], workflow["poke_user_id"], {
        "resume_draft_id": draft["id"],
        "identity_id": identity_id,
        "revision": int(draft.get("resume_revision") or 1),
        "status": "action_required" if draft["status"] == "duplicate_review" else "processing",
        "pending_action": None,
    })


def start_resume_generation(
    *,
    poke_user_id: str,
    job_description: str,
    identity_id: str = "",
    company_name: str = "",
    role_title: str = "",
    source_url: str = "",
) -> dict:
    workflow = workflows.create(
        poke_user_id=poke_user_id,
        job_description=job_description.strip(),
        identity_id=identity_id.strip(),
        company_name=company_name.strip(),
        role_title=role_title.strip(),
        source_url=source_url.strip(),
    )
    profile_issues = resume_app.validate_profile_payload(resume_app.current_profile())
    if not resume_app.has_permanent_profile_doc() or profile_issues:
        return _set_profile_action(workflow, profile_issues)

    choices = identity_choices()
    if identity_id:
        try:
            require_identity(identity_id)
        except ValueError:
            return _set_identity_action(workflow, f"Identity '{identity_id}' is not available. Which identity should be used?")
    elif len(choices) == 1:
        identity_id = choices[0]["value"]
    else:
        return _set_identity_action(workflow)

    workflow = _create_linked_draft(workflow, identity_id)
    return get_resume_status(poke_user_id=poke_user_id, workflow_id=workflow["id"])


def _sync_workflow(workflow: dict, draft: dict, status: str) -> dict:
    values = {
        "status": status,
        "revision": int(draft.get("resume_revision") or 1),
        "company_name": draft.get("company_name") or workflow.get("company_name") or None,
        "role_title": draft.get("role_title") or workflow.get("role_title") or None,
    }
    return workflows.update(workflow["id"], workflow["poke_user_id"], values)


def _draft_response(workflow: dict, draft: dict, *, include_review: bool = False) -> dict:
    response = {
        "status": workflow["status"],
        "draft_id": workflow["id"],
        "revision": int(draft.get("resume_revision") or 1),
        "stage": draft.get("stage", ""),
        "company_name": draft.get("company_name", ""),
        "role_title": draft.get("role_title", ""),
        "audit_status": draft.get("audit_status", "not_started"),
    }
    if workflow["status"] in {"preview_ready", "completed"}:
        response.update({
            "resume_markdown": draft.get("resume_content", ""),
            "preview": draft.get("preview") or draft.get("resume_snapshot") or {},
        })
    if include_review:
        response["detailed_review"] = draft.get("audit_result")
    elif isinstance(draft.get("audit_result"), dict):
        audit = draft["audit_result"]
        response["review"] = {
            key: audit.get(key)
            for key in ("decision", "overall_score", "review_summary", "scores")
            if key in audit
        }
    return response


def _stale_revision_response(workflow: dict, draft: dict, message: str) -> dict:
    current_revision = int(draft.get("resume_revision") or 1)
    updated = workflows.set_action(
        workflow["id"],
        workflow["poke_user_id"],
        action_type="refresh_resume_revision",
        question=message,
        choices=[{"value": "refresh", "label": "Use latest revision"}],
        details={"current_revision": current_revision},
    )
    response = _action_response(updated)
    response.update({
        "revision": current_revision,
        "resume_markdown": draft.get("resume_content", ""),
        "preview": draft.get("preview") or draft.get("resume_snapshot") or {},
    })
    return response


def _map_status(workflow: dict, draft: dict, *, include_review: bool = False) -> dict:
    user_id = workflow["poke_user_id"]
    draft_status = str(draft.get("status", ""))
    audit_status = str(draft.get("audit_status", "not_started"))

    if draft_status == "duplicate_review":
        history = resume_app.tracker_company_history(draft.get("company_name", ""))
        updated = workflows.set_action(
            workflow["id"], user_id,
            action_type="duplicate_application",
            question=f"You already have {history.get('count', 0)} application(s) for {draft.get('company_name')}. Continue or skip this resume?",
            choices=[
                {"value": "continue", "label": "Continue"},
                {"value": "skip", "label": "Skip"},
            ],
            details=history,
        )
        return _action_response(updated)

    if draft_status == "failed":
        error_stage = str(draft.get("error_stage", ""))
        error_details = {
            "stage": error_stage,
            "error": str(draft.get("error_message", "")),
        }
        if error_stage == "context_resolution":
            updated = workflows.set_action(
                workflow["id"], user_id,
                action_type="resolve_job_context",
                question="The JD analysis could not identify the company or advertised role. Provide both values to continue.",
                details={"error": draft.get("error_message", "")},
            )
        elif error_stage == "pdf_generation":
            updated = workflows.set_action(
                workflow["id"], user_id,
                action_type="retry_finalization",
                question="File generation failed. Retry PDF and DOCX creation for the same resume revision?",
                choices=[{"value": "retry", "label": "Retry files"}],
                details={"error": draft.get("error_message", "")},
            )
        else:
            updated = workflows.set_action(
                workflow["id"], user_id,
                action_type="retry_generation",
                question="Resume generation failed. Retry from the latest saved checkpoint?",
                choices=[{"value": "retry", "label": "Retry"}],
                details={"stage": error_stage, "error": draft.get("error_message", "")},
            )
        updated = workflows.update(workflow["id"], user_id, {"last_error": error_details})
        return _action_response(updated)

    if draft_status == "skipped":
        updated = _sync_workflow(workflow, draft, "skipped")
        return _draft_response(updated, draft, include_review=include_review)

    if draft_status in PROCESSING_STATUSES:
        persisted_status = "finalizing" if workflow.get("status") == "finalizing" else "processing"
        updated = _sync_workflow(workflow, draft, persisted_status)
        response = _draft_response(updated, draft, include_review=include_review)
        response["status"] = "processing"
        return response

    if audit_status == "technical_failed":
        audit_error = (draft.get("audit_result") or {}).get("error", "")
        updated = workflows.set_action(
            workflow["id"], user_id,
            action_type="retry_quality_review",
            question="The quality review failed technically. Retry only the review stage?",
            choices=[{"value": "retry", "label": "Retry review"}],
            details={"error": audit_error},
        )
        updated = workflows.update(workflow["id"], user_id, {
            "last_error": {"stage": "quality_audit", "error": audit_error},
        })
        return _action_response(updated)

    if audit_status == "manual_attention":
        updated = workflows.set_action(
            workflow["id"], user_id,
            action_type="manual_edit_required",
            question="Luna found a blocking issue that cannot be changed safely. Submit a structured edit, then check status again.",
            details={"review": draft.get("audit_result") or {}},
        )
        return _action_response(updated)

    if audit_status == "changes_suggested":
        updated = workflows.set_action(
            workflow["id"], user_id,
            action_type="review_decision",
            question="Luna suggested changes that were not auto-applied. Apply all changes or keep the current resume?",
            choices=[
                {"value": "apply_all", "label": "Apply all"},
                {"value": "keep_current", "label": "Keep current"},
            ],
        )
        return _action_response(updated)

    if draft_status in {"ready", "pdf_ready"} and audit_status in PREVIEW_AUDIT_STATUSES:
        completed = (
            workflow.get("status") == "finalizing"
            and draft_status == "pdf_ready"
            and not draft.get("pdf_stale")
            and int(draft.get("pdf_revision") or 0) == int(draft.get("resume_revision") or 1)
        )
        updated = _sync_workflow(workflow, draft, "completed" if completed else "preview_ready")
        if not completed:
            updated = workflows.update(updated["id"], user_id, {"pending_action": None})
        return _draft_response(updated, draft, include_review=include_review)

    updated = _sync_workflow(workflow, draft, "processing")
    return _draft_response(updated, draft, include_review=include_review)


def get_resume_status(
    *,
    poke_user_id: str,
    workflow_id: str,
    include_review: bool = False,
    wait_seconds: int = 0,
) -> dict:
    deadline = time.monotonic() + min(max(int(wait_seconds), 0), 20)
    while True:
        workflow = workflows.get_for_user(workflow_id, poke_user_id)
        if not workflow:
            raise KeyError("Resume workflow not found.")
        if not workflow.get("resume_draft_id"):
            return _action_response(workflow) if workflow.get("pending_action") else {
                "status": workflow["status"], "draft_id": workflow["id"], "revision": workflow["revision"]
            }
        raw_draft = resume_app.extension_drafts.get(workflow["resume_draft_id"])
        if not raw_draft:
            raise RuntimeError("The linked resume draft is unavailable.")
        draft = resume_app.extension_draft_payload(raw_draft)
        response = _map_status(workflow, draft, include_review=include_review)
        if response["status"] != "processing" or time.monotonic() >= deadline:
            return response
        time.sleep(0.5)


def _require_action(workflow: dict, action_id: str) -> dict:
    action = workflow.get("pending_action") or {}
    if not action or action.get("action_id") != action_id:
        raise ValueError("This action is stale or does not belong to the current workflow state.")
    return action


def continue_resume_action(
    *, poke_user_id: str, workflow_id: str, action_id: str, selection: str | dict
) -> dict:
    workflow = workflows.get_for_user(workflow_id, poke_user_id)
    if not workflow:
        raise KeyError("Resume workflow not found.")
    action = _require_action(workflow, action_id)
    action_type = action["type"]

    if action_type == "select_contact_identity":
        selected = str(selection).strip()
        try:
            require_identity(selected)
        except ValueError:
            return _set_identity_action(
                workflow,
                f"Identity '{selected}' is not available. Which identity should be used?",
            )
        _create_linked_draft(workflow, selected)
    elif action_type == "configure_contact_identity":
        if str(selection).strip() != "check_again":
            raise ValueError("Select check_again after configuring a contact identity.")
        choices = identity_choices()
        if not choices:
            return _set_identity_action(workflow)
        if len(choices) > 1:
            return _set_identity_action(workflow)
        _create_linked_draft(workflow, choices[0]["value"])
    elif action_type == "complete_profile_setup":
        if str(selection).strip() != "check_again":
            raise ValueError("Select check_again after completing the permanent profile.")
        profile_issues = resume_app.validate_profile_payload(resume_app.current_profile())
        if not resume_app.has_permanent_profile_doc() or profile_issues:
            return _set_profile_action(workflow, profile_issues)
        choices = identity_choices()
        if len(choices) != 1:
            return _set_identity_action(workflow)
        _create_linked_draft(workflow, choices[0]["value"])
    else:
        draft_id = workflow.get("resume_draft_id")
        if not draft_id:
            raise RuntimeError("The workflow has no linked resume draft.")
        if action_type == "duplicate_application":
            resume_app.extension_drafts.decide_duplicate(draft_id, str(selection))
        elif action_type == "resolve_job_context":
            if not isinstance(selection, dict):
                raise ValueError("Provide company_name and role_title as an object.")
            company = str(selection.get("company_name", "")).strip()
            role = str(selection.get("role_title", "")).strip()
            if not company or not role:
                raise ValueError("Both company_name and role_title are required.")
            draft = resume_app.extension_drafts.get(draft_id)
            metadata = {**(draft.get("source_metadata") or {}), "context_resolved": True}
            history = resume_app.tracker_company_history(company)
            metadata["duplicate_checked"] = True
            resume_app.extension_drafts.update(draft_id, {
                "company_name": company,
                "role_title": role,
                "source_metadata": metadata,
            })
            workflows.update(workflow_id, poke_user_id, {"company_name": company, "role_title": role})
            if int(history.get("count", 0)):
                resume_app.extension_drafts.update(draft_id, {
                    "status": "duplicate_review", "stage": "duplicate_review"
                })
            else:
                resume_app.extension_drafts.retry(draft_id)
        elif action_type == "retry_generation":
            if str(selection).strip() != "retry":
                raise ValueError("Select retry to continue.")
            resume_app.extension_drafts.retry(draft_id)
        elif action_type == "retry_quality_review":
            if str(selection).strip() != "retry":
                raise ValueError("Select retry to continue.")
            resume_app.extension_drafts.retry_audit_background(draft_id)
        elif action_type == "retry_finalization":
            if str(selection).strip() != "retry":
                raise ValueError("Select retry to continue.")
            draft = resume_app.extension_drafts.update(draft_id, {
                "status": "ready",
                "stage": "complete",
                "error_stage": "",
                "error_message": "",
            })
            workflows.update(workflow_id, poke_user_id, {
                "status": "finalizing", "pending_action": None,
            })
            return finalize_resume(
                poke_user_id=poke_user_id,
                workflow_id=workflow_id,
                base_revision=int(draft.get("resume_revision") or 1),
                confirmed=True,
            )
        elif action_type == "review_decision":
            decision = str(selection).strip()
            if decision == "apply_all":
                resume_app.apply_extension_draft_audit(draft_id)
            elif decision == "keep_current":
                resume_app.extension_drafts.keep_current_audit(draft_id)
            else:
                raise ValueError("Select apply_all or keep_current.")
        elif action_type == "manual_edit_required":
            raise ValueError("Submit the needed structured edit with update_resume_draft.")
        elif action_type == "refresh_resume_revision":
            if str(selection).strip() != "refresh":
                raise ValueError("Select refresh to use the latest resume revision.")
        elif action_type == "confirm_finalization":
            if str(selection).strip() != "confirm":
                raise ValueError("Select confirm to generate the files.")
            return finalize_resume(
                poke_user_id=poke_user_id,
                workflow_id=workflow_id,
                base_revision=int(workflow["revision"]),
                confirmed=True,
            )
        else:
            raise ValueError(f"Unsupported pending action '{action_type}'.")
        workflows.clear_action(workflow_id, poke_user_id)
    return get_resume_status(poke_user_id=poke_user_id, workflow_id=workflow_id)


def _experience_map(draft: dict) -> dict[str, dict]:
    result = {}
    result.update(copy.deepcopy((draft.get("experience_recent") or {}).get("experience") or {}))
    result.update(copy.deepcopy((draft.get("experience_older") or {}).get("experience") or {}))
    return result


def _skills_text(skills: list[dict]) -> str:
    return "\n".join(
        f"{item['category']}: {', '.join(item.get('items') or [])}"
        for item in skills
    )


def apply_structured_changes(
    *, poke_user_id: str, workflow_id: str, base_revision: int, changes: Iterable[ResumeChange]
) -> dict:
    workflow = workflows.get_for_user(workflow_id, poke_user_id)
    if not workflow or not workflow.get("resume_draft_id"):
        raise KeyError("Resume workflow not found.")
    draft = resume_app.extension_drafts.get(workflow["resume_draft_id"])
    if not draft:
        raise KeyError("Resume draft not found.")
    if draft.get("status") not in {"ready", "pdf_ready"} or not str(draft.get("resume_content", "")).strip():
        raise ValueError("Wait for resume generation to finish before applying edits.")
    if int(draft.get("resume_revision") or 1) != int(base_revision):
        return _stale_revision_response(
            workflow,
            draft,
            f"The resume changed. Expected revision {base_revision}, current revision is {draft.get('resume_revision')}. Review the latest preview and resubmit the edits.",
        )

    title = str((draft.get("title_summary") or {}).get("updated_title", "")).strip()
    summary = str((draft.get("title_summary") or {}).get("updated_summary", "")).strip()
    skills = copy.deepcopy((draft.get("skills") or {}).get("updated_skills") or [])
    experience = _experience_map(draft)
    enabled = list(draft.get("enabled_experience_keys") or [])
    changed_roles: set[str] = set()
    applied_changes: list[dict] = []

    def require_role(key: str) -> dict:
        if key not in experience:
            raise ValueError(f"Role '{key}' is not available in this draft.")
        return experience[key]

    for change in changes:
        item = change.model_dump()
        operation = item["operation"]
        if operation == "replace_resume_title":
            title = item["new_text"]
        elif operation == "replace_summary":
            summary = item["new_text"]
        elif operation == "replace_experience_title":
            require_role(item["role_key"])["title"] = item["new_text"]
            changed_roles.add(item["role_key"])
        elif operation in {"replace_bullet", "remove_bullet", "move_bullet"}:
            role = require_role(item["role_key"])
            bullets = list(role.get("bullets") or [])
            index = item["bullet_number"] - 1
            if index >= len(bullets):
                raise ValueError(f"Bullet {item['bullet_number']} does not exist for role '{item['role_key']}'.")
            if operation in {"replace_bullet", "remove_bullet"} and bullets[index].strip() != item["expected_text"].strip():
                return _stale_revision_response(
                    workflow,
                    draft,
                    f"Bullet {item['bullet_number']} for role '{item['role_key']}' changed before this edit was applied. Review the latest preview and resubmit the edit.",
                )
            if operation == "replace_bullet":
                bullets[index] = item["new_text"]
            elif operation == "remove_bullet":
                bullets.pop(index)
                if not bullets:
                    raise ValueError("An enabled experience must keep at least one bullet.")
            else:
                bullet = bullets.pop(index)
                target = min(item["new_position"] - 1, len(bullets))
                bullets.insert(target, bullet)
            role["bullets"] = bullets
            changed_roles.add(item["role_key"])
        elif operation == "add_bullet":
            role = require_role(item["role_key"])
            bullets = list(role.get("bullets") or [])
            if item["position"] > len(bullets) + 1:
                raise ValueError("New bullet position is outside the role's bullet list.")
            bullets.insert(item["position"] - 1, item["new_text"])
            role["bullets"] = bullets
            changed_roles.add(item["role_key"])
        elif operation in {"add_skill", "remove_skill", "replace_skill_category"}:
            category_index = next(
                (i for i, entry in enumerate(skills) if str(entry.get("category", "")).casefold() == item["category"].casefold()),
                None,
            )
            if operation == "add_skill":
                if category_index is None:
                    skills.append({"category": item["category"], "items": [item["skill"]]})
                elif item["skill"].casefold() not in {str(value).casefold() for value in skills[category_index].get("items", [])}:
                    skills[category_index].setdefault("items", []).append(item["skill"])
            else:
                if category_index is None:
                    raise ValueError(f"Skills category '{item['category']}' does not exist.")
                if operation == "replace_skill_category":
                    skills[category_index]["category"] = item["new_category"]
                else:
                    original = list(skills[category_index].get("items") or [])
                    remaining = [value for value in original if str(value).casefold() != item["skill"].casefold()]
                    if len(remaining) == len(original):
                        raise ValueError(f"Skill '{item['skill']}' was not found in '{item['category']}'.")
                    if remaining:
                        skills[category_index]["items"] = remaining
                    else:
                        skills.pop(category_index)
        elif operation == "set_experience_enabled":
            key = item["role_key"]
            if key not in {entry.get("key") for entry in draft.get("experience_history_snapshot", [])}:
                raise ValueError(f"Unknown experience role '{key}'.")
            if item["enabled"] and key not in enabled:
                enabled.append(key)
            elif not item["enabled"] and key in enabled:
                enabled.remove(key)
            if not enabled:
                raise ValueError("Keep at least one complete experience role enabled.")
        applied_changes.append(item)

    quick_edits = {"title": title, "summary": summary, "skills_text": _skills_text(skills)}
    if changed_roles:
        quick_edits["experience"] = [
            {
                "key": key,
                "title": experience[key].get("title", ""),
                "bullets": experience[key].get("bullets", []),
            }
            for key in changed_roles
        ]
    updated = resume_app.update_extension_draft_service(
        draft["id"],
        {"enabled_experience_keys": enabled, "quick_edits": quick_edits},
        expected_revision=base_revision,
    )
    workflows.update(workflow_id, poke_user_id, {
        "revision": int(updated.get("resume_revision") or 1),
        "status": "preview_ready",
        "pending_action": None,
    })
    return {
        "status": "preview_ready",
        "draft_id": workflow_id,
        "revision": int(updated.get("resume_revision") or 1),
        "applied_changes": applied_changes,
        "resume_markdown": updated.get("resume_content", ""),
        "preview": updated.get("preview") or updated.get("resume_snapshot") or {},
        "pdf_invalidated": True,
    }


def finalize_resume(
    *, poke_user_id: str, workflow_id: str, base_revision: int, confirmed: bool
) -> dict:
    workflow = workflows.get_for_user(workflow_id, poke_user_id)
    if not workflow or not workflow.get("resume_draft_id"):
        raise KeyError("Resume workflow not found.")
    draft = resume_app.extension_draft_payload(
        resume_app.extension_drafts.get(workflow["resume_draft_id"])
    )
    if int(draft.get("resume_revision") or 1) != int(base_revision):
        return _stale_revision_response(
            workflow,
            draft,
            f"The resume changed. Expected revision {base_revision}, current revision is {draft.get('resume_revision')}. Review the latest preview before generating files.",
        )
    if draft.get("status") not in {"ready", "pdf_ready"}:
        return get_resume_status(poke_user_id=poke_user_id, workflow_id=workflow_id)
    if str(draft.get("audit_status", "")) not in PREVIEW_AUDIT_STATUSES:
        return get_resume_status(poke_user_id=poke_user_id, workflow_id=workflow_id)
    if not confirmed:
        updated = workflows.set_action(
            workflow_id, poke_user_id,
            action_type="confirm_finalization",
            question="Generate the PDF and DOCX from this exact resume revision?",
            choices=[{"value": "confirm", "label": "Generate files"}],
        )
        return _action_response(updated)
    already_current = (
        draft.get("status") == "pdf_ready"
        and not draft.get("pdf_stale")
        and int(draft.get("pdf_revision") or 0) == int(base_revision)
    )
    workflows.update(workflow_id, poke_user_id, {
        "status": "finalizing", "revision": int(base_revision), "pending_action": None,
    })
    if not already_current:
        resume_app.generate_extension_pdf(draft)
    return get_resume_status(poke_user_id=poke_user_id, workflow_id=workflow_id)


def add_file_urls(response: dict, *, poke_user_id: str, base_url: str) -> dict:
    if response.get("status") != "completed":
        return response
    workflow = workflows.get_for_user(response["draft_id"], poke_user_id)
    draft = resume_app.extension_draft_payload(
        resume_app.extension_drafts.get(workflow["resume_draft_id"])
    )
    return {
        **response,
        "files": signed_download_urls(
            workflow=workflow, draft=draft, poke_user_id=poke_user_id, base_url=base_url
        ),
        "links_expire_in_hours": 24,
    }

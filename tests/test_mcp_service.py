from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

import database
from database import Base
from resume_mcp.contracts import ReplaceBullet, ReplaceResumeTitle
from resume_mcp.persistence import McpWorkflowStore
from resume_mcp import service


def setup_store(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'mcp-service.db'}", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_local)
    Base.metadata.create_all(bind=engine)
    store = McpWorkflowStore()
    monkeypatch.setattr(service, "workflows", store)
    return store


def test_missing_identity_returns_action_required(tmp_path, monkeypatch):
    setup_store(tmp_path, monkeypatch)
    monkeypatch.setattr(service.resume_app, "has_permanent_profile_doc", lambda: True)
    monkeypatch.setattr(service.resume_app, "validate_profile_payload", lambda _profile: [])
    monkeypatch.setattr(service.resume_app, "current_profile", lambda: {})
    monkeypatch.setattr(service.resume_app, "current_identity_profiles", lambda: [
        {"id": "outlook", "label": "Outlook"},
        {"id": "gmail", "label": "Gmail"},
    ])

    response = service.start_resume_generation(
        poke_user_id="poke-a",
        job_description="Build reliable software and integrations for enterprise customers. " * 4,
    )

    assert response["status"] == "action_required"
    assert response["action"]["type"] == "select_contact_identity"
    assert [item["value"] for item in response["action"]["choices"]] == ["outlook", "gmail"]


def test_invalid_identity_is_not_silently_replaced(tmp_path, monkeypatch):
    setup_store(tmp_path, monkeypatch)
    monkeypatch.setattr(service.resume_app, "has_permanent_profile_doc", lambda: True)
    monkeypatch.setattr(service.resume_app, "validate_profile_payload", lambda _profile: [])
    monkeypatch.setattr(service.resume_app, "current_profile", lambda: {})
    monkeypatch.setattr(service.resume_app, "current_identity_profiles", lambda: [
        {"id": "outlook", "label": "Outlook"},
    ])

    response = service.start_resume_generation(
        poke_user_id="poke-a",
        identity_id="missing",
        job_description="Build reliable software and integrations for enterprise customers. " * 4,
    )

    assert response["status"] == "action_required"
    assert "not available" in response["action"]["question"]


def test_no_configured_identity_returns_setup_action(tmp_path, monkeypatch):
    setup_store(tmp_path, monkeypatch)
    monkeypatch.setattr(service.resume_app, "has_permanent_profile_doc", lambda: True)
    monkeypatch.setattr(service.resume_app, "validate_profile_payload", lambda _profile: [])
    monkeypatch.setattr(service.resume_app, "current_profile", lambda: {})
    monkeypatch.setattr(service.resume_app, "current_identity_profiles", lambda: [])

    response = service.start_resume_generation(
        poke_user_id="poke-a",
        job_description="Build reliable software and integrations for enterprise customers. " * 4,
    )

    assert response["status"] == "action_required"
    assert response["action"]["type"] == "configure_contact_identity"
    assert response["action"]["choices"] == [{"value": "check_again", "label": "Check again"}]


def test_incomplete_profile_returns_recoverable_setup_action(tmp_path, monkeypatch):
    setup_store(tmp_path, monkeypatch)
    monkeypatch.setattr(service.resume_app, "has_permanent_profile_doc", lambda: True)
    monkeypatch.setattr(service.resume_app, "current_profile", lambda: {"name": "Candidate"})
    monkeypatch.setattr(
        service.resume_app,
        "validate_profile_payload",
        lambda _profile: ["At least one enabled work experience role with all fields filled is required."],
    )

    response = service.start_resume_generation(
        poke_user_id="poke-a",
        job_description="Build reliable software and integrations for enterprise customers. " * 4,
    )

    assert response["status"] == "action_required"
    assert response["action"]["type"] == "complete_profile_setup"
    assert response["action"]["details"]["issues"]


class FakeDraftStore:
    def __init__(self, draft):
        self.draft = draft

    def get(self, _draft_id):
        return self.draft

    def decide_duplicate(self, _draft_id, decision):
        self.draft = {**self.draft, "status": "queued" if decision == "continue" else "skipped"}
        return self.draft


def generated_draft():
    return {
        "id": "draft-1",
        "status": "ready",
        "stage": "complete",
        "resume_revision": 3,
        "audit_status": "applied",
        "title_summary": {"updated_title": "Software Engineer", "updated_summary": "A clear summary."},
        "skills": {"updated_skills": [{"category": "Backend", "items": ["Python", "APIs"]}]},
        "experience_recent": {"experience": {"mckinsey": {
            "title": "Software Engineer",
            "bullets": ["Built a reliable API for customer workflows."],
        }}},
        "experience_older": {"experience": {}},
        "enabled_experience_keys": ["mckinsey"],
        "experience_history_snapshot": [{
            "key": "mckinsey", "company": "Acme", "location": "CA",
            "title": "Engineer", "dates": "2025 - Present", "enabled": True,
        }],
        "resume_content": "Generated content",
        "resume_snapshot": {},
    }


def linked_workflow(store):
    workflow = store.create(
        poke_user_id="poke-a",
        job_description="Build reliable software and integrations. " * 5,
    )
    return store.update(workflow["id"], "poke-a", {
        "resume_draft_id": "draft-1", "revision": 3, "status": "preview_ready",
    })


def test_structured_edits_build_one_canonical_update(tmp_path, monkeypatch):
    store = setup_store(tmp_path, monkeypatch)
    workflow = linked_workflow(store)
    draft = generated_draft()
    monkeypatch.setattr(service.resume_app, "extension_drafts", FakeDraftStore(draft))
    captured = {}

    def fake_update(draft_id, payload, *, expected_revision):
        captured.update({"draft_id": draft_id, "payload": payload, "revision": expected_revision})
        return {
            **draft,
            "resume_revision": 4,
            "resume_content": "Edited content",
            "preview": {"title": payload["quick_edits"]["title"]},
        }

    monkeypatch.setattr(service.resume_app, "update_extension_draft_service", fake_update)
    response = service.apply_structured_changes(
        poke_user_id="poke-a",
        workflow_id=workflow["id"],
        base_revision=3,
        changes=[
            ReplaceResumeTitle(operation="replace_resume_title", new_text="Backend Engineer"),
            ReplaceBullet(
                operation="replace_bullet",
                role_key="mckinsey",
                bullet_number=1,
                expected_text="Built a reliable API for customer workflows.",
                new_text="Built and operated a reliable API for customer workflows.",
            ),
        ],
    )

    assert captured["revision"] == 3
    assert captured["payload"]["quick_edits"]["title"] == "Backend Engineer"
    assert captured["payload"]["quick_edits"]["experience"][0]["bullets"][0].startswith("Built and operated")
    assert response["revision"] == 4
    assert response["pdf_invalidated"] is True


def test_structured_edit_rejects_stale_revision(tmp_path, monkeypatch):
    store = setup_store(tmp_path, monkeypatch)
    workflow = linked_workflow(store)
    monkeypatch.setattr(service.resume_app, "extension_drafts", FakeDraftStore(generated_draft()))

    response = service.apply_structured_changes(
        poke_user_id="poke-a",
        workflow_id=workflow["id"],
        base_revision=2,
        changes=[ReplaceResumeTitle(operation="replace_resume_title", new_text="Backend Engineer")],
    )

    assert response["status"] == "action_required"
    assert response["revision"] == 3
    assert response["action"]["type"] == "refresh_resume_revision"
    assert response["resume_markdown"] == "Generated content"


def test_duplicate_status_returns_history_and_stable_action(tmp_path, monkeypatch):
    store = setup_store(tmp_path, monkeypatch)
    workflow = linked_workflow(store)
    draft = {**generated_draft(), "status": "duplicate_review"}
    monkeypatch.setattr(service.resume_app, "extension_drafts", FakeDraftStore(draft))
    monkeypatch.setattr(service.resume_app, "extension_draft_payload", lambda value: value)
    monkeypatch.setattr(
        service.resume_app,
        "tracker_company_history",
        lambda _company: {"count": 2, "applications": [{"role_title": "Engineer"}]},
    )

    first = service.get_resume_status(poke_user_id="poke-a", workflow_id=workflow["id"])
    second = service.get_resume_status(poke_user_id="poke-a", workflow_id=workflow["id"])

    assert first["status"] == "action_required"
    assert first["action"]["type"] == "duplicate_application"
    assert first["action"]["details"]["count"] == 2
    assert first["action"]["action_id"] == second["action"]["action_id"]


def test_finalization_reuses_current_files_and_does_not_create_tracker_entry(tmp_path, monkeypatch):
    store = setup_store(tmp_path, monkeypatch)
    workflow = linked_workflow(store)
    draft = {
        **generated_draft(),
        "status": "pdf_ready",
        "pdf_stale": False,
        "pdf_revision": 3,
        "pdf_path": "/tmp/resume.pdf",
        "docx_path": "/tmp/resume.docx",
    }
    monkeypatch.setattr(service.resume_app, "extension_drafts", FakeDraftStore(draft))
    monkeypatch.setattr(service.resume_app, "extension_draft_payload", lambda value: value)
    monkeypatch.setattr(
        service.resume_app,
        "generate_extension_pdf",
        lambda _draft: pytest.fail("Current files should be reused."),
    )

    response = service.finalize_resume(
        poke_user_id="poke-a",
        workflow_id=workflow["id"],
        base_revision=3,
        confirmed=True,
    )

    assert response["status"] == "completed"
    assert response["revision"] == 3


def test_finalization_preserves_docx_for_later_requests(tmp_path, monkeypatch):
    store = setup_store(tmp_path, monkeypatch)
    workflow = linked_workflow(store)
    draft = generated_draft()
    draft_store = FakeDraftStore(draft)
    monkeypatch.setattr(service.resume_app, "extension_drafts", draft_store)
    monkeypatch.setattr(service.resume_app, "extension_draft_payload", lambda value: value)
    captured = {}

    def fake_generate(value, *, preserve_docx=False):
        captured["draft"] = value
        captured["preserve_docx"] = preserve_docx
        return value

    monkeypatch.setattr(service.resume_app, "generate_extension_pdf", fake_generate)

    service.finalize_resume(
        poke_user_id="poke-a",
        workflow_id=workflow["id"],
        base_revision=3,
        confirmed=True,
    )

    assert captured["draft"]["id"] == "draft-1"
    assert captured["preserve_docx"] is True

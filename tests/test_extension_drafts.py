import threading

import pytest
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import database
from database import Base, ResumeDraftTask
from extension_drafts import ActiveDraftTaskError, AuditStaleError, ExtensionDraftStore, canonical_job_url, normalize_context, validate_context


def store_for_test(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'drafts.db'}", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_local)
    Base.metadata.create_all(bind=engine)
    return ExtensionDraftStore()


def save_audit(store, draft, result, base_hash="hash-1"):
    result = {"schema_version": "2", **result}
    if result.get("decision") == "changes_proposed":
        result["decision"] = "changes_suggested"
    elif result.get("decision") == "blocked":
        result["decision"] = "manual_attention"
    if "proposed_resume" in result and "changes" not in result:
        result["changes"] = result.pop("proposed_resume")
    running = store.start_audit(draft["id"])
    return store.save_audit_result(
        draft["id"],
        result,
        base_hash,
        draft["resume_revision"],
        running["audit_result"]["run_token"],
    )


def context(job_id="12345", company="Acme"):
    return {
        "source": "linkedin",
        "external_job_id": job_id,
        "url": f"https://www.linkedin.com/jobs/view/{job_id}/?trackingId=ignored",
        "company_name": company,
        "role_title": "Backend Engineer",
        "location": "Chicago, IL",
        "job_description": "Build and operate reliable backend systems and APIs. " * 8,
    }


def snapshot():
    history = [{
        "key": "mckinsey",
        "company": "Acme Consulting",
        "location": "CA, USA",
        "title": "Software Engineer",
        "dates": "May 2025 - Present",
        "enabled": True,
    }]
    return {
        "identity_id": "outlook",
        "enabled_experience_keys": ["mckinsey"],
        "profile_snapshot": {"name": "Candidate", "experience_history": history},
        "contact_snapshot": {"location": "Austin, TX", "phone": "555-0100", "email": "candidate@example.com"},
        "experience_history_snapshot": history,
    }


def task_rows(draft_id):
    with database.SessionLocal() as db:
        return db.query(ResumeDraftTask).filter(ResumeDraftTask.draft_id == draft_id).order_by(ResumeDraftTask.requested_at.asc()).all()


def task_statuses(draft_id):
    return [task.status for task in task_rows(draft_id)]


def test_linkedin_context_uses_stable_job_id_and_canonical_url():
    normalized = normalize_context(context())
    assert normalized["source_key"] == "linkedin:12345"
    assert normalized["canonical_url"] == "https://www.linkedin.com/jobs/view/12345/"
    assert not validate_context(normalized)
    assert canonical_job_url("https://www.linkedin.com/jobs/view/12345/?trk=abc", "12345") == normalized["canonical_url"]


def test_dice_context_uses_stable_job_id_and_canonical_url():
    payload = {
        "source": "dice",
        "url": "https://www.dice.com/job-detail/336d7a94-e57e-47b1-ae57-07fbdb593ea4?utm_source=test",
        "company_name": "Zions Bancorporation",
        "role_title": "Engineering Manager",
        "location": "Midvale, UT",
        "job_description": "Lead reliable infrastructure and network operations across the enterprise. " * 8,
    }

    normalized = normalize_context(payload)

    assert normalized["external_job_id"] == "336d7a94-e57e-47b1-ae57-07fbdb593ea4"
    assert normalized["source_key"] == "dice:336d7a94-e57e-47b1-ae57-07fbdb593ea4"
    assert normalized["canonical_url"] == "https://www.dice.com/job-detail/336d7a94-e57e-47b1-ae57-07fbdb593ea4"
    assert not validate_context(normalized)


def test_linkedin_and_dice_job_ids_do_not_collide(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    linkedin = store.create(context("shared-id", "LinkedIn Company"), snapshot(), duplicate_count=0)
    dice_context = {
        **context("shared-id", "Dice Company"),
        "source": "dice",
        "url": "https://www.dice.com/job-detail/shared-id",
    }
    dice = store.create(dice_context, snapshot(), duplicate_count=0)

    assert linkedin["id"] != dice["id"]
    assert linkedin["source_key"] == "linkedin:shared-id"
    assert dice["source_key"] == "dice:shared-id"
    _, restored = store.resolve(dice_context)
    assert restored["id"] == dice["id"]


def test_incomplete_context_is_blocked():
    normalized = normalize_context({"url": "https://www.linkedin.com/jobs/", "company_name": "", "role_title": "Engineer", "job_description": "short"})
    issues = validate_context(normalized)
    assert "Company is required." in issues
    assert "The extracted job description is incomplete." in issues


def test_drafts_are_isolated_and_restore_by_linkedin_job(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    first = store.create(context("111", "Acme"), snapshot(), duplicate_count=0)
    second = store.create(context("222", "Beta"), snapshot(), duplicate_count=0)
    assert first["id"] != second["id"]
    assert first["source_key"] == "linkedin:111"
    assert second["source_key"] == "linkedin:222"
    _, restored = store.resolve(context("111", "Acme"))
    assert restored["id"] == first["id"]


def test_duplicate_review_creates_no_task_until_continue(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=2)
    assert draft["status"] == "duplicate_review"
    assert store.has_duplicate_review() is True
    assert store.next_task() is None
    continued = store.decide_duplicate(draft["id"], "continue")
    assert continued["status"] == "queued"
    assert store.has_duplicate_review() is False
    task = store.next_task()
    assert task["draft"]["id"] == draft["id"]


def test_mcp_draft_accepts_jd_before_company_and_role_are_known(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create_mcp(
        {
            "job_description": "Build reliable software and integrations for enterprise customers. " * 4,
            "company_name": "",
            "role_title": "",
        },
        snapshot(),
        "mcp-workflow-1",
    )

    assert draft["source"] == "mcp"
    assert draft["source_key"] == "mcp:mcp-workflow-1"
    assert draft["company_name"] == ""
    assert draft["role_title"] == ""
    assert draft["source_metadata"]["duplicate_checked"] is False
    assert store.next_task()["draft"]["id"] == draft["id"]


def test_technical_review_retry_keeps_generated_resume_checkpoint(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    task = store.next_task()
    ready = store.complete_task(task["task_id"], draft["id"], {
        "status": "ready",
        "stage": "complete",
        "resume_content": "Generated resume checkpoint",
        "audit_status": "technical_failed",
        "audit_result": {"error": "connection closed"},
    })

    queued = store.retry_audit_background(ready["id"])

    assert queued["status"] == "queued"
    assert queued["stage"] == "audit"
    assert queued["resume_content"] == "Generated resume checkpoint"
    assert queued["audit_status"] == "not_started"
    assert task_statuses(draft["id"]) == ["completed", "queued"]


def test_skip_retains_draft_without_queueing(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=1)
    skipped = store.decide_duplicate(draft["id"], "skip")
    assert skipped["status"] == "skipped"
    assert store.next_task() is None


def test_applied_drafts_are_locked_and_cannot_be_deleted(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    applied = store.update(draft["id"], {"status": "applied", "application_id": "application-1"})
    assert applied["locked"] is True
    try:
        store.update(draft["id"], {"company_name": "Changed"})
        raise AssertionError("Applied draft update should fail")
    except ValueError as error:
        assert "locked" in str(error).lower()
    try:
        store.delete(draft["id"])
        raise AssertionError("Applied draft deletion should fail")
    except ValueError as error:
        assert "cannot be deleted" in str(error).lower()


def test_identical_delayed_save_keeps_generated_pdf_current(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    ready = store.update(draft["id"], {
        "status": "pdf_ready",
        "resume_content": "Generated resume content",
        "pdf_path": str(tmp_path / "resume.pdf"),
        "pdf_revision": draft["resume_revision"],
        "pdf_stale": False,
    })

    repeated = store.update(
        draft["id"],
        {"resume_content": "Generated resume content"},
        invalidate_pdf=True,
    )

    assert repeated["status"] == "pdf_ready"
    assert repeated["pdf_stale"] is False
    assert repeated["resume_revision"] == ready["resume_revision"]
    assert repeated["pdf_revision"] == ready["pdf_revision"]


def test_real_resume_edit_increments_revision_and_invalidates_pdf(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    ready = store.update(draft["id"], {
        "status": "pdf_ready",
        "resume_content": "Original resume content",
        "pdf_path": str(tmp_path / "resume.pdf"),
        "pdf_revision": draft["resume_revision"],
        "pdf_stale": False,
    })

    changed = store.update(
        draft["id"],
        {"resume_content": "Edited resume content"},
        invalidate_pdf=True,
    )

    assert changed["status"] == "ready"
    assert changed["pdf_stale"] is True
    assert changed["resume_revision"] == ready["resume_revision"] + 1
    assert changed["pdf_revision"] == ready["pdf_revision"]


def test_completed_draft_preserves_original_resume_version(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    task = store.next_task()
    ready = store.complete_task(task["task_id"], draft["id"], {
        "title_summary": {"updated_title": "Backend Engineer", "updated_summary": "Summary"},
        "skills": {"updated_skills": [{"category": "Backend", "items": ["Python", "APIs"]}]},
        "experience_recent": {"experience": {"mckinsey": {"title": "Backend Engineer"}}},
        "experience_older": {"experience": {}},
        "resume_content": "Original generated resume",
        "resume_snapshot": {"title": "Backend Engineer"},
    })

    assert ready["active_resume_version"] == "original"
    assert set(ready["resume_versions"]) == {"original"}
    original = ready["resume_versions"]["original"]
    assert set(original) == {
        "title_summary", "skills", "experience_recent", "experience_older",
        "resume_content", "resume_snapshot", "revision", "created_at",
    }
    assert original["resume_content"] == "Original generated resume"
    assert original["revision"] == ready["resume_revision"]
    assert original["created_at"]


def test_luna_and_manual_versions_preserve_prior_versions(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    task = store.next_task()
    ready = store.complete_task(task["task_id"], draft["id"], {
        "title_summary": {"updated_title": "Backend Engineer", "updated_summary": "Original summary"},
        "skills": {"updated_skills": [{"category": "Backend", "items": ["Python", "APIs"]}]},
        "experience_recent": {"experience": {}},
        "experience_older": {"experience": {}},
        "resume_content": "Original generated resume",
        "resume_snapshot": {"title": "Backend Engineer"},
    })
    audited = save_audit(
        store,
        ready,
        {"decision": "changes_suggested", "changes": {"title": {"replacement": "Platform Engineer"}}},
    )
    luna = store.resolve_audit_decisions(
        draft["id"],
        expected_revision=audited["resume_revision"],
        expected_hash="hash-1",
        current_hash="hash-1",
        values={
            "title_summary": {"updated_title": "Platform Engineer", "updated_summary": "Reviewed summary"},
            "skills": ready["skills"],
            "experience_recent": ready["experience_recent"],
            "experience_older": ready["experience_older"],
            "resume_content": "Luna reviewed resume",
            "resume_snapshot": {"title": "Platform Engineer"},
        },
    )

    assert luna["active_resume_version"] == "luna_reviewed"
    assert set(luna["resume_versions"]) == {"original", "luna_reviewed"}
    assert luna["resume_versions"]["original"]["resume_content"] == "Original generated resume"
    assert luna["resume_versions"]["luna_reviewed"]["resume_content"] == "Luna reviewed resume"

    manual = store.update(
        draft["id"],
        {
            "title_summary": {"updated_title": "Senior Platform Engineer", "updated_summary": "Manual summary"},
            "resume_content": "Manually edited resume",
            "resume_snapshot": {"title": "Senior Platform Engineer"},
        },
        invalidate_pdf=True,
    )

    assert manual["active_resume_version"] == "manual"
    assert set(manual["resume_versions"]) == {"original", "luna_reviewed", "manual"}
    assert manual["resume_versions"]["original"] == luna["resume_versions"]["original"]
    assert manual["resume_versions"]["luna_reviewed"] == luna["resume_versions"]["luna_reviewed"]
    assert manual["resume_versions"]["manual"]["resume_content"] == "Manually edited resume"
    assert manual["resume_versions"]["manual"]["revision"] == manual["resume_revision"]


def test_init_db_adds_and_serializes_audit_columns(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE resume_drafts ("
            "id VARCHAR(80) PRIMARY KEY, status VARCHAR(60), updated_at DATETIME, "
            "pdf_stale BOOLEAN NOT NULL DEFAULT 0, pdf_path TEXT, resume_revision INTEGER NOT NULL DEFAULT 1)"
        ))
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    columns = {column["name"] for column in inspect(engine).get_columns("resume_drafts")}
    assert {
        "resume_versions", "active_resume_version",
        "audit_status", "audit_result", "audit_proposal", "audit_base_revision",
        "audit_base_hash", "audit_created_at", "audit_applied_at",
    } <= columns


def test_edit_invalidates_pending_audit_proposal(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {"status": "ready", "resume_content": "Original"})
    result = {"decision": "changes_proposed", "proposed_resume": {"updated_title": "New"}}
    audited = save_audit(store, draft, result)
    changed = store.update(
        draft["id"],
        {"identity_id": "gmail"},
        invalidate_pdf=True,
    )
    assert audited["audit_status"] == "changes_suggested"
    assert changed["audit_status"] == "kept_current"
    assert changed["audit_proposal"] is None


def test_out_of_order_audit_result_cannot_overwrite_newer_run(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {"status": "ready", "resume_content": "Original"})
    first = store.start_audit(draft["id"])
    first_token = first["audit_result"]["run_token"]
    second = store.start_audit(draft["id"])
    second_token = second["audit_result"]["run_token"]
    release_old = threading.Event()
    old_finished = threading.Event()
    old_error = []

    def save_old_result():
        release_old.wait(timeout=2)
        try:
            store.save_audit_result(
                draft["id"],
                {"schema_version": "2", "decision": "manual_attention", "changes": None},
                "old-hash",
                draft["resume_revision"],
                first_token,
            )
        except Exception as exc:
            old_error.append(exc)
        finally:
            old_finished.set()

    old_thread = threading.Thread(target=save_old_result)
    old_thread.start()
    newest = store.save_audit_result(
        draft["id"],
        {"schema_version": "2", "decision": "approved", "changes": None},
        "new-hash",
        draft["resume_revision"],
        second_token,
    )
    release_old.set()
    assert old_finished.wait(timeout=2)
    old_thread.join(timeout=2)

    assert newest["audit_status"] == "approved"
    assert len(old_error) == 1
    assert isinstance(old_error[0], AuditStaleError)
    preserved = store.get(draft["id"])
    assert preserved["audit_status"] == "approved"
    assert preserved["audit_base_hash"] == "new-hash"


def test_resolved_reject_all_is_immune_to_late_result_and_failure(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {"status": "ready", "resume_content": "Original"})
    running = store.start_audit(draft["id"])
    token = running["audit_result"]["run_token"]
    pending = store.save_audit_result(
        draft["id"],
        {
            "schema_version": "2",
            "decision": "changes_suggested",
            "changes": {"updated_title": "New"},
        },
        "hash-1",
        draft["resume_revision"],
        token,
    )
    kept = store.resolve_audit_decisions(
        draft["id"],
        expected_revision=pending["resume_revision"],
        expected_hash="hash-1",
        current_hash="hash-1",
        values=None,
    )

    with pytest.raises(AuditStaleError):
        store.save_audit_result(
            draft["id"],
            {"schema_version": "2", "decision": "manual_attention", "changes": None},
            "late-hash",
            draft["resume_revision"],
            token,
        )
    with pytest.raises(AuditStaleError):
        store.mark_audit_failure(draft["id"], "late failure", token)

    preserved = store.get(draft["id"])
    assert kept["audit_status"] == "kept_current"
    assert preserved["audit_status"] == "kept_current"
    assert preserved["audit_base_hash"] == "hash-1"


def test_default_resume_snapshot_edit_stales_approved_audit(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {"status": "ready", "resume_content": "Original"})
    approved = save_audit(
        store,
        draft,
        {"decision": "approved", "proposed_resume": None},
    )

    changed = store.update(
        draft["id"],
        {"resume_snapshot": {"title": "Edited"}},
        invalidate_pdf=True,
    )

    assert approved["audit_status"] == "approved"
    assert changed["audit_status"] == "kept_current"
    assert changed["audit_proposal"] is None


def test_keep_current_does_not_change_revision_or_pdf(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {"status": "ready", "resume_content": "Original"})
    result = {"decision": "changes_proposed", "proposed_resume": {"updated_title": "New"}}
    audited = save_audit(store, draft, result)
    kept = store.keep_current_audit(draft["id"])
    assert kept["audit_status"] == "kept_current"
    assert kept["audit_proposal"] is None
    assert kept["resume_revision"] == audited["resume_revision"]
    assert kept["pdf_stale"] == audited["pdf_stale"]


@pytest.mark.parametrize("resolved_status", ["approved", "kept_current"])
def test_resume_edit_makes_completed_audit_stale(tmp_path, monkeypatch, resolved_status):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {"status": "ready", "resume_content": "Original"})
    if resolved_status == "approved":
        resolved = save_audit(
            store,
            draft,
            {"decision": "approved", "proposed_resume": None},
        )
    else:
        save_audit(
            store,
            draft,
            {"decision": "changes_proposed", "proposed_resume": {"updated_title": "New"}},
        )
        resolved = store.keep_current_audit(draft["id"])

    edited = store.update(draft["id"], {"resume_content": "Edited"}, invalidate_pdf=True)

    assert resolved["audit_status"] == resolved_status
    assert edited["audit_status"] == "kept_current"
    assert edited["audit_proposal"] is None
    assert edited["audit_result"] == resolved["audit_result"]


def test_stale_apply_commits_stale_state(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {"status": "ready", "resume_content": "Original"})
    result = {"decision": "changes_proposed", "proposed_resume": {"updated_title": "New"}}
    save_audit(store, draft, result)
    with pytest.raises(AuditStaleError):
        store.apply_audit_proposal(
            draft["id"],
            expected_revision=draft["resume_revision"],
            expected_hash="hash-1",
            current_hash="changed",
            values={
                "title_summary": {}, "skills": {}, "experience_recent": {},
                "experience_older": {}, "resume_content": "New", "resume_snapshot": {},
            },
        )
    assert store.get(draft["id"])["audit_status"] == "stale"


def test_apply_increments_once_and_invalidates_pdf(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {
        "status": "pdf_ready", "resume_content": "Original",
        "pdf_path": str(tmp_path / "resume.pdf"), "pdf_stale": False,
    })
    result = {"decision": "changes_proposed", "proposed_resume": {"updated_title": "New"}}
    audited = save_audit(store, draft, result)
    applied = store.apply_audit_proposal(
        draft["id"],
        expected_revision=audited["resume_revision"],
        expected_hash="hash-1",
        current_hash="hash-1",
        values={
            "title_summary": {"updated_title": "New"}, "skills": {"updated_skills": []},
            "experience_recent": {"experience": {}}, "experience_older": {"experience": {}},
            "resume_content": "New content", "resume_snapshot": {"title": "New"},
        },
    )
    assert applied["resume_revision"] == audited["resume_revision"] + 1
    assert applied["pdf_stale"] is True
    assert applied["status"] == "ready"
    assert applied["audit_status"] == "applied"
    assert applied["audit_proposal"] is None
    assert applied["audit_result"]["schema_version"] == "2"
    assert applied["audit_result"]["decision"] == "changes_suggested"
    assert applied["audit_result"]["changes"] == {"updated_title": "New"}


def test_reject_all_resolution_uses_stale_guard_without_changing_resume(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {
        "status": "pdf_ready",
        "resume_content": "Original",
        "pdf_path": str(tmp_path / "resume.pdf"),
        "pdf_stale": False,
    })
    result = {"decision": "changes_proposed", "proposed_resume": {"updated_title": "New"}}
    audited = save_audit(store, draft, result)

    kept = store.resolve_audit_decisions(
        draft["id"],
        expected_revision=audited["resume_revision"],
        expected_hash="hash-1",
        current_hash="hash-1",
        values=None,
    )

    assert kept["audit_status"] == "kept_current"
    assert kept["audit_proposal"] is None
    assert kept["resume_revision"] == audited["resume_revision"]
    assert kept["resume_content"] == "Original"
    assert kept["pdf_stale"] is False
    assert kept["status"] == "pdf_ready"


def test_reject_all_resolution_marks_changed_base_stale(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    draft = store.update(draft["id"], {"status": "ready", "resume_content": "Original"})
    result = {"decision": "changes_proposed", "proposed_resume": {"updated_title": "New"}}
    save_audit(store, draft, result)

    with pytest.raises(AuditStaleError):
        store.resolve_audit_decisions(
            draft["id"],
            expected_revision=draft["resume_revision"],
            expected_hash="hash-1",
            current_hash="changed",
            values=None,
        )

    assert store.get(draft["id"])["audit_status"] == "stale"


def test_regenerate_clears_audit_and_applied_drafts_remain_locked(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    task = store.next_task()
    draft = store.complete_task(task["task_id"], draft["id"], {"resume_content": "Original"})
    save_audit(
        store,
        draft,
        {"decision": "changes_proposed", "proposed_resume": {"updated_title": "New"}},
    )
    regenerated = store.regenerate(draft["id"])
    assert regenerated["audit_status"] == "not_started"
    assert regenerated["audit_result"] is None
    assert regenerated["audit_proposal"] is None
    assert regenerated["resume_versions"] == {}
    assert regenerated["active_resume_version"] == ""
    applied = store.update(regenerated["id"], {"status": "applied", "application_id": "application-1"})
    with pytest.raises(ValueError, match="locked"):
        store.start_audit(applied["id"])


def test_regenerate_conflicts_with_running_task_and_preserves_checkpoints(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    task = store.next_task()
    checkpointed = store.checkpoint(task["task_id"], draft["id"], "core", {
        "status": "generating_core",
        "analysis": {"target_role": "Backend Engineer"},
        "title_summary": {"updated_title": "Checkpoint"},
        "resume_content": "Partial checkpoint",
    })

    with pytest.raises(ActiveDraftTaskError):
        store.regenerate(draft["id"], context("12345", "Changed"))

    preserved = store.get(draft["id"])
    assert preserved["status"] == "generating_core"
    assert preserved["analysis"] == checkpointed["analysis"]
    assert preserved["title_summary"] == checkpointed["title_summary"]
    assert preserved["resume_content"] == "Partial checkpoint"
    assert preserved["company_name"] == "Acme"
    assert task_statuses(draft["id"]) == ["running"]
    assert store.next_task() is None


def test_worker_prunes_legacy_running_plus_queued_duplicate(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    running = store.next_task()
    with database.SessionLocal() as db:
        db.add(ResumeDraftTask(id="task-legacy-duplicate", draft_id=draft["id"], status="queued", stage="waiting"))
        db.commit()

    assert sorted(task_statuses(draft["id"])) == ["queued", "running"]
    assert store.next_task() is None
    assert task_statuses(draft["id"]) == ["running"]
    assert running["draft"]["id"] == draft["id"]


def test_repeated_concurrent_regenerate_enqueues_one_active_task(tmp_path, monkeypatch):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    task = store.next_task()
    ready = store.complete_task(task["task_id"], draft["id"], {
        "resume_content": "Generated resume",
        "analysis": {"target_role": "Backend Engineer"},
        "title_summary": {"updated_title": "Backend Engineer"},
        "skills": {"updated_skills": []},
        "experience_recent": {"experience": {}},
        "experience_older": {"experience": {}},
    })

    def regenerate_once():
        try:
            return ("ok", store.regenerate(ready["id"]))
        except ActiveDraftTaskError as exc:
            return ("conflict", str(exc))

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _index: regenerate_once(), range(4)))

    successful_regenerates = [payload for status, payload in results if status == "ok"]
    assert len(successful_regenerates) == 1
    assert sum(1 for status, _payload in results if status == "conflict") == 3
    regenerated = successful_regenerates[0]
    assert regenerated["status"] == "queued"
    assert regenerated["stage"] == "waiting"
    assert regenerated["resume_content"] == ""
    assert regenerated["analysis"] == {}
    assert regenerated["title_summary"] == {}
    assert regenerated["skills"] == {}
    assert regenerated["experience_recent"] == {}
    assert regenerated["experience_older"] == {}
    assert regenerated["resume_revision"] == ready["resume_revision"] + 1
    statuses = task_statuses(draft["id"])
    active_statuses = [status for status in statuses if status in {"queued", "running"}]
    assert len(active_statuses) == 1
    assert statuses.count("completed") == 0


@pytest.mark.parametrize("terminal_status", ["completed", "failed"])
def test_regenerate_after_terminal_task_resets_and_enqueues_exactly_one(tmp_path, monkeypatch, terminal_status):
    store = store_for_test(tmp_path, monkeypatch)
    draft = store.create(context(), snapshot(), duplicate_count=0)
    task = store.next_task()
    if terminal_status == "completed":
        ready = store.complete_task(task["task_id"], draft["id"], {
            "resume_content": "Generated resume",
            "analysis": {"target_role": "Backend Engineer"},
            "title_summary": {"updated_title": "Backend Engineer"},
            "skills": {"updated_skills": []},
            "experience_recent": {"experience": {}},
            "experience_older": {"experience": {}},
        })
    else:
        store.fail_task(task["task_id"], draft["id"], "analysis", "boom")
        ready = store.update(draft["id"], {
            "status": "ready",
            "stage": "complete",
            "resume_content": "Manual recovery",
            "analysis": {"target_role": "Backend Engineer"},
        })

    regenerated = store.regenerate(ready["id"])

    assert regenerated["status"] == "queued"
    assert regenerated["stage"] == "waiting"
    assert regenerated["resume_content"] == ""
    assert regenerated["analysis"] == {}
    assert regenerated["resume_revision"] == ready["resume_revision"] + 1
    assert task_statuses(draft["id"]) == ["queued"]

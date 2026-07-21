from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
from database import Base
from extension_drafts import ExtensionDraftStore, canonical_job_url, normalize_context, validate_context


def store_for_test(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'drafts.db'}", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_local)
    Base.metadata.create_all(bind=engine)
    return ExtensionDraftStore()


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
        "contact_snapshot": {"location": "Dallas, TX", "phone": "123", "email": "candidate@example.com"},
        "experience_history_snapshot": history,
    }


def test_linkedin_context_uses_stable_job_id_and_canonical_url():
    normalized = normalize_context(context())
    assert normalized["source_key"] == "linkedin:12345"
    assert normalized["canonical_url"] == "https://www.linkedin.com/jobs/view/12345/"
    assert not validate_context(normalized)
    assert canonical_job_url("https://www.linkedin.com/jobs/view/12345/?trk=abc", "12345") == normalized["canonical_url"]


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

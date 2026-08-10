import copy
import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app as resume_app
import database
from database import Base, ResumeDraftTask
from extension_drafts import AuditStaleError, ExtensionDraftStore


def pipeline_store(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline.db'}", future=True)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_local)
    Base.metadata.create_all(bind=engine)
    store = ExtensionDraftStore()
    monkeypatch.setattr(resume_app, "extension_drafts", store)
    return store


def queued_task(store):
    history = [
        {
            "key": blueprint["key"],
            "company": blueprint["company"],
            "location": blueprint["location"],
            "dates": blueprint["dates"],
            "title": "Software Engineer",
            "enabled": True,
        }
        for blueprint in resume_app.EXPERIENCE_BLUEPRINTS
    ]
    draft = store.create(
        {
            "source": "linkedin",
            "external_job_id": "audit-pipeline",
            "company_name": "Acme",
            "role_title": "Backend Engineer",
            "job_description": "Build reliable Python APIs and distributed backend systems. " * 8,
        },
        {
            "identity_id": "outlook",
            "enabled_experience_keys": [item["key"] for item in history],
            "profile_snapshot": {"name": "Candidate"},
            "contact_snapshot": {"email": "candidate@example.com"},
            "experience_history_snapshot": history,
        },
        0,
    )
    return draft, store.next_task()


def active_task_statuses(draft_id):
    with database.SessionLocal() as db:
        rows = db.query(ResumeDraftTask.status).filter(
            ResumeDraftTask.draft_id == draft_id,
            ResumeDraftTask.status.in_(("queued", "running")),
        ).all()
    return [status for (status,) in rows]


def ready_pdf_draft(store, audit_status):
    with store._task_lock:
        draft = store.create(
            {
                "source": "linkedin",
                "external_job_id": f"pdf-audit-{audit_status}",
                "company_name": "Acme",
                "role_title": "Backend Engineer",
                "job_description": "Build reliable Python APIs and distributed backend systems. " * 8,
            },
            {
                "identity_id": "outlook",
                "enabled_experience_keys": [],
                "profile_snapshot": {"name": "Candidate"},
                "contact_snapshot": {"email": "candidate@example.com"},
                "experience_history_snapshot": [],
            },
            0,
        )
        task = store.next_task()
        assert task["draft"]["id"] == draft["id"]
        draft = store.complete_task(task["task_id"], draft["id"], {
            "resume_content": "Generated resume",
            "title_summary": {"updated_title": "Backend Engineer"},
            "analysis": {"target_role": "Backend Engineer"},
            "skills": {"updated_skills": []},
            "experience_recent": {"experience": {}},
            "experience_older": {"experience": {}},
        })
    assert active_task_statuses(draft["id"]) == []
    draft = store.update(draft["id"], {
        "audit_status": audit_status,
    })
    assert active_task_statuses(draft["id"]) == []
    return draft


def install_pipeline_mocks(monkeypatch, calls, *, audit_error=None):
    analysis = {
        "target_role": "Backend Engineer",
        "role_family": "backend application engineering",
        "skill_category_order_key": "backend_application",
        "prompt_family_key": "software_engineering",
        "skills_mentioned": ["Python"],
    }
    preliminary = {"updated_skills": [{"category": "Programming Languages", "items": ["Python"]}]}

    def analyze(**_kwargs):
        calls.append(("analysis", None))
        return analysis

    def skills(**_kwargs):
        calls.append(("skills", None))
        return copy.deepcopy(preliminary)

    def experience(**kwargs):
        calls.append(("experience", copy.deepcopy(kwargs["preliminary_skills_payload"])))
        return {
            "experience": {
                item["key"]: {"title": "Software Engineer", "bullets": ["Built reliable Python systems."]}
                for item in kwargs["blueprints"]
            }
        }

    def synthesis(**kwargs):
        calls.append(("synthesis", copy.deepcopy(kwargs["combined_experience_payload"])))
        return {
            "updated_title": "Backend Engineer",
            "updated_summary": "Backend engineer building reliable Python systems.",
            "updated_skills": preliminary["updated_skills"],
            "experience_titles": {
                item["key"]: "Backend Software Engineer" for item in kwargs["active_blueprints"]
            },
        }

    def audit(**kwargs):
        calls.append(("audit", copy.deepcopy(kwargs["current_resume"])))
        if audit_error:
            raise audit_error
        return {
            "schema_version": "2",
            "decision": "approved",
            "overall_score": 95,
            "review_summary": "The resume is ready.",
            "component_scores": {
                "ats_alignment": 95,
                "technical_credibility": 95,
                "human_tone": 95,
                "evidence_quality": 95,
                "career_coherence": 95,
            },
            "manual_findings": [],
            "changes": resume_app._empty_resume_quality_audit_changes(),
            "review_groups": [],
            "withheld_changes": [],
            "base_hash": resume_app.canonical_json_hash(kwargs["current_resume"]),
        }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "analyze_job_description", analyze)
    monkeypatch.setattr(resume_app, "generate_skills_from_analysis", skills)
    monkeypatch.setattr(resume_app, "generate_experience_subset_from_analysis", experience)
    monkeypatch.setattr(resume_app, "generate_final_synthesis_from_analysis", synthesis)
    monkeypatch.setattr(resume_app, "generate_resume_quality_audit", audit)
    monkeypatch.setattr(resume_app, "generate_title_summary_from_analysis", lambda **_kwargs: pytest.fail("early title call"))
    monkeypatch.setattr(resume_app, "normalize_updated_skills", lambda value: value)
    monkeypatch.setattr(resume_app, "validate_skills_only_payload", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(resume_app, "validate_experience_subset_payload_with_analysis", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(resume_app, "validate_final_synthesis_payload", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(resume_app, "format_generated_resume_text", lambda *_args, **_kwargs: "Generated resume")
    monkeypatch.setattr(resume_app, "draft_resume_snapshot", lambda draft: {"title": draft["title_summary"]["updated_title"]})
    return preliminary


def test_worker_makes_six_calls_and_audits_canonical_resume(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    calls = []
    preliminary = install_pipeline_mocks(monkeypatch, calls)

    resume_app.run_extension_generation_task(task)

    assert [name for name, _payload in calls] == [
        "analysis", "skills", "experience", "experience", "synthesis", "audit"
    ], store.get(draft["id"])["error_message"]
    assert calls[2][1] == preliminary
    assert calls[3][1] == preliminary
    assert set(calls[4][1]["experience"]) == set(draft["enabled_experience_keys"])
    canonical = calls[5][1]
    assert canonical["updated_title"] == "Backend Engineer"
    assert set(canonical["experience"]) == set(draft["enabled_experience_keys"])
    completed = store.get(draft["id"])
    assert completed["status"] == "ready"
    assert completed["audit_status"] == "approved"


def test_mcp_jd_analysis_enriches_context_and_is_reused_after_duplicate_decision(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    history = [
        {
            "key": blueprint["key"],
            "company": blueprint["company"],
            "location": blueprint["location"],
            "dates": blueprint["dates"],
            "title": "Software Engineer",
            "enabled": True,
        }
        for blueprint in resume_app.EXPERIENCE_BLUEPRINTS
    ]
    draft = store.create_mcp(
        {
            "job_description": "Build reliable Python APIs and distributed backend systems. " * 8,
            "company_name": "",
            "role_title": "",
        },
        {
            "identity_id": "outlook",
            "enabled_experience_keys": [item["key"] for item in history],
            "profile_snapshot": {"name": "Candidate"},
            "contact_snapshot": {"email": "candidate@example.com"},
            "experience_history_snapshot": history,
        },
        "workflow-1",
    )
    task = store.next_task()
    calls = []
    install_pipeline_mocks(monkeypatch, calls)
    original_analysis = resume_app.analyze_job_description

    def analyze_with_context(**kwargs):
        return {
            **original_analysis(**kwargs),
            "company_name": "Acme",
            "target_role": "Backend Engineer",
        }

    monkeypatch.setattr(resume_app, "analyze_job_description", analyze_with_context)
    monkeypatch.setattr(
        resume_app,
        "tracker_company_history",
        lambda _company: {"count": 1, "applications": [{"company": "Acme"}]},
    )

    resume_app.run_extension_generation_task(task)

    paused = store.get(draft["id"])
    assert paused["status"] == "duplicate_review"
    assert paused["company_name"] == "Acme"
    assert paused["role_title"] == "Backend Engineer"
    assert [name for name, _payload in calls] == ["analysis"]

    store.decide_duplicate(draft["id"], "continue")
    resume_app.run_extension_generation_task(store.next_task())

    completed = store.get(draft["id"])
    assert completed["status"] == "ready"
    assert [name for name, _payload in calls].count("analysis") == 1


def test_audit_failure_preserves_ready_resume(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    calls = []
    install_pipeline_mocks(monkeypatch, calls, audit_error=RuntimeError("audit unavailable"))

    resume_app.run_extension_generation_task(task)

    completed = store.get(draft["id"])
    assert completed["status"] == "ready"
    assert completed["resume_content"] == "Generated resume"
    assert completed["audit_status"] == "technical_failed"
    assert "audit unavailable" in completed["audit_result"]["error"]


def test_duplicate_review_gate_blocks_quality_audit_stage(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    calls = []
    install_pipeline_mocks(monkeypatch, calls)
    duplicate_review = threading.Event()
    audit_gate_waiting = threading.Event()
    release_gate = threading.Event()
    synthesis_finished = threading.Event()
    audit_started = threading.Event()
    original_synthesis = resume_app.generate_final_synthesis_from_analysis
    original_audit = resume_app.generate_resume_quality_audit

    class ObservedWorkerSignal:
        def wait(self, timeout=None):
            audit_gate_waiting.set()
            return release_gate.wait(timeout=timeout)

        def clear(self):
            pass

    def synthesis_then_pause(**kwargs):
        result = original_synthesis(**kwargs)
        duplicate_review.set()
        synthesis_finished.set()
        return result

    def audited(**kwargs):
        audit_started.set()
        return original_audit(**kwargs)

    monkeypatch.setattr(store, "has_duplicate_review", duplicate_review.is_set)
    monkeypatch.setattr(resume_app, "extension_worker_event", ObservedWorkerSignal())
    monkeypatch.setattr(resume_app, "generate_final_synthesis_from_analysis", synthesis_then_pause)
    monkeypatch.setattr(resume_app, "generate_resume_quality_audit", audited)

    worker = threading.Thread(target=resume_app.run_extension_generation_task, args=(task,))
    worker.start()

    assert synthesis_finished.wait(timeout=2)
    assert audit_gate_waiting.wait(timeout=2)
    assert not audit_started.is_set()

    duplicate_review.clear()
    release_gate.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert audit_started.is_set()
    assert store.get(draft["id"])["audit_status"] == "approved"


def test_duplicate_creation_wins_gate_before_ai_stage_reservation(monkeypatch):
    create_entered = threading.Event()
    release_create = threading.Event()
    ai_started = threading.Event()
    wake_event = threading.Event()

    class GateStore:
        duplicate_pending = False

        def create(self, context, snapshot, duplicate_count):
            create_entered.set()
            assert release_create.wait(timeout=2)
            self.duplicate_pending = bool(duplicate_count)
            return {"id": "duplicate-draft"}

        def has_duplicate_review(self):
            return self.duplicate_pending

    store = GateStore()
    monkeypatch.setattr(resume_app, "extension_drafts", store)
    monkeypatch.setattr(resume_app, "extension_worker_event", wake_event)

    create_thread = threading.Thread(
        target=resume_app.create_extension_draft_with_gate,
        args=({}, {}, 1),
    )
    create_thread.start()
    assert create_entered.wait(timeout=2)

    ai_thread = threading.Thread(
        target=resume_app.run_extension_ai_stage,
        args=(lambda: ai_started.set(),),
    )
    ai_thread.start()
    assert not ai_started.wait(timeout=0.1)

    release_create.set()
    create_thread.join(timeout=2)
    assert not create_thread.is_alive()
    assert not ai_started.wait(timeout=0.1)

    store.duplicate_pending = False
    wake_event.set()
    ai_thread.join(timeout=2)
    assert not ai_thread.is_alive()
    assert ai_started.is_set()


def test_ai_stage_reservation_wins_without_holding_gate_for_network_call(monkeypatch):
    ai_started = threading.Event()
    release_ai = threading.Event()
    create_finished = threading.Event()

    class GateStore:
        duplicate_pending = False

        def create(self, context, snapshot, duplicate_count):
            self.duplicate_pending = bool(duplicate_count)
            create_finished.set()
            return {"id": "duplicate-draft"}

        def has_duplicate_review(self):
            return self.duplicate_pending

    store = GateStore()
    monkeypatch.setattr(resume_app, "extension_drafts", store)

    def network_call():
        ai_started.set()
        assert release_ai.wait(timeout=2)

    ai_thread = threading.Thread(
        target=resume_app.run_extension_ai_stage,
        args=(network_call,),
    )
    ai_thread.start()
    assert ai_started.wait(timeout=2)

    create_thread = threading.Thread(
        target=lambda: resume_app.create_extension_draft_with_gate({}, {}, 1),
    )
    create_thread.start()
    assert create_finished.wait(timeout=2)
    assert ai_thread.is_alive()

    release_ai.set()
    ai_thread.join(timeout=2)
    create_thread.join(timeout=2)
    assert not ai_thread.is_alive()
    assert not create_thread.is_alive()


def test_pdf_rejects_stale_audit():
    with pytest.raises(resume_app.ExtensionPdfAuditConflict, match="Run or resolve"):
        resume_app.generate_extension_pdf({
            "audit_status": "stale",
            "status": "ready",
            "resume_content": "Generated resume",
        })


@pytest.mark.parametrize(
    "audit_status",
    [
        "not_started",
        "running",
        "reviewing",
        "changes_suggested",
        "manual_attention",
        "technical_failed",
        "stale",
    ],
)
def test_extension_pdf_api_rejects_unresolved_audits_before_pdf_work(tmp_path, monkeypatch, audit_status):
    store = pipeline_store(tmp_path, monkeypatch)
    draft = ready_pdf_draft(store, audit_status)
    output_dir = tmp_path / "pdf-output"
    monkeypatch.setitem(resume_app.settings, "output_directory", str(output_dir))
    monkeypatch.setattr(resume_app, "draft_resume_snapshot", lambda _draft: pytest.fail("resume snapshot must not be built"))
    monkeypatch.setattr(resume_app, "validate_updated_content", lambda _content: pytest.fail("resume validation must not run"))
    monkeypatch.setattr(resume_app, "build_resume_docx", lambda *_args, **_kwargs: pytest.fail("PDF builder must not run"))
    monkeypatch.setattr(resume_app, "start_pdf_conversion", lambda *_args, **_kwargs: pytest.fail("PDF conversion must not start"))
    monkeypatch.setattr(store, "materialize_pdf", lambda *_args, **_kwargs: pytest.fail("trusted PDF materialization must not run"))

    response = resume_app.app.test_client().post(f"/api/extension/drafts/{draft['id']}/pdf")

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["audit_status"] == audit_status
    assert "Run or resolve the resume quality review" in payload["error"]
    assert not output_dir.exists()
    preserved = store.get(draft["id"])
    assert preserved["status"] == "ready"
    assert preserved["audit_status"] == audit_status


@pytest.mark.parametrize("audit_status", ["approved", "applied", "kept_current"])
def test_extension_pdf_api_allows_resolved_audits(tmp_path, monkeypatch, audit_status):
    store = pipeline_store(tmp_path, monkeypatch)
    draft = ready_pdf_draft(store, audit_status)
    output_dir = tmp_path / "pdf-output"
    calls = []
    monkeypatch.setitem(resume_app.settings, "output_directory", str(output_dir))
    monkeypatch.setattr(resume_app, "draft_resume_snapshot", lambda _draft: {"title": "Backend Engineer"})
    monkeypatch.setattr(resume_app, "validate_updated_content", lambda _content: ([], []))
    monkeypatch.setattr(resume_app, "build_resume_docx", lambda *_args, **_kwargs: calls.append("builder"))
    monkeypatch.setattr(resume_app, "start_pdf_conversion", lambda *_args, **_kwargs: calls.append("conversion"))

    response = resume_app.app.test_client().post(f"/api/extension/drafts/{draft['id']}/pdf")

    assert response.status_code == 200
    assert calls == ["builder", "conversion"]
    updated = response.get_json()["draft"]
    assert updated["status"] == "pdf_generating"
    assert updated["audit_status"] == audit_status


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (KeyError("missing"), 404),
        (AuditStaleError("stale"), 409),
        (ValueError("invalid"), 400),
    ],
)
def test_audit_api_status_mappings(monkeypatch, error, expected):
    monkeypatch.setattr(resume_app, "run_extension_draft_audit", lambda _draft_id: (_ for _ in ()).throw(error))
    response = resume_app.app.test_client().post("/api/extension/drafts/draft-1/audit")
    assert response.status_code == expected


def test_audit_resolve_endpoint_passes_explicit_decisions(monkeypatch):
    captured = {}

    def resolve(draft_id, decisions):
        captured.update({"draft_id": draft_id, "decisions": decisions})
        return {"id": draft_id, "audit_status": "applied", "resume_content": ""}

    monkeypatch.setattr(resume_app, "resolve_extension_draft_audit", resolve)

    response = resume_app.app.test_client().post(
        "/api/extension/drafts/draft-1/audit/resolve",
        json={"decisions": {"updated_summary": "accept"}},
    )

    assert response.status_code == 200
    assert captured == {
        "draft_id": "draft-1",
        "decisions": {"updated_summary": "accept"},
    }


def test_opening_editor_does_not_apply_pending_audit(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft = ready_pdf_draft(store, "not_started")
    running = store.start_audit(draft["id"])
    pending = store.save_audit_result(
        draft["id"],
        {
            "schema_version": "2",
            "decision": "changes_suggested",
            "overall_score": 84,
            "review_summary": "One title change is recommended.",
            "component_scores": {},
            "manual_findings": [],
            "changes": {
                **resume_app._empty_resume_quality_audit_changes(),
                "top_title": {
                    "change_id": "title.market-standard",
                    "suggested": "Backend Engineer",
                    "reason": "Use a common market title.",
                    "evidence_refs": ["upstream.mckinsey.title"],
                },
            },
            "review_groups": [{
                "change_id": "title.market-standard",
                "section": "top_title",
                "current": "Software Engineer",
                "proposed": "Backend Engineer",
                "reason": "Use a common market title.",
            }],
        },
        "hash-1",
        draft["resume_revision"],
        running["audit_result"]["run_token"],
    )
    monkeypatch.setattr(resume_app, "draft_resume_snapshot", lambda _draft: {"title": "Backend Engineer"})

    response = resume_app.app.test_client().post(
        f"/api/extension/drafts/{draft['id']}/editor-session"
    )

    assert response.status_code == 200
    preserved = store.get(draft["id"])
    assert preserved["audit_status"] == "changes_suggested"
    assert preserved["audit_proposal"] == pending["audit_proposal"]
    assert preserved["resume_revision"] == pending["resume_revision"]


def test_regenerate_api_conflicts_with_active_task_and_preserves_checkpoint(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    store.checkpoint(task["task_id"], draft["id"], "core", {
        "status": "generating_core",
        "analysis": {"target_role": "Backend Engineer"},
        "resume_content": "Partial checkpoint",
    })

    response = resume_app.app.test_client().post(
        f"/api/extension/drafts/{draft['id']}/regenerate",
        json={"context": {**draft, "company_name": "Changed"}},
    )

    assert response.status_code == 409
    assert "already queued or generating" in response.get_json()["error"]
    preserved = store.get(draft["id"])
    assert preserved["status"] == "generating_core"
    assert preserved["analysis"] == {"target_role": "Backend Engineer"}
    assert preserved["resume_content"] == "Partial checkpoint"
    assert preserved["company_name"] == "Acme"

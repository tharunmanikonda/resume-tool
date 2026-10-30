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
            "location": blueprint["location"] or "CA, USA",
            "dates": blueprint["dates"] or "January 2024 - Present",
            "title": "Software Engineer",
            "enabled": True,
            "source_bullets": ["PRIVATE_SAVED_BULLET"],
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
            "profile_snapshot": {"name": "Candidate", "summary": "PRIVATE_SUMMARY", "skills": ["PRIVATE_SKILL"]},
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
    monkeypatch.setattr(resume_app, "classify_resume_job", lambda *_args: {"category": "software_engineering", "suitable": True})
    analysis = {
        "target_role": "Backend Engineer",
        "target_work": {"system_type": "Backend services", "primary_workflow": "Build and operate services",
                        "engineering_changes": ["Implement services"], "evidence_expectations": ["Service implementation"]},
        "role_family": "backend application engineering",
        "skill_category_order_key": "backend_application",
        "prompt_family_key": "software_engineering",
        "skills_mentioned": ["Python"],
    }
    preliminary = {"updated_skills": [{"category": "Programming Languages", "items": ["Python", "Java"]}]}

    def analyze(**_kwargs):
        calls.append(("analysis", None))
        return analysis

    mechanisms = [
        "Implement request validation with typed REST contracts",
        "Reduce database round trips through batched query execution",
        "Add regression tests for error handling and compatibility",
        "Instrument service dashboards to isolate slow requests",
        "Automate staged deployments with health checks",
        "Resolve concurrency failures through idempotent message consumption",
        "Improve form accessibility with keyboard navigation",
        "Isolate infrastructure changes through deployment configuration checks",
        "Document incident recovery procedures and service dependencies",
        "Harden authentication boundaries using token validation",
        "Tune process scheduling to reduce queue contention",
    ]
    def generate(stage, schema, prompt, inputs):
        calls.append((stage, copy.deepcopy(inputs)))
        assert "source_bullets" not in str(inputs)
        assert "PRIVATE_" not in str(inputs)
        roles = inputs["employment_headings_only"]
        if stage == "targeting":
            return {"decision": "aligned", "corrections": [], "assessment": {
                "level_scope": "Feature-level IC", "team_path": "Backend services", "choice_basis": "conservative_assumption",
                "primary_focus": [{"source_clause_id": "jd_1", "focus": "Build Python APIs"}],
                "secondary_focus": [], "excluded_paths": [], "rationale": "Backend implementation scope"}}
        if stage == "plan":
            return {"role_positioning": "Backend Engineer", "target_system": "Backend APIs",
                    "target_workflow": "Implement reliable request handling",
                    "required": [{"capability": "Python APIs", "jd_quote": "Build reliable Python APIs"}],
                    "optional": [], "unknowns": ["Product"],
                    "experience": {r["key"]: {"system": "Proposed request service", "workflow": "Build and test requests",
                        "scope": "Module implementation", "assumptions": ["Proposed system"],
                        "contributions": mechanisms[:r["bullet_min"]]} for r in roles}}
        if stage == "core":
            skills = preliminary["updated_skills"]
            if 'Programming Languages' not in inputs['ordered_skill_categories']:
                skills = [{'category': inputs['ordered_skill_categories'][0], 'items': ['HPE ProLiant', 'Dell PowerEdge']}]
            return {"headline": "Backend Engineer", "summary": "Backend engineer building reliable Python systems.",
                    "skills": skills}
        if stage == "experience":
            assert inputs['core_sections']['headline'] == 'Backend Engineer'
            return {"headline": "Backend Engineer", "summary": "Backend engineer building reliable Python systems.",
                    "skills": preliminary["updated_skills"],
                    "experience": {r["key"]: {"bullets": [{"contribution_number": i+1,
                        "text": contribution + " across a workload of 500 requests, checking expected responses and failure cases during integration testing before releasing changes to shared service environments.",
                        "measurement": {"kind": "scale", "value": "500", "unit": "requests",
                                        "context": "Illustrative test workload", "status": "illustrative_unverified"}}
                        for i, contribution in enumerate(mechanisms[:r["bullet_min"]])]} for r in roles}}
        if audit_error:
            raise audit_error
        return {"summary": "Writing review complete.", "ready_for_assumption_review": True, "findings": []}

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "analyze_job_description", analyze)
    monkeypatch.setattr(resume_app, "_jd_experiment_call", generate)
    monkeypatch.setattr(resume_app, "generate_skills_from_analysis", lambda **kwargs: pytest.fail("source skills generator used"))
    monkeypatch.setattr(resume_app, "generate_experience_subset_from_analysis", lambda **kwargs: pytest.fail("source bullet generator used"))
    monkeypatch.setattr(resume_app, "draft_resume_snapshot", lambda draft: {"title": draft["title_summary"]["updated_title"]})
    return preliminary


@pytest.mark.parametrize('edit_during_review', [False, True])
def test_jd_retry_review_repairs_and_saves_atomically(tmp_path, monkeypatch, edit_during_review):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    install_pipeline_mocks(monkeypatch, [])
    resume_app.run_extension_generation_task(task)
    before = store.get(draft['id'])
    stages = []
    def generate(stage, schema, prompt, inputs):
        stages.append(stage)
        assert stage == 'review'
        assert 'PRIVATE_' not in str(inputs)
        if edit_during_review:
            store.update(draft['id'], {'title_summary': {'updated_title': 'User Edited Title', 'updated_summary': before['title_summary']['updated_summary']}}, invalidate_pdf=True)
        return {'summary': 'Title corrected',
                'findings': [{'target_id': 'headline', 'severity': 'repair', 'issue': 'Use standard positioning', 'change_indices': [1]}],
                'changes': [{'target': 'headline', 'old_text': inputs['assembled_draft']['headline'], 'replacement': 'Backend Software Engineer'}]}
    monkeypatch.setattr(resume_app, '_jd_experiment_call', generate)
    if edit_during_review:
        with pytest.raises(AuditStaleError):
            resume_app.run_extension_draft_audit(draft['id'])
        assert store.get(draft['id'])['title_summary']['updated_title'] == 'User Edited Title'
    else:
        result = resume_app.run_extension_draft_audit(draft['id'])
        assert result['audit_status'] == 'approved'
        assert result['title_summary']['updated_title'] == 'Backend Software Engineer'
        assert result['resume_revision'] == before['resume_revision'] + 1
        assert result['audit_base_revision'] == result['resume_revision']
        assert result['resume_versions']['original'] == before['resume_versions']['original']
        assert result['active_resume_version'] == 'luna_reviewed'
    assert stages == ['review']


def test_data_center_worker_classifies_before_generation_and_keeps_hpe(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    task["draft"] = store.update(draft["id"], {
        "profile_snapshot": {"name": "Candidate", "contact": {"location": "Dallas, TX"}},
    })
    calls = []
    install_pipeline_mocks(monkeypatch, calls)

    def classify(*_args):
        calls.append(("classification", None))
        return {"category": "data_center_infrastructure", "suitable": True}

    monkeypatch.setattr(resume_app, "classify_resume_job", classify)
    resume_app.run_extension_generation_task(task)
    completed = store.get(draft["id"])
    assert completed["status"] == "ready", completed["error_message"]
    assert calls[0][0] == "classification"
    assert completed["analysis"]["prompt_family_key"] == "data_center_infrastructure"
    assert completed["source_metadata"]["job_fit"]["category"] == "data_center_infrastructure"
    history = completed["experience_history_snapshot"]
    assert len(history) == 1
    assert history[0]["company"] == "HPE"
    assert history[0]["dates"] == "February 2024 - Present"
    assert completed["enabled_experience_keys"] == [history[0]["key"]]
    assert len(completed["experience_recent"]["experience"]) == 1
    assert completed["experience_older"]["experience"] == {}


def test_worker_uses_shared_jd_only_workflow_and_saves_normal_versions(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    calls = []
    preliminary = install_pipeline_mocks(monkeypatch, calls)

    resume_app.run_extension_generation_task(task)

    assert [name for name, _payload in calls] == ["analysis", "plan", "targeting", "core", "experience", "review"], store.get(draft["id"])["error_message"]
    assert set(calls[-1][1]["assembled_draft"]["experience"]) == set(draft["enabled_experience_keys"])
    completed = store.get(draft["id"])
    assert completed["status"] == "ready", completed["error_message"]
    assert completed["audit_status"] == "approved"


def test_retry_uses_persisted_jd_plan_and_regenerate_discards_it(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    calls = []
    install_pipeline_mocks(monkeypatch, calls)
    original = resume_app._jd_experiment_call
    fail_once = True
    def interrupted(stage, schema, prompt, inputs):
        nonlocal fail_once
        if stage == 'experience' and fail_once:
            fail_once = False
            raise resume_app.AIStageError('jd_draft', 'max_output_tokens')
        return original(stage, schema, prompt, inputs)
    monkeypatch.setattr(resume_app, '_jd_experiment_call', interrupted)
    resume_app.run_extension_generation_task(task)
    failed = store.get(draft['id'])
    assert failed['status'] == 'failed'
    assert failed['error_stage'] == 'jd_draft'
    assert failed['source_metadata']['jd_only_checkpoint']['plan']
    assert [stage for stage, _ in calls].count('plan') == 1
    store.retry(draft['id'])
    resume_app.run_extension_generation_task(store.next_task())
    completed = store.get(draft['id'])
    assert completed['status'] == 'ready', completed['error_message']
    assert [stage for stage, _ in calls].count('plan') == 1
    assert completed['source_metadata']['jd_only_checkpoint']['draft']
    regenerated = store.regenerate(draft['id'])
    assert 'jd_only_checkpoint' not in regenerated['source_metadata']


def test_mcp_jd_analysis_enriches_context_and_is_reused_after_duplicate_decision(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    history = [
        {
            "key": blueprint["key"],
            "company": blueprint["company"],
            "location": blueprint["location"] or "CA, USA",
            "dates": blueprint["dates"] or "January 2024 - Present",
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
    assert completed["status"] == "ready", completed["error_message"]
    assert [name for name, _payload in calls].count("analysis") == 1


def test_audit_failure_preserves_ready_resume(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    calls = []
    install_pipeline_mocks(monkeypatch, calls, audit_error=RuntimeError("audit unavailable"))

    resume_app.run_extension_generation_task(task)

    completed = store.get(draft["id"])
    assert completed["status"] == "ready", completed["error_message"]
    assert completed["resume_content"].startswith("Updated Title")
    assert completed["audit_status"] == "technical_failed"
    assert "audit unavailable" in completed["audit_result"]["error"]


def test_duplicate_review_does_not_block_quality_audit_stage(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    calls = []
    install_pipeline_mocks(monkeypatch, calls)
    audit_started = threading.Event()
    original_call = resume_app._jd_experiment_call

    def audited(stage, schema, prompt, inputs):
        if stage == "review":
            audit_started.set()
        return original_call(stage, schema, prompt, inputs)

    monkeypatch.setattr(store, "has_duplicate_review", lambda: True)
    monkeypatch.setattr(resume_app, "_jd_experiment_call", audited)

    resume_app.run_extension_generation_task(task)

    assert audit_started.is_set()
    assert store.get(draft["id"])["audit_status"] == "approved"


def test_duplicate_creation_does_not_block_ai_stage(monkeypatch):
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
    assert ai_started.wait(timeout=0.1)

    release_create.set()
    create_thread.join(timeout=2)
    ai_thread.join(timeout=2)
    assert not create_thread.is_alive()
    assert not ai_thread.is_alive()


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


def test_ai_stage_retries_transient_network_failure(monkeypatch):
    attempts = {"count": 0}
    sleeps = []
    monkeypatch.setenv("EXTENSION_AI_STAGE_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("EXTENSION_AI_STAGE_RETRY_BASE_SECONDS", "0.01")
    monkeypatch.setattr(resume_app.time, "sleep", lambda seconds: sleeps.append(seconds))

    def flaky_call():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError(
                "OpenAI API request failed: [Errno 8] nodename nor servname provided, or not known"
            )
        return {"ok": True}

    assert resume_app.run_extension_ai_stage(flaky_call) == {"ok": True}
    assert attempts["count"] == 2
    assert sleeps == [0.01]


def test_validation_mentioning_timeout_is_not_retried_as_network_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(resume_app.time, 'sleep', lambda *_: pytest.fail('validation must not sleep/retry'))
    def invalid_content():
        calls.append(True)
        raise resume_app.AIStageError('experience_generation', "Skills: clarify 'retry / timeout handling'", validation=True)
    with pytest.raises(resume_app.AIStageError):
        resume_app.run_extension_ai_stage(invalid_content)
    assert len(calls) == 1


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


def test_identical_editor_save_keeps_inflight_review_revision(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    install_pipeline_mocks(monkeypatch, [])
    resume_app.run_extension_generation_task(task)
    ready = store.get(draft['id'])
    running = store.start_audit(draft['id'])
    monkeypatch.setattr(resume_app, 'profile_for_resume_mode', lambda *a, **kw: pytest.fail('Same-mode save refreshed profile'))
    monkeypatch.setattr(resume_app, 'identity_profile_by_id', lambda *a: {'id': running['identity_id'], 'email': 'new-global@example.com'})
    resume_app.update_extension_draft_service(draft['id'], {
        'resume_content': running['resume_content'], 'company_name': running['company_name'],
        'identity_id': running['identity_id'], 'resume_mode': running['resume_mode'],
        'enabled_experience_keys': running['enabled_experience_keys'],
        'experience_history': running['experience_history_snapshot'],
    })
    saved = store.get(draft['id'])
    assert saved['resume_revision'] == ready['resume_revision']
    assert saved['audit_status'] == 'running'
    assert saved['contact_snapshot'] == ready['contact_snapshot']
    result = store.save_audit_result(draft['id'], {'schema_version': '2', 'decision': 'approved', 'changes': {}},
        'reviewed-hash', running['resume_revision'], running['audit_result']['run_token'])
    assert result['audit_status'] == 'approved'


def test_planned_experience_titles_persist_without_rewriting_profile(tmp_path, monkeypatch):
    store = pipeline_store(tmp_path, monkeypatch)
    draft, task = queued_task(store)
    install_pipeline_mocks(monkeypatch, [])
    generate = resume_app._jd_experiment_call
    expected = {'mckinsey': 'Salesforce Developer', 'uber': 'Software Engineer',
                'kpmg': 'Java Developer', 'trigent': 'Frontend Developer'}
    def with_titles(stage, schema, prompt, inputs):
        result = generate(stage, schema, prompt, inputs)
        if stage == 'plan':
            for key, entry in result['experience'].items():
                entry['title'] = expected[key]
        return result
    monkeypatch.setattr(resume_app, '_jd_experiment_call', with_titles)
    original_history = copy.deepcopy(draft['experience_history_snapshot'])
    resume_app.run_extension_generation_task(task)
    saved = store.get(draft['id'])
    assert saved['audit_status'] == 'approved'
    for key, title in expected.items():
        group = 'experience_recent' if key in {'mckinsey', 'uber'} else 'experience_older'
        assert saved[group]['experience'][key]['title'] == title
        assert title in saved['resume_content']
        assert saved['resume_versions']['luna_reviewed']['resume']['experience'][key]['title'] == title
    assert saved['experience_history_snapshot'] == original_history
    resume_app.update_extension_draft_service(draft['id'], {'resume_content': saved['resume_content']})
    reopened = store.get(draft['id'])
    assert reopened['experience_recent']['experience']['mckinsey']['title'] == 'Salesforce Developer'

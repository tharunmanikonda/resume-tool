import copy

import pytest

import app as resume_app


ANALYSIS = {
    "target_role": "Backend Engineer",
    "role_family": "backend application engineering",
    "skill_category_order_key": "backend_application",
    "prompt_family_key": "software_engineering",
    "core_problem": "Build reliable backend services",
    "top_requirements": ["Python", "FastAPI", "PostgreSQL"],
    "skills_mentioned": [
        "Python",
        "Java",
        "FastAPI",
        "Spring Boot",
        "PostgreSQL",
        "Redis",
        "AWS",
        "Docker",
        "OpenTelemetry",
        "Grafana",
        "GitHub Actions",
        "Terraform",
    ],
}

SUMMARY = (
    "Backend engineer with experience building APIs, operational tools, and reliable data workflows "
    "across enterprise and product environments. Delivered Python and FastAPI services, PostgreSQL "
    "integrations, cloud deployments, observability improvements, and automated testing that made "
    "systems easier to operate. Work spans customer-facing delivery and internal platforms, with a "
    "practical focus on measurable outcomes, clear technical decisions, and dependable execution. "
    "Brings transferable system design and collaboration skills to complex software problems without "
    "overstating industry-specific background."
)

SKILLS = {
    "updated_skills": [
        {"category": "Programming Languages", "items": ["Python", "Java"]},
        {"category": "Backend Engineering", "items": ["FastAPI", "Spring Boot"]},
        {"category": "Data & Storage", "items": ["PostgreSQL", "Redis"]},
        {"category": "Cloud & Infrastructure", "items": ["AWS", "Docker"]},
        {"category": "Observability & Reliability", "items": ["OpenTelemetry", "Grafana"]},
        {"category": "DevOps & CI/CD", "items": ["GitHub Actions", "Terraform"]},
    ]
}


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch):
    resume_app.ai_sessions.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    yield
    resume_app.ai_sessions.clear()


@pytest.fixture
def one_blueprint(monkeypatch):
    blueprint = dict(resume_app.EXPERIENCE_BLUEPRINTS[0])
    blueprint["bullet_min"] = 2
    blueprint["bullet_max"] = 2
    monkeypatch.setattr(resume_app, "current_experience_blueprints", lambda: [copy.deepcopy(blueprint)])
    return blueprint


def scores():
    return {
        "ats_alignment": 90,
        "technical_credibility": 92,
        "human_tone": 88,
        "career_coherence": 91,
        "evidence_quality": 93,
    }


def canonical_resume(blueprint):
    return {
        "updated_title": "Backend Software Engineer",
        "updated_summary": SUMMARY,
        "updated_skills": copy.deepcopy(SKILLS["updated_skills"]),
        "experience": {
            blueprint["key"]: {
                "title": "Software Engineer",
                "bullets": [
                    (
                        "Built FastAPI services that improved workflow reliability by 20% across "
                        "enterprise delivery teams while strengthening deployment checks and operational support."
                    ),
                    (
                        "Delivered PostgreSQL integrations with AWS deployment automation for dependable "
                        "customer-facing systems, clearer data flows, and more consistent release validation."
                    ),
                ],
            }
        },
    }


def completed_session(blueprint):
    session_id, session = resume_app.get_ai_session(None, "Build reliable Python APIs.", False)
    session["analysis"] = copy.deepcopy(ANALYSIS)
    session["enabled_experience_keys"] = [blueprint["key"]]
    resume_app.update_ai_session_structured_resume(
        session,
        canonical_resume(blueprint),
        [blueprint],
    )
    return session_id, session


def approved_audit(current):
    return {
        "schema_version": "2",
        "decision": "approved",
        "overall_score": 91,
        "review_summary": "The resume is credible, focused, and easy to scan.",
        "component_scores": scores(),
        "manual_findings": [],
        "changes": resume_app._empty_resume_quality_audit_changes(),
        "review_groups": [],
        "withheld_changes": [],
        "base_hash": resume_app.canonical_json_hash(current),
    }


def changes_audit(current, blueprint):
    changes = resume_app._empty_resume_quality_audit_changes()
    changes["top_title"] = {
        "change_id": "title.market-standard",
        "suggested": "Backend Engineer",
        "reason": "Use the common market title used by the target role.",
        "evidence_refs": [f"upstream.{blueprint['key']}.title"],
    }
    raw = {
        "schema_version": "2",
        "decision": "changes_suggested",
        "overall_score": 86,
        "review_summary": "One focused title change will improve alignment.",
        "component_scores": scores(),
        "manual_findings": [],
        "changes": changes,
    }
    return resume_app.validate_resume_quality_audit_result(
        raw,
        current_resume=current,
        analysis_payload=ANALYSIS,
        active_blueprints=[blueprint],
    )


def test_new_session_initializes_main_audit_fields():
    _session_id, session = resume_app.get_ai_session(None, "Build APIs.", False)

    assert session["resume_revision"] == 1
    assert session["resume_content"] == ""
    assert session["audit_status"] == "not_started"
    assert session["audit_result"] is None
    assert session["audit_proposal"] is None
    assert session["audit_base_revision"] is None
    assert session["audit_base_hash"] is None
    assert session["audit_created_at"] is None
    assert session["audit_applied_at"] is None


def test_experience_endpoint_needs_analysis_and_preliminary_skills_not_title_summary(
    monkeypatch,
    one_blueprint,
):
    session_id, session = resume_app.get_ai_session(None, "Build APIs.", False)
    session["analysis"] = copy.deepcopy(ANALYSIS)
    session["skills"] = copy.deepcopy(SKILLS)
    session["enabled_experience_keys"] = [one_blueprint["key"]]
    captured = {}

    def generate(**kwargs):
        captured.update(kwargs)
        return {
            "experience": {
                one_blueprint["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable Python APIs.", "Improved service operations by 20%."],
                }
            }
        }

    monkeypatch.setattr(resume_app, "generate_experience_subset_from_analysis", generate)
    monkeypatch.setattr(resume_app, "validate_experience_subset_payload_with_analysis", lambda *_args: [])

    response = resume_app.app.test_client().post(
        "/api/ai/generate-experience-recent",
        json={"session_id": session_id, "enabled_experience_keys": [one_blueprint["key"]]},
    )

    assert response.status_code == 200
    assert captured["preliminary_skills_payload"] == SKILLS
    assert "core_payload" not in captured
    assert session["title_summary"] is None


def test_final_synthesis_consumes_complete_experience_and_stores_output(
    monkeypatch,
    one_blueprint,
):
    session_id, session = resume_app.get_ai_session(None, "Raw JD text", False)
    session.update({
        "analysis": copy.deepcopy(ANALYSIS),
        "skills": copy.deepcopy(SKILLS),
        "enabled_experience_keys": [one_blueprint["key"]],
        "experience_recent": {
            "experience": {
                one_blueprint["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable Python APIs.", "Improved service operations by 20%."],
                }
            }
        },
        "experience_older": {"experience": {}},
        "audit_status": "approved",
        "audit_result": {"decision": "approved"},
    })
    captured = {}

    def synthesize(**kwargs):
        captured.update(copy.deepcopy(kwargs))
        return {
            "updated_title": "Backend Software Engineer",
            "updated_summary": SUMMARY,
            "updated_skills": copy.deepcopy(SKILLS["updated_skills"]),
            "experience_titles": {one_blueprint["key"]: "Backend Software Engineer"},
        }

    monkeypatch.setattr(resume_app, "generate_final_synthesis_from_analysis", synthesize)
    monkeypatch.setattr(resume_app, "validate_final_synthesis_payload", lambda *_args: [])

    response = resume_app.app.test_client().post(
        "/api/ai/final-synthesis",
        json={"session_id": session_id},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert captured["job_description"] == "Raw JD text"
    assert one_blueprint["key"] in captured["combined_experience_payload"]["experience"]
    assert session["title_summary"]["updated_title"] == "Backend Software Engineer"
    assert session["experience_recent"]["experience"][one_blueprint["key"]]["title"] == "Backend Software Engineer"
    assert payload["content"] == session["resume_content"]
    assert payload["resume"]["updated_skills"] == SKILLS["updated_skills"]
    assert session["audit_status"] == "not_started"
    assert session["audit_result"] is None


def test_final_synthesis_advances_revision_once_when_replacing_finalized_resume(
    monkeypatch,
    one_blueprint,
):
    session_id, session = completed_session(one_blueprint)
    before_revision = session["resume_revision"]

    monkeypatch.setattr(
        resume_app,
        "generate_final_synthesis_from_analysis",
        lambda **_kwargs: {
            "updated_title": "Senior Backend Software Engineer",
            "updated_summary": SUMMARY,
            "updated_skills": copy.deepcopy(SKILLS["updated_skills"]),
            "experience_titles": {one_blueprint["key"]: "Software Engineer"},
        },
    )
    monkeypatch.setattr(resume_app, "validate_final_synthesis_payload", lambda *_args: [])

    client = resume_app.app.test_client()
    first_response = client.post(
        "/api/ai/final-synthesis",
        json={"session_id": session_id},
    )
    second_response = client.post(
        "/api/ai/final-synthesis",
        json={"session_id": session_id},
    )

    assert first_response.status_code == 200
    assert first_response.get_json()["resume_revision"] == before_revision + 1
    assert second_response.status_code == 200
    assert second_response.get_json()["resume_revision"] == before_revision + 1
    assert session["title_summary"]["updated_title"] == "Senior Backend Software Engineer"


def test_edited_content_updates_structured_audit_input_and_keeps_current_review(
    monkeypatch,
    one_blueprint,
):
    session_id, session = completed_session(one_blueprint)
    session["audit_status"] = "approved"
    before_revision = session["resume_revision"]
    edited = canonical_resume(one_blueprint)
    edited["updated_title"] = "Senior Backend Software Engineer"
    edited_content = resume_app.format_generated_resume_text(edited, [one_blueprint])

    changed = resume_app.accept_ai_session_resume_content(
        session,
        edited_content,
        [one_blueprint],
    )
    assert changed is True
    assert session["resume_revision"] == before_revision + 1
    assert session["audit_status"] == "kept_current"

    captured = {}

    def audit(**kwargs):
        captured.update(copy.deepcopy(kwargs))
        return approved_audit(kwargs["current_resume"])

    monkeypatch.setattr(resume_app, "generate_resume_quality_audit", audit)
    response = resume_app.app.test_client().post(
        "/api/ai/quality-audit",
        json={
            "session_id": session_id,
            "enabled_experience_keys": [one_blueprint["key"]],
            "current_resume_content": edited_content,
        },
    )

    assert response.status_code == 200
    assert captured["current_resume"]["updated_title"] == "Senior Backend Software Engineer"
    assert session["resume_revision"] == before_revision + 1
    assert session["audit_status"] == "approved"


def test_identical_manual_content_does_not_increment_revision(one_blueprint):
    _session_id, session = completed_session(one_blueprint)
    before_revision = session["resume_revision"]

    changed = resume_app.accept_ai_session_resume_content(
        session,
        session["resume_content"],
        [one_blueprint],
    )

    assert changed is False
    assert session["resume_revision"] == before_revision


@pytest.mark.parametrize("decision", ["approved", "changes_suggested", "manual_attention"])
def test_audit_decision_persists(monkeypatch, one_blueprint, decision):
    session_id, session = completed_session(one_blueprint)
    current = resume_app.ai_session_canonical_resume(session, [one_blueprint])
    result = approved_audit(current)
    result["decision"] = decision
    if decision == "changes_suggested":
        result = changes_audit(current, one_blueprint)
    elif decision == "manual_attention":
        result["decision"] = "manual_attention"
        result["manual_findings"] = [{
            "id": "blocked-1",
            "severity": "error",
            "path": "updated_summary",
            "problem": "Evidence is insufficient.",
            "recommendation": "Keep the current evidence.",
            "evidence_refs": [],
        }]
    monkeypatch.setattr(resume_app, "generate_resume_quality_audit", lambda **_kwargs: copy.deepcopy(result))

    response = resume_app.app.test_client().post(
        "/api/ai/quality-audit",
        json={"session_id": session_id, "enabled_experience_keys": [one_blueprint["key"]]},
    )

    assert response.status_code == 200
    expected_status = "applied" if decision == "changes_suggested" else decision
    assert session["audit_status"] == expected_status
    assert session["audit_proposal"] is None
    if decision == "changes_suggested":
        assert session["audit_result"]["auto_applied"] is True
        assert session["active_resume_version"] == "luna_reviewed"
        assert set(session["resume_versions"]) == {"original", "luna_reviewed"}


def test_audit_failure_preserves_current_resume(monkeypatch, one_blueprint):
    session_id, session = completed_session(one_blueprint)
    before_content = session["resume_content"]
    before_resume = resume_app.ai_session_canonical_resume(session, [one_blueprint])
    monkeypatch.setattr(
        resume_app,
        "generate_resume_quality_audit",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )

    response = resume_app.app.test_client().post(
        "/api/ai/quality-audit",
        json={"session_id": session_id, "enabled_experience_keys": [one_blueprint["key"]]},
    )

    assert response.status_code == 500
    assert session["resume_content"] == before_content
    assert resume_app.ai_session_canonical_resume(session, [one_blueprint]) == before_resume
    assert session["audit_status"] == "technical_failed"
    assert session["audit_result"]["decision"] == "technical_failed"
    assert session["audit_result"]["error"] == "audit unavailable"
    assert session["audit_result"]["model"] == "gpt-5.6-luna"
    assert session["audit_result"]["reasoning_effort"] == "medium"
    assert session["audit_result"]["attempt_count"] == 1


def test_apply_increments_revision_once_and_does_not_mutate_audit_input(one_blueprint):
    session_id, session = completed_session(one_blueprint)
    current = resume_app.ai_session_canonical_resume(session, [one_blueprint])
    result = changes_audit(current, one_blueprint)
    before_result = copy.deepcopy(result)
    base_revision = session["resume_revision"]
    session.update({
        "audit_status": "changes_suggested",
        "audit_result": result,
        "audit_proposal": copy.deepcopy(result["changes"]),
        "audit_base_revision": base_revision,
        "audit_base_hash": result["base_hash"],
    })

    response = resume_app.app.test_client().post(
        "/api/ai/quality-audit/apply",
        json={"session_id": session_id, "expected_base_hash": result["base_hash"]},
    )

    assert response.status_code == 200
    assert session["resume_revision"] == base_revision + 1
    assert session["audit_status"] == "applied"
    assert session["audit_proposal"] is None
    assert result == before_result
    assert session["title_summary"]["updated_title"] == "Backend Engineer"
    assert session["audit_result"]["accepted_change_ids"] == ["title.market-standard"]


def test_stale_apply_returns_conflict(one_blueprint):
    session_id, session = completed_session(one_blueprint)
    current = resume_app.ai_session_canonical_resume(session, [one_blueprint])
    result = changes_audit(current, one_blueprint)
    session.update({
        "audit_status": "changes_suggested",
        "audit_result": result,
        "audit_proposal": copy.deepcopy(result["changes"]),
        "audit_base_revision": session["resume_revision"],
        "audit_base_hash": result["base_hash"],
    })
    changed = copy.deepcopy(current)
    changed["updated_title"] = "Senior Backend Software Engineer"
    resume_app.update_ai_session_structured_resume(session, changed, [one_blueprint])

    response = resume_app.app.test_client().post(
        "/api/ai/quality-audit/apply",
        json={"session_id": session_id, "expected_base_hash": result["base_hash"]},
    )

    assert response.status_code == 409
    assert session["audit_status"] == "stale"
    assert session["audit_proposal"] is None


def test_keep_current_leaves_revision_and_content_unchanged(one_blueprint):
    session_id, session = completed_session(one_blueprint)
    current = resume_app.ai_session_canonical_resume(session, [one_blueprint])
    result = changes_audit(current, one_blueprint)
    session.update({
        "audit_status": "changes_suggested",
        "audit_result": result,
        "audit_proposal": copy.deepcopy(result["changes"]),
    })
    before_revision = session["resume_revision"]
    before_content = session["resume_content"]

    response = resume_app.app.test_client().post(
        "/api/ai/quality-audit/keep-current",
        json={"session_id": session_id},
    )

    assert response.status_code == 200
    assert session["audit_status"] == "kept_current"
    assert session["audit_proposal"] is None
    assert session["resume_revision"] == before_revision
    assert session["resume_content"] == before_content


def test_regenerate_preserves_inputs_and_link_without_model_call(monkeypatch, one_blueprint):
    session_id, session = completed_session(one_blueprint)
    session["extension_draft_id"] = "draft-123"
    session["audit_status"] = "approved"
    session["audit_result"] = {"decision": "approved"}
    before_revision = session["resume_revision"]
    for name in (
        "analyze_job_description",
        "generate_skills_from_analysis",
        "generate_experience_subset_from_analysis",
        "generate_final_synthesis_from_analysis",
        "generate_resume_quality_audit",
    ):
        monkeypatch.setattr(
            resume_app,
            name,
            lambda **_kwargs: pytest.fail("regenerate must not call a model"),
        )

    response = resume_app.app.test_client().post(
        "/api/ai/regenerate",
        json={"session_id": session_id},
    )

    assert response.status_code == 200
    assert session["job_description"] == "Build reliable Python APIs."
    assert session["analysis"] == ANALYSIS
    assert session["enabled_experience_keys"] == [one_blueprint["key"]]
    assert session["extension_draft_id"] == "draft-123"
    assert session["title_summary"] is None
    assert session["skills"] is None
    assert session["experience_recent"] is None
    assert session["experience_older"] is None
    assert session["resume_content"] == ""
    assert session["audit_status"] == "not_started"
    assert session["resume_revision"] == before_revision + 1


def test_review_core_route_remains_registered():
    routes = {rule.rule for rule in resume_app.app.url_map.iter_rules()}
    assert "/api/ai/review-core" in routes


def test_quality_audit_missing_session_status_mapping():
    client = resume_app.app.test_client()

    assert client.post("/api/ai/quality-audit", json={}).status_code == 400
    assert client.post(
        "/api/ai/quality-audit",
        json={"session_id": "missing"},
    ).status_code == 404

import copy

import pytest

import app as resume_app
import data_center_resume


def test_decision_classifies_data_center_without_software_duties(monkeypatch):
    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _key: None)
    monkeypatch.setattr(resume_app, "save_cached_ai_stage_result", lambda **_kwargs: None)
    monkeypatch.setattr(resume_app, "_request_openai_json", lambda **_kwargs: {
        "answers": [
            {"type": "predicate", "name": "data_center_related", "probability": 0.98},
            {"type": "predicate", "name": "software_related", "probability": 0.10},
            {"type": "predicate", "name": "over_six_years_required", "probability": 0.01},
            {"type": "predicate", "name": "advanced_seniority_scope", "probability": 0.01},
        ],
    })
    decision = resume_app.classify_resume_job("test-key", "Install HPE servers, perform break-fix and rack-and-stack, troubleshoot Linux and cabling.")
    assert decision["suitable"] is True
    assert decision["category"] == data_center_resume.CATEGORY
    routed = resume_app.apply_resume_category({"generation_route_key": "platform_distributed"}, decision)
    assert resume_app.prompt_family_key_for_analysis(routed) == data_center_resume.CATEGORY
    assert resume_app.skill_category_order_key_for_analysis(routed) == data_center_resume.CATEGORY


def test_hpe_snapshot_is_single_entry_and_does_not_change_regular_profile():
    profile = {
        "name": "Candidate", "contact": {"location": "Dallas, TX"},
        "experience_history": [{"company": "Original"}],
        "projects": [{"name": "Software project"}],
        "certifications": ["AWS"], "education": [{"degree": "MS"}],
    }
    original = copy.deepcopy(profile)
    values = resume_app.data_center_snapshot_values(profile)
    assert profile == original
    assert values["profile_snapshot"]["name"] == "Candidate"
    assert values["profile_snapshot"]["education"] == profile["education"]
    assert values["profile_snapshot"]["certifications"] == ["AWS"]
    blueprints = resume_app.experience_blueprints_from_snapshot(values)
    assert len(blueprints) == 1
    assert blueprints[0]["company"] == "HPE"
    assert blueprints[0]["dates"] == "February 2024 - Present"
    assert blueprints[0]["bullet_min"] == 10
    assert values["enabled_experience_keys"] == [blueprints[0]["key"]]


def test_data_center_skills_pass_validator():
    analysis = resume_app.apply_resume_category(
        {"core_problem": "Maintain server infrastructure"},
        {"category": data_center_resume.CATEGORY},
    )
    skills = {"updated_skills": [
        {"category": category, "items": [category + " one", category + " two"]}
        for category in data_center_resume.SKILL_CATEGORIES
    ]}
    assert resume_app.validate_skills_only_payload(skills, analysis) == []
    assert resume_app.normalize_skills_for_order(skills, data_center_resume.SKILL_CATEGORIES) == skills


def test_data_center_dedicated_prompts_cover_all_sections():
    category = data_center_resume.CATEGORY
    prompts = [
        resume_app.build_ai_resume_title_summary_prompt(category),
        resume_app.build_ai_resume_skills_prompt(category),
        resume_app.build_ai_resume_experience_prompt(category),
        resume_app.build_ai_resume_experience_subset_prompt([], category),
    ]
    for prompt in prompts:
        assert "HPE" in prompt
        assert "February 2024" in prompt
        assert "rack-and-stack" in prompt
        assert "never invent server counts" in prompt


def test_main_analyze_automatically_routes_and_returns_hpe_history(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "current_job_preflight", lambda *_args, **_kwargs: {"blocked": False})
    monkeypatch.setattr(resume_app, "analyze_job_description", lambda **_kwargs: {
        "target_role": "Data Center Technician", "core_problem": "Maintain server infrastructure",
    })
    monkeypatch.setattr(resume_app, "classify_resume_job", lambda *_args: {
        "category": data_center_resume.CATEGORY, "suitable": True,
    })
    response = resume_app.app.test_client().post("/api/ai/analyze", json={
        "job_description": "Deploy and troubleshoot servers, Linux, network cabling and infrastructure incidents. " * 3,
        "reset_memory": True,
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["analysis"]["prompt_family_key"] == data_center_resume.CATEGORY
    assert len(payload["experience_history"]) == 1
    assert payload["experience_history"][0]["company"] == "HPE"
    session = resume_app.ai_sessions[payload["session_id"]]
    assert resume_app.normalize_ai_enabled_experience_keys(resume_app.EXPERIENCE_BLUEPRINT_KEYS, session) == payload["enabled_experience_keys"]
    resume_app.ai_sessions.pop(payload["session_id"], None)


@pytest.mark.parametrize("subset", [True, False])
def test_data_center_qualitative_bullets_do_not_trigger_numeric_retries(monkeypatch, subset):
    analysis = resume_app.apply_resume_category(
        {"core_problem": "Maintain server infrastructure"},
        {"category": data_center_resume.CATEGORY},
    )
    snapshot = resume_app.data_center_snapshot_values({"contact": {"location": "Dallas, TX"}})
    blueprints = resume_app.experience_blueprints_from_snapshot(snapshot)
    key = blueprints[0]["key"]
    payload = {"experience": {key: {
        "title": "Data Center Technician",
        "bullets": [
            "Diagnosed server hardware failures, replaced faulty components, validated system health, and documented corrective actions within approved maintenance procedures."
        ] * 12,
    }}}
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(payload)

    monkeypatch.setattr(resume_app, "call_openai_structured_output", generate)
    monkeypatch.setattr(resume_app, "current_experience_blueprints", lambda **_kwargs: blueprints)
    kwargs = {"api_key": "test-key", "analysis_payload": analysis}
    if subset:
        result = resume_app.generate_experience_subset_from_analysis(
            **kwargs, blueprints=blueprints, model=resume_app.RESUME_MODEL,
            timeout_seconds=resume_app.OPENAI_RESUME_TIMEOUT_SECONDS,
        )
    else:
        result = resume_app.generate_resume_experience_from_analysis(
            **kwargs, job_description="Maintain servers", core_payload={}, enabled_experience_keys=[key],
        )
    assert len(calls) == 1
    assert len(result["experience"][key]["bullets"]) == 12
    assert resume_app.validate_experience_numeric_coverage(result, blueprints, analysis) == []
    assert resume_app.validate_experience_numeric_coverage(result, blueprints, {"generation_route_key": "backend_application"})

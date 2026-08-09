import inspect

import app as resume_app


ANALYSIS = {
    "target_role": "Backend Engineer",
    "role_family": "backend application engineering",
    "skill_category_order_key": "backend_application",
    "prompt_family_key": "software_engineering",
    "skills_mentioned": ["Python", "FastAPI"],
}


def active_blueprints():
    return [dict(resume_app.EXPERIENCE_BLUEPRINTS[0])]


def test_jd_analysis_keeps_analysis_stage_configuration(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return dict(ANALYSIS)

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    resume_app.analyze_job_description(
        api_key="test-key",
        job_description="Build reliable backend systems with Python and FastAPI.",
    )

    assert captured["model"] == resume_app.ANALYSIS_MODEL
    assert captured["temperature"] == resume_app.ANALYSIS_TEMPERATURE
    assert captured["request_timeout_seconds"] == resume_app.OPENAI_ANALYSIS_TIMEOUT_SECONDS
    assert captured["reasoning_effort"] == "low"
    assert captured["schema_name"] == "jd_analysis"


def test_analysis_schema_uses_one_canonical_generation_route():
    schema = resume_app.ai_analysis_schema()
    properties = schema["properties"]

    assert "generation_route_key" in properties
    assert "generation_route_key" in schema["required"]
    assert "skill_category_order_key" not in properties
    assert "prompt_family_key" not in properties


def test_growth_engineer_repairs_legacy_gtm_route_mismatch():
    analysis = {
        "target_role": "Growth Engineer",
        "role_family": "GTM engineering",
        "skill_category_order_key": "gtm_engineering",
        "prompt_family_key": "solutions_customer",
        "top_requirements": [
            "Own the activation funnel and experimentation loop",
            "Build backend and frontend product features",
        ],
        "responsibilities": [
            "Instrument product analytics and attribution",
            "Own marketplace growth systems from design to production",
        ],
        "skills_mentioned": [
            "Python",
            "Postgres",
            "AWS",
            "React",
            "TypeScript",
            "PostHog",
            "Amplitude",
        ],
    }

    normalized = resume_app.normalize_analysis_payload(analysis)

    assert normalized["role_family"] == "growth product engineering"
    assert normalized["generation_route_key"] == "growth_product"
    assert normalized["skill_category_order_key"] == "fullstack_product"
    assert normalized["prompt_family_key"] == "software_engineering"
    assert not resume_app.is_gtm_prompt_family(normalized)


def test_real_gtm_systems_role_stays_on_gtm_route():
    analysis = {
        "target_role": "GTM Engineer",
        "role_family": "GTM engineering",
        "generation_route_key": "gtm_engineering",
        "responsibilities": [
            "Build Salesforce and HubSpot lead routing",
            "Automate enrichment and outbound sequencing",
        ],
        "skills_mentioned": ["Salesforce", "HubSpot", "Clay"],
    }

    normalized = resume_app.normalize_analysis_payload(analysis)

    assert normalized["generation_route_key"] == "gtm_engineering"
    assert normalized["skill_category_order_key"] == "gtm_engineering"
    assert normalized["prompt_family_key"] == "gtm_engineering"
    assert resume_app.is_gtm_prompt_family(normalized)


def test_ai_coding_tools_do_not_route_architecture_role_to_ai_application():
    analysis = {
        "target_role": "Senior Software Engineer",
        "role_family": "AI application engineering",
        "skill_category_order_key": "ai_application",
        "prompt_family_key": "software_engineering",
        "responsibilities": [
            "Break a monolith into service-oriented domain services",
            "Build event-driven .NET and React applications",
        ],
        "skills_mentioned": ["C#", ".NET", "React", "PostgreSQL", "AWS", "Cursor", "Claude Code"],
    }

    normalized = resume_app.normalize_analysis_payload(analysis)

    assert normalized["role_family"] == "backend application engineering"
    assert normalized["generation_route_key"] == "backend_application"
    assert normalized["skill_category_order_key"] == "backend_application"
    assert normalized["prompt_family_key"] == "software_engineering"


def test_growth_route_accepts_coherent_software_history_titles():
    blueprints = [dict(item) for item in resume_app.EXPERIENCE_BLUEPRINTS[:3]]
    analysis = {
        "target_role": "Growth Engineer",
        "role_family": "growth product engineering",
        "generation_route_key": "growth_product",
    }
    payload = {
        "experience_titles": {
            blueprints[0]["key"]: "Applied AI Engineer",
            blueprints[1]["key"]: "Full Stack Engineer",
            blueprints[2]["key"]: "Software Engineer",
        }
    }

    assert resume_app.validate_experience_title_review_payload(
        payload,
        blueprints,
        analysis,
    ) == []


def test_preliminary_skills_forwards_resume_stage_configuration(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return {"updated_skills": []}

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "validate_skills_only_payload", lambda *_args, **_kwargs: [])

    resume_app.generate_skills_from_analysis(
        api_key="test-key",
        analysis_payload=ANALYSIS,
    )

    assert captured["model"] == resume_app.RESUME_MODEL
    assert captured["temperature"] == resume_app.RESUME_TEMPERATURE
    assert captured["request_timeout_seconds"] == resume_app.OPENAI_RESUME_TIMEOUT_SECONDS
    assert captured["reasoning_effort"] == "low"
    assert captured["schema_name"] == "resume_skills_generation"


def test_preliminary_skills_retries_once_with_more_tokens_on_truncation(monkeypatch):
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError(
                "OpenAI API returned no final output "
                "(status=incomplete, details={'reason': 'max_output_tokens'})"
            )
        return {"updated_skills": []}

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "validate_skills_only_payload", lambda *_args, **_kwargs: [])

    resume_app.generate_skills_from_analysis(
        api_key="test-key",
        analysis_payload=ANALYSIS,
    )

    assert len(calls) == 2
    assert calls[0]["max_output_tokens"] == 2900
    assert calls[1]["max_output_tokens"] == 4800
    assert "exhausted its output budget" in calls[1]["user_prompt"]


def test_preliminary_skills_does_not_retry_other_api_failures(monkeypatch):
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("OpenAI API request failed: authentication_error")

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    try:
        resume_app.generate_skills_from_analysis(
            api_key="test-key",
            analysis_payload=ANALYSIS,
        )
    except RuntimeError as exc:
        assert "authentication_error" in str(exc)
    else:
        raise AssertionError("Expected authentication failure")

    assert len(calls) == 1


def test_high_judgment_helper_signatures_use_dedicated_models_and_reasoning():
    synthesis_signature = inspect.signature(resume_app.generate_final_synthesis_from_analysis)
    audit_signature = inspect.signature(resume_app.generate_resume_quality_audit)

    assert synthesis_signature.parameters["model"].default == resume_app.SYNTHESIS_MODEL
    assert synthesis_signature.parameters["reasoning_effort"].default == resume_app.SYNTHESIS_REASONING_EFFORT
    assert audit_signature.parameters["model"].default == resume_app.AUDIT_MODEL
    assert audit_signature.parameters["reasoning_effort"].default == resume_app.AUDIT_REASONING_EFFORT


def test_final_synthesis_forwards_dedicated_model_and_medium_reasoning(monkeypatch):
    captured = {}
    blueprints = active_blueprints()

    def fake_call(**kwargs):
        captured.update(kwargs)
        return {
            "updated_title": "Backend Engineer",
            "updated_summary": "Builds reliable backend systems.",
            "updated_skills": [],
            "experience_titles": {blueprints[0]["key"]: "Software Engineer"},
        }

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    resume_app.generate_final_synthesis_from_analysis(
        api_key="test-key",
        job_description="Build reliable backend systems.",
        analysis_payload=ANALYSIS,
        preliminary_skills_payload={"updated_skills": []},
        combined_experience_payload={
            "experience": {
                blueprints[0]["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable backend systems."],
                }
            }
        },
        active_blueprints=blueprints,
    )

    assert captured["model"] == resume_app.SYNTHESIS_MODEL
    assert captured["reasoning_effort"] == "medium"


def test_quality_audit_forwards_dedicated_model_and_medium_reasoning(monkeypatch):
    captured = {}
    validated = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return {"decision": "approved"}

    def fake_validator(result, **kwargs):
        validated["result"] = result
        validated.update(kwargs)
        return result

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "validate_resume_quality_audit_result", fake_validator)

    current_resume = {
        "updated_title": "Backend Engineer",
        "updated_summary": "Builds reliable backend systems.",
        "updated_skills": [],
        "experience": {},
    }
    result = resume_app.generate_resume_quality_audit(
        api_key="test-key",
        job_description="Build reliable backend systems.",
        analysis_payload=ANALYSIS,
        current_resume=current_resume,
        active_blueprints=active_blueprints(),
    )

    assert captured["model"] == resume_app.AUDIT_MODEL
    assert captured["reasoning_effort"] == "medium"
    assert captured["max_output_tokens"] == 8000
    assert captured["background"] is True
    assert (
        captured["background_timeout_seconds"]
        == resume_app.OPENAI_AUDIT_BACKGROUND_TIMEOUT_SECONDS
    )
    assert validated["result"] == result
    assert validated["current_resume"]["updated_title"] == current_resume["updated_title"]
    assert resume_app.AUDIT_MODEL == "gpt-5.6-luna"


def assert_model_metadata(payload):
    assert payload["model"] == resume_app.RESUME_MODEL
    assert payload["analysis_model"] == resume_app.ANALYSIS_MODEL
    assert payload["resume_model"] == resume_app.RESUME_MODEL
    assert payload["synthesis_model"] == resume_app.SYNTHESIS_MODEL
    assert payload["audit_model"] == resume_app.AUDIT_MODEL
    assert payload["synthesis_reasoning_effort"] == resume_app.SYNTHESIS_REASONING_EFFORT
    assert payload["audit_reasoning_effort"] == resume_app.AUDIT_REASONING_EFFORT


def test_ai_extension_and_settings_status_expose_all_model_metadata(monkeypatch):
    monkeypatch.setattr(resume_app, "is_ai_generation_ready", lambda: (True, "Ready"))
    monkeypatch.setattr(resume_app, "get_pdf_conversion_status", lambda: (True, "Ready"))
    monkeypatch.setattr(resume_app, "current_profile", lambda: {"experience_history": []})
    monkeypatch.setattr(resume_app, "current_identity_profiles", lambda: [])
    monkeypatch.setattr(resume_app, "has_permanent_profile_doc", lambda: True)
    monkeypatch.setattr(resume_app.extension_drafts, "has_duplicate_review", lambda: False)

    client = resume_app.app.test_client()
    ai_payload = client.get("/api/ai/status").get_json()
    extension_payload = client.get("/api/extension/status").get_json()
    settings_payload = client.get("/api/settings").get_json()

    assert_model_metadata(ai_payload)
    assert_model_metadata(extension_payload)
    assert settings_payload["ai_model"] == resume_app.RESUME_MODEL
    assert settings_payload["ai_analysis_model"] == resume_app.ANALYSIS_MODEL
    assert settings_payload["ai_resume_model"] == resume_app.RESUME_MODEL
    assert settings_payload["ai_synthesis_model"] == resume_app.SYNTHESIS_MODEL
    assert settings_payload["ai_audit_model"] == resume_app.AUDIT_MODEL
    assert settings_payload["ai_synthesis_reasoning_effort"] == resume_app.SYNTHESIS_REASONING_EFFORT
    assert settings_payload["ai_audit_reasoning_effort"] == resume_app.AUDIT_REASONING_EFFORT

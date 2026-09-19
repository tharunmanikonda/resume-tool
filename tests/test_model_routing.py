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
    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _cache_key: None)
    monkeypatch.setattr(resume_app, "save_cached_ai_stage_result", lambda **_kwargs: None)

    resume_app.analyze_job_description(
        api_key="test-key",
        job_description="Build reliable backend systems with Python and FastAPI.",
    )

    assert captured["model"] == resume_app.ANALYSIS_MODEL
    assert captured["temperature"] == resume_app.ANALYSIS_TEMPERATURE
    assert captured["request_timeout_seconds"] == resume_app.OPENAI_ANALYSIS_TIMEOUT_SECONDS
    assert captured["reasoning_effort"] == "low"
    assert captured["schema_name"] == "jd_analysis"


def test_jd_analysis_cache_hit_skips_openai_call(monkeypatch):
    def fail_call(**_kwargs):
        raise AssertionError("JD analysis should be served from cache")

    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _cache_key: dict(ANALYSIS))
    monkeypatch.setattr(resume_app, "call_openai_structured_output", fail_call)

    result = resume_app.analyze_job_description(
        api_key="test-key",
        job_description="Build reliable backend systems with Python and FastAPI.",
    )

    assert result["target_role"] == ANALYSIS["target_role"]
    assert result["generation_route_key"] == "backend_application"


def test_jd_analysis_cache_miss_saves_normalized_result(monkeypatch):
    saved = {}

    def fake_call(**_kwargs):
        return dict(ANALYSIS)

    def fake_save(**kwargs):
        saved.update(kwargs)

    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _cache_key: None)
    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "save_cached_ai_stage_result", fake_save)

    result = resume_app.analyze_job_description(
        api_key="test-key",
        job_description="Build reliable backend systems with Python and FastAPI.",
    )

    assert saved["stage"] == "jd_analysis"
    assert saved["model"] == resume_app.ANALYSIS_MODEL
    assert saved["prompt_version"] == resume_app.ANALYSIS_PROMPT_VERSION
    assert saved["result"]["generation_route_key"] == result["generation_route_key"]


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


def test_professional_resume_mode_keeps_existing_experience_guidance():
    prompt = resume_app.build_ai_resume_title_summary_prompt(resume_mode="professional")

    assert "RESUME MODE: Professional" in prompt
    assert "4+ years of experience" in prompt


def test_internship_resume_mode_uses_student_eligible_guidance():
    prompt = resume_app.build_ai_resume_title_summary_prompt(resume_mode="internship")

    assert "RESUME MODE: Internship / Co-op / New Grad" in prompt
    assert "3+ years of software engineering experience" in prompt
    assert "lead with software engineering experience first for engineering roles" in prompt
    assert "for analyst/data roles, lead with data, SQL, reporting, process, and decision-support evidence" in prompt
    assert "Treat DBA as education/context" in prompt
    assert "4+ years of experience" not in prompt


def test_internship_resume_mode_neutralizes_india_experience_locations():
    profile = {
        "experience_history": [
            {
                "key": "mckinsey",
                "company": "Example",
                "location": "Bengaluru, India",
                "title": "Software Engineer",
                "dates": "Jan 2022 - Dec 2024",
                "enabled": True,
            }
        ]
    }

    professional = resume_app.current_experience_blueprints(profile, "professional")
    internship = resume_app.current_experience_blueprints(profile, "internship")

    assert professional[0]["location"] == "Bengaluru, India"
    assert internship[0]["location"] == "Location omitted"
    assert internship[0]["enabled"] is False


def test_internship_resume_mode_defaults_to_two_us_experiences():
    profile = {
        "experience_history": [
            {
                "key": "mckinsey",
                "company": "Role 1",
                "location": "CA, USA",
                "title": "Software Engineer",
                "dates": "2025 - Present",
                "enabled": True,
            },
            {
                "key": "uber",
                "company": "Role 2",
                "location": "Austin, TX",
                "title": "Full Stack Developer",
                "dates": "2024 - 2025",
                "enabled": True,
            },
            {
                "key": "kpmg",
                "company": "Role 3",
                "location": "Bengaluru, India",
                "title": "Java Developer",
                "dates": "2021 - 2022",
                "enabled": True,
            },
            {
                "key": "trigent",
                "company": "Role 4",
                "location": "Remote, United States",
                "title": "Frontend Developer",
                "dates": "2020 - 2021",
                "enabled": True,
            },
        ]
    }

    assert resume_app.complete_profile_experience_keys(profile, "internship") == ["mckinsey", "uber"]


def test_internship_ai_enabled_keys_are_capped_to_two_us_roles():
    profile = {
        "experience_history": [
            {
                "key": "mckinsey",
                "company": "Role 1",
                "location": "CA, USA",
                "title": "Software Engineer",
                "dates": "2025 - Present",
                "enabled": True,
            },
            {
                "key": "uber",
                "company": "Role 2",
                "location": "Austin, TX",
                "title": "Full Stack Developer",
                "dates": "2024 - 2025",
                "enabled": True,
            },
            {
                "key": "kpmg",
                "company": "Role 3",
                "location": "Bengaluru, India",
                "title": "Java Developer",
                "dates": "2021 - 2022",
                "enabled": True,
            },
            {
                "key": "trigent",
                "company": "Role 4",
                "location": "Remote, United States",
                "title": "Frontend Developer",
                "dates": "2020 - 2021",
                "enabled": True,
            },
        ]
    }
    session = {
        "resume_mode": "internship",
        "profile_snapshot": resume_app.profile_for_resume_mode(profile, "internship"),
    }

    keys = resume_app.normalize_ai_enabled_experience_keys(["mckinsey", "uber", "kpmg", "trigent"], session)

    assert keys == ["mckinsey", "uber"]


def test_internship_resume_mode_adds_dba_education(monkeypatch):
    monkeypatch.setattr(
        resume_app,
        "current_profile",
        lambda: {
            "name": "Test User",
            "contact": {},
            "application": {},
            "projects": [],
            "certifications": [],
            "experience_history": [],
        },
    )
    resume = {"education": [{"degree": "Master's in Computer Science", "institution": "UAB", "dates": "2023"}]}

    updated = resume_app.apply_profile_overrides(resume, resume_mode="internship")

    assert updated["education"][0]["degree"] == "Doctor of Business Administration (DBA), in progress"
    assert updated["education"][0]["dates"] == "In progress"
    assert updated["education"][1]["degree"] == "Master's in Computer Science"


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
    assert captured["user_prompt"].index("Active experience structure") < captured["user_prompt"].index("Raw job description")


def test_experience_subset_prompt_places_blueprints_before_analysis(monkeypatch):
    captured = {}
    blueprints = active_blueprints()

    def fake_call(**kwargs):
        captured.update(kwargs)
        return {
            "experience": {
                blueprints[0]["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable backend systems that improved recurring operational throughput by 20%."],
                }
            }
        }

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "collect_invalid_experience_titles", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(resume_app, "validate_experience_subset_payload_with_analysis", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(resume_app, "validate_experience_numeric_coverage", lambda *_args, **_kwargs: [])

    resume_app.generate_experience_subset_from_analysis(
        api_key="test-key",
        analysis_payload=ANALYSIS,
        blueprints=blueprints,
        model=resume_app.RESUME_MODEL,
        timeout_seconds=resume_app.OPENAI_RESUME_TIMEOUT_SECONDS,
        preliminary_skills_payload={"updated_skills": []},
    )

    assert captured["user_prompt"].index("Experience structure") < captured["user_prompt"].index("Analysis:")


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

import app as resume_app


ANALYSIS = {
    "target_role": "Backend Engineer",
    "role_family": "backend application engineering",
    "skill_category_order_key": "backend_application",
    "prompt_family_key": "software_engineering",
    "core_problem": "Build reliable backend services",
    "top_requirements": ["Python", "FastAPI", "PostgreSQL"],
    "skills_mentioned": ["Python", "FastAPI", "PostgreSQL", "AWS"],
}

PRELIMINARY_SKILLS = {
    "updated_skills": [
        {"category": "Programming Languages", "items": ["Python", "Java"]},
        {"category": "Backend Engineering", "items": ["FastAPI", "Spring Boot"]},
        {"category": "Data & Storage", "items": ["PostgreSQL", "Redis"]},
        {"category": "Cloud & Infrastructure", "items": ["AWS", "Docker"]},
        {"category": "Observability & Reliability", "items": ["OpenTelemetry", "Grafana"]},
        {"category": "DevOps & CI/CD", "items": ["GitHub Actions", "Terraform"]},
    ]
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


def active_blueprints(count=2):
    return [dict(blueprint) for blueprint in resume_app.EXPERIENCE_BLUEPRINTS[:count]]


def test_numeric_evidence_detection_distinguishes_versions_from_metrics():
    assert resume_app._numeric_tokens(
        "Implemented OAuth 2.0, TLS 1.3, HTTP/2, Microsoft 365, and .NET 8 integrations."
    ) == set()
    assert resume_app._numeric_tokens(
        "Reduced latency by 35%, improved throughput by 2.0x, and served 5,000+ users with 500ms responses."
    ) == {"35%", "2.0x", "5000+", "500"}


def test_experience_evidence_validation_allows_protocol_versions_but_rejects_ungrounded_metrics():
    blueprint = dict(active_blueprints(1)[0])
    blueprint.update({
        "anchor": "Authentication and API integration",
        "metric_evidence": "",
        "evidence": "",
        "achievements": "",
        "source_bullets": [],
    })
    role_key = blueprint["key"]

    version_payload = {
        "experience": {
            role_key: {
                "title": "Software Engineer",
                "bullets": ["Implemented OAuth 2.0 authentication for secure API integrations."],
            }
        }
    }
    assert resume_app.validate_generated_experience_evidence(version_payload, [blueprint]) == []

    metric_payload = {
        "experience": {
            role_key: {
                "title": "Software Engineer",
                "bullets": ["Improved API throughput by 2.0x through concurrency tuning."],
            }
        }
    }
    assert "unsupported numeric metrics: 2.0x" in resume_app.validate_generated_experience_evidence(
        metric_payload,
        [blueprint],
    )[0]


def valid_final_skills():
    return [dict(entry, items=list(entry["items"])) for entry in PRELIMINARY_SKILLS["updated_skills"]]


def test_experience_subset_uses_preliminary_skills_without_early_core(monkeypatch):
    captured = {}
    blueprint = dict(active_blueprints(1)[0], bullet_min=1, bullet_max=1)

    def fake_call(**kwargs):
        captured.update(kwargs)
        return {
            "experience": {
                blueprint["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built a Python API workflow using FastAPI with measured reliability improvements."],
                }
            }
        }

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    resume_app.generate_experience_subset_from_analysis(
        api_key="test-key",
        analysis_payload=ANALYSIS,
        preliminary_skills_payload=PRELIMINARY_SKILLS,
        core_payload={
            "updated_title": "EARLY TOP TITLE MUST NOT APPEAR",
            "updated_summary": "EARLY SUMMARY MUST NOT APPEAR",
            "updated_skills": [],
        },
        blueprints=[blueprint],
        model="test-model",
        timeout_seconds=1,
    )

    assert "Preliminary skills:" in captured["user_prompt"]
    assert "FastAPI" in captured["user_prompt"]
    assert "EARLY TOP TITLE MUST NOT APPEAR" not in captured["user_prompt"]
    assert "EARLY SUMMARY MUST NOT APPEAR" not in captured["user_prompt"]
    assert "preliminary skills" in captured["developer_prompt"].lower()


def test_final_synthesis_prompt_contains_all_stage_inputs_and_active_keys(monkeypatch):
    captured = {}
    blueprints = active_blueprints()
    job_description = "Build payment infrastructure for a healthcare platform using Python."
    combined_experience = {
        "experience": {
            blueprints[0]["key"]: {
                "title": "Software Engineer",
                "bullets": ["MCKINSEY COMPLETE BULLET with Python and measurable delivery evidence."],
            },
            blueprints[1]["key"]: {
                "title": "Software Engineer",
                "bullets": ["UBER COMPLETE BULLET with PostgreSQL and operational reliability evidence."],
            },
        }
    }

    def fake_call(**kwargs):
        captured.update(kwargs)
        return {
            "updated_title": "Backend Software Engineer",
            "updated_summary": SUMMARY,
            "updated_skills": valid_final_skills(),
            "experience_titles": {
                blueprints[0]["key"]: "Software Engineer",
                blueprints[1]["key"]: "Software Engineer",
            },
        }

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    resume_app.generate_final_synthesis_from_analysis(
        api_key="test-key",
        job_description=job_description,
        analysis_payload=ANALYSIS,
        preliminary_skills_payload=PRELIMINARY_SKILLS,
        combined_experience_payload=combined_experience,
        active_blueprints=blueprints,
        model="test-model",
        timeout_seconds=1,
    )

    assert job_description in captured["user_prompt"]
    assert "FastAPI" in captured["user_prompt"]
    assert "MCKINSEY COMPLETE BULLET" in captured["user_prompt"]
    assert "UBER COMPLETE BULLET" in captured["user_prompt"]
    for blueprint in blueprints:
        assert blueprint["key"] in captured["user_prompt"]
    title_schema = captured["schema"]["properties"]["experience_titles"]
    assert title_schema["required"] == [blueprint["key"] for blueprint in blueprints]


def test_final_synthesis_normalizes_skills_into_required_category_order(monkeypatch):
    blueprints = active_blueprints(1)
    scrambled_skills = list(reversed(valid_final_skills()))

    monkeypatch.setattr(
        resume_app,
        "call_openai_structured_output",
        lambda **kwargs: {
            "updated_title": "Backend Software Engineer",
            "updated_summary": SUMMARY,
            "updated_skills": scrambled_skills,
            "experience_titles": {blueprints[0]["key"]: "Software Engineer"},
        },
    )

    result = resume_app.generate_final_synthesis_from_analysis(
        api_key="test-key",
        job_description="Build reliable Python services.",
        analysis_payload=ANALYSIS,
        preliminary_skills_payload=PRELIMINARY_SKILLS,
        combined_experience_payload={
            "experience": {
                blueprints[0]["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable Python services with measurable operational outcomes."],
                }
            }
        },
        active_blueprints=blueprints,
        model="test-model",
        timeout_seconds=1,
    )

    assert [entry["category"] for entry in result["updated_skills"]] == [
        "Programming Languages",
        "Backend Engineering",
        "Data & Storage",
        "Cloud & Infrastructure",
        "Observability & Reliability",
        "DevOps & CI/CD",
    ]


def test_final_synthesis_validates_only_active_role_keys():
    blueprints = active_blueprints()
    payload = {
        "updated_title": "Backend Software Engineer",
        "updated_summary": SUMMARY,
        "updated_skills": valid_final_skills(),
        "experience_titles": {
            blueprints[0]["key"]: "Software Engineer",
            blueprints[1]["key"]: "Software Engineer",
        },
    }

    issues = resume_app.validate_final_synthesis_payload(payload, blueprints, ANALYSIS)

    assert not any("KPMG" in issue or "Trigent" in issue for issue in issues)
    assert not any("missing a reviewed title" in issue for issue in issues)

    payload["experience_titles"].pop(blueprints[1]["key"])
    issues = resume_app.validate_final_synthesis_payload(payload, blueprints, ANALYSIS)
    assert any(blueprints[1]["company"] in issue and "missing a reviewed title" in issue for issue in issues)


def test_final_synthesis_prompt_has_summary_and_domain_guardrails():
    prompt = resume_app.build_ai_final_synthesis_prompt().lower()

    assert "word count rules (mandatory)" in prompt
    assert "top resume title must be 2-8 words" in prompt
    assert "65-95 words" in prompt
    assert "every experience title must be 2-8 words" in prompt
    assert "count the final returned wording after all edits" in prompt
    assert "do not return a synthesis or proposal that falls outside any required range" in prompt
    assert "simple, natural human tone" in prompt
    assert "transferable capabilities" in prompt
    assert "merely because the jd mentions it" in prompt
    assert "unless the generated experience or active blueprints independently support" in prompt
    assert "standard market titles" in prompt
    assert "unrelated role families" in prompt

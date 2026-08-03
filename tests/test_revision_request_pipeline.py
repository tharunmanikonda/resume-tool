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
    "skills_mentioned": ["Python", "FastAPI", "PostgreSQL", "AWS"],
}

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

REVISION_REQUEST = "Keep the summary direct and move API reliability evidence earlier."
CURRENT_RESUME = """Updated Title
Backend Software Engineer

Updated Summary
Keep this unaffected summary sentence.

Updated Skills
Programming Languages: Python, Java.
"""

GUARD_PHRASES = (
    "editing instruction only; never factual evidence",
    "consistent with the JD, generated evidence, immutable experience blueprints",
    "never as evidence for a skill, tool, metric, vertical or domain experience",
    "Do not invent unsupported tools, metrics, vertical experience, or history",
    "Preserve unaffected current resume content",
)


@pytest.fixture(autouse=True)
def isolated_sessions(monkeypatch):
    resume_app.ai_sessions.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    yield
    resume_app.ai_sessions.clear()


def revision_context():
    return resume_app.normalize_revision_context(REVISION_REQUEST, CURRENT_RESUME)


def assert_revision_prompt(prompt):
    assert REVISION_REQUEST in prompt
    assert "Keep this unaffected summary sentence." in prompt
    for phrase in GUARD_PHRASES:
        assert phrase in prompt


def test_revision_context_is_present_and_guarded_in_skills_prompt(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return copy.deepcopy(SKILLS)

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "validate_skills_only_payload", lambda *_args: [])

    resume_app.generate_skills_from_analysis(
        api_key="test-key",
        analysis_payload=ANALYSIS,
        revision_context=revision_context(),
    )

    assert_revision_prompt(captured["user_prompt"])


def test_revision_context_is_present_and_guarded_in_experience_prompt(monkeypatch):
    captured = {}
    blueprint = dict(resume_app.EXPERIENCE_BLUEPRINTS[0], bullet_min=1, bullet_max=1)

    def fake_call(**kwargs):
        captured.update(kwargs)
        return {
            "experience": {
                blueprint["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable Python APIs with measurable operational outcomes."],
                }
            }
        }

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "validate_experience_subset_payload_with_analysis", lambda *_args: [])

    resume_app.generate_experience_subset_from_analysis(
        api_key="test-key",
        analysis_payload=ANALYSIS,
        preliminary_skills_payload=SKILLS,
        blueprints=[blueprint],
        model="test-model",
        timeout_seconds=1,
        revision_context=revision_context(),
    )

    assert_revision_prompt(captured["user_prompt"])


def test_revision_context_is_present_and_guarded_in_final_synthesis_prompt(monkeypatch):
    captured = {}
    blueprint = dict(resume_app.EXPERIENCE_BLUEPRINTS[0], bullet_min=1, bullet_max=1)

    def fake_call(**kwargs):
        captured.update(kwargs)
        return {
            "updated_title": "Backend Software Engineer",
            "updated_summary": (
                "Backend engineer with experience building reliable APIs and operational workflows across enterprise "
                "environments. Delivered Python services, PostgreSQL integrations, cloud deployments, and practical "
                "monitoring improvements that made systems easier to operate. Work includes customer-facing delivery "
                "and internal platforms, with a focus on clear technical decisions, measurable outcomes, and dependable "
                "execution. Brings transferable system design and collaboration skills to complex software problems "
                "without overstating industry-specific experience."
            ),
            "updated_skills": copy.deepcopy(SKILLS["updated_skills"]),
            "experience_titles": {blueprint["key"]: "Software Engineer"},
        }

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)

    resume_app.generate_final_synthesis_from_analysis(
        api_key="test-key",
        job_description="Build reliable Python APIs.",
        analysis_payload=ANALYSIS,
        preliminary_skills_payload=SKILLS,
        combined_experience_payload={
            "experience": {
                blueprint["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable Python APIs with measurable operational outcomes."],
                }
            }
        },
        active_blueprints=[blueprint],
        revision_context=revision_context(),
        model="test-model",
        timeout_seconds=1,
    )

    assert_revision_prompt(captured["user_prompt"])


def test_analyze_stores_bounded_context_and_new_jd_clears_it(monkeypatch):
    monkeypatch.setattr(resume_app, "analyze_job_description", lambda **_kwargs: copy.deepcopy(ANALYSIS))
    client = resume_app.app.test_client()

    first = client.post(
        "/api/ai/analyze",
        json={
            "job_description": "First JD",
            "revision_request": "  Make   this direct.  ",
            "current_resume_content": "Line one.  \r\n\r\n Line two.",
        },
    )
    assert first.status_code == 200
    session_id = first.get_json()["session_id"]
    context = resume_app.ai_sessions[session_id]["revision_context"]
    assert context == {
        "revision_request": "Make this direct.",
        "current_resume_content": "Line one.\nLine two.",
    }

    second = client.post(
        "/api/ai/analyze",
        json={
            "session_id": session_id,
            "job_description": "Second JD",
        },
    )
    assert second.status_code == 200
    assert resume_app.ai_sessions[session_id]["revision_context"] is None

    bounded = resume_app.normalize_revision_context(
        "x" * (resume_app.AI_REVISION_REQUEST_MAX_CHARS + 20),
        "y" * (resume_app.AI_REVISION_RESUME_MAX_CHARS + 20),
    )
    assert len(bounded["revision_request"]) == resume_app.AI_REVISION_REQUEST_MAX_CHARS
    assert len(bounded["current_resume_content"]) == resume_app.AI_REVISION_RESUME_MAX_CHARS


def test_reset_creates_clean_session_and_no_context_keeps_all_prompts_unchanged(monkeypatch):
    old_session_id, old_session = resume_app.get_ai_session(None, "First JD", False)
    old_session["revision_context"] = revision_context()

    new_session_id, new_session = resume_app.get_ai_session(old_session_id, "First JD", True)
    assert new_session_id != old_session_id
    assert new_session["revision_context"] is None

    captured = {}
    blueprint = dict(resume_app.EXPERIENCE_BLUEPRINTS[0], bullet_min=1, bullet_max=1)

    def fake_call(**kwargs):
        captured[kwargs["schema_name"]] = kwargs["user_prompt"]
        if kwargs["schema_name"] == "resume_skills_generation":
            return copy.deepcopy(SKILLS)
        if kwargs["schema_name"] == "resume_experience_subset_generation":
            return {
                "experience": {
                    blueprint["key"]: {
                        "title": "Software Engineer",
                        "bullets": ["Built reliable Python APIs with measurable operational outcomes."],
                    }
                }
            }
        return {
            "updated_title": "Backend Software Engineer",
            "updated_summary": "A grounded summary based on generated evidence.",
            "updated_skills": copy.deepcopy(SKILLS["updated_skills"]),
            "experience_titles": {blueprint["key"]: "Software Engineer"},
        }

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "validate_skills_only_payload", lambda *_args: [])
    monkeypatch.setattr(resume_app, "validate_experience_subset_payload_with_analysis", lambda *_args: [])
    resume_app.generate_skills_from_analysis(
        api_key="test-key",
        analysis_payload=ANALYSIS,
    )
    resume_app.generate_experience_subset_from_analysis(
        api_key="test-key",
        analysis_payload=ANALYSIS,
        preliminary_skills_payload=SKILLS,
        blueprints=[blueprint],
        model="test-model",
        timeout_seconds=1,
    )
    resume_app.generate_final_synthesis_from_analysis(
        api_key="test-key",
        job_description="Build reliable Python APIs.",
        analysis_payload=ANALYSIS,
        preliminary_skills_payload=SKILLS,
        combined_experience_payload={
            "experience": {
                blueprint["key"]: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable Python APIs with measurable operational outcomes."],
                }
            }
        },
        active_blueprints=[blueprint],
        model="test-model",
        timeout_seconds=1,
    )

    assert set(captured) == {
        "resume_skills_generation",
        "resume_experience_subset_generation",
        "resume_final_synthesis",
    }
    for prompt in captured.values():
        assert REVISION_REQUEST not in prompt
        assert "User-requested revision context" not in prompt

import copy

import pytest

import app as resume_app


JOB_DESCRIPTION = "Build reliable backend services with Python, PostgreSQL, AWS, and automated testing."

ANALYSIS = {
    "target_role": "Backend Software Engineer",
    "role_family": "backend application engineering",
    "skill_category_order_key": "backend_application",
    "prompt_family_key": "software_engineering",
    "core_problem": "Build reliable backend services",
    "top_requirements": ["Python", "PostgreSQL", "AWS"],
    "skills_mentioned": ["Python", "PostgreSQL", "AWS", "Docker"],
}

SUMMARY = (
    "Backend software engineer with experience building reliable APIs, data workflows, and customer-facing "
    "systems across consulting and product environments. Delivered Python services, PostgreSQL integrations, "
    "cloud deployments, monitoring improvements, and automated testing that made platforms easier to operate. "
    "Work includes translating business needs into practical technical decisions, collaborating across teams, "
    "and improving system performance through measured changes. Brings a clear, grounded approach to complex "
    "software delivery without overstating industry-specific experience."
)

SKILLS = [
    {"category": "Programming Languages", "items": ["Python", "Java"]},
    {"category": "Backend Engineering", "items": ["REST APIs", "Microservices"]},
    {"category": "Data & Storage", "items": ["PostgreSQL", "Redis"]},
    {"category": "Cloud & Infrastructure", "items": ["AWS", "Docker"]},
    {"category": "Testing & Quality", "items": ["Unit testing", "Integration testing"]},
    {"category": "System Design & Performance", "items": ["System design", "Performance tuning"]},
]


@pytest.fixture(autouse=True)
def isolated_ai_sessions(monkeypatch):
    resume_app.ai_sessions.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    yield
    resume_app.ai_sessions.clear()


def generated_resume_payload():
    return {
        "updated_title": "Backend Software Engineer",
        "updated_summary": SUMMARY,
        "updated_skills": copy.deepcopy(SKILLS),
        "experience": {
            blueprint["key"]: {
                "title": "Software Engineer",
                "bullets": [f"Built reliable systems for {blueprint['company']}."],
            }
            for blueprint in resume_app.current_experience_blueprints()
        },
    }


def core_payload():
    return {
        "updated_title": "Backend Software Engineer",
        "updated_summary": SUMMARY,
        "updated_skills": copy.deepcopy(SKILLS),
    }


def test_generate_resume_from_analysis_defaults_to_all_role_prompt_and_schema(monkeypatch):
    captured = {}

    def fake_structured_output(**kwargs):
        captured.update(kwargs)
        return generated_resume_payload()

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_structured_output)

    result = resume_app.generate_resume_from_analysis(
        api_key="test-key",
        job_description=JOB_DESCRIPTION,
        analysis_payload=copy.deepcopy(ANALYSIS),
    )

    assert result["updated_title"] == "Backend Software Engineer"
    experience_schema = captured["schema"]["properties"]["experience"]
    assert experience_schema["required"] == resume_app.EXPERIENCE_BLUEPRINT_KEYS
    assert set(experience_schema["properties"]) == set(resume_app.EXPERIENCE_BLUEPRINT_KEYS)
    for blueprint in resume_app.current_experience_blueprints():
        assert blueprint["company"] in captured["developer_prompt"]


def test_generate_resume_from_analysis_uses_selected_role_subset_in_prompt_and_schema(monkeypatch):
    captured = {}
    selected_key = resume_app.EXPERIENCE_BLUEPRINT_KEYS[1]
    selected_blueprint = next(
        blueprint for blueprint in resume_app.current_experience_blueprints()
        if blueprint["key"] == selected_key
    )
    omitted_blueprints = [
        blueprint for blueprint in resume_app.current_experience_blueprints()
        if blueprint["key"] != selected_key
    ]

    def fake_structured_output(**kwargs):
        captured.update(kwargs)
        return {
            **generated_resume_payload(),
            "experience": {
                selected_key: {
                    "title": "Software Engineer",
                    "bullets": ["Built reliable backend service workflows using Python with measurable delivery gains."],
                }
            },
        }

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_structured_output)

    resume_app.generate_resume_from_analysis(
        api_key="test-key",
        job_description=JOB_DESCRIPTION,
        analysis_payload=copy.deepcopy(ANALYSIS),
        enabled_experience_keys=[selected_key],
    )

    experience_schema = captured["schema"]["properties"]["experience"]
    assert experience_schema["required"] == [selected_key]
    assert list(experience_schema["properties"]) == [selected_key]
    assert selected_blueprint["company"] in captured["developer_prompt"]
    assert all(blueprint["company"] not in captured["developer_prompt"] for blueprint in omitted_blueprints)


@pytest.mark.parametrize(
    ("request_keys", "expected_keys"),
    [
        (None, resume_app.EXPERIENCE_BLUEPRINT_KEYS),
        ([resume_app.EXPERIENCE_BLUEPRINT_KEYS[1]], [resume_app.EXPERIENCE_BLUEPRINT_KEYS[1]]),
    ],
)
def test_legacy_generate_resolves_enabled_experience_keys(
    monkeypatch,
    request_keys,
    expected_keys,
):
    captured = {}

    def fake_engine(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "analysis": copy.deepcopy(ANALYSIS),
            "resume": generated_resume_payload(),
            "timing": {"total_ms": 1},
        }

    monkeypatch.setattr(resume_app, "call_openai_resume_engine", fake_engine)
    request_payload = {"job_description": JOB_DESCRIPTION}
    if request_keys is not None:
        request_payload["enabled_experience_keys"] = request_keys

    response = resume_app.app.test_client().post("/api/ai/generate", json=request_payload)
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    session = resume_app.ai_sessions[payload["session_id"]]
    assert session["enabled_experience_keys"] == expected_keys
    assert captured["enabled_experience_keys"] == expected_keys

    expected_companies = {
        blueprint["company"]
        for blueprint in resume_app.current_experience_blueprints()
        if blueprint["key"] in expected_keys
    }
    omitted_companies = {
        blueprint["company"]
        for blueprint in resume_app.current_experience_blueprints()
        if blueprint["key"] not in expected_keys
    }
    assert all(company in payload["content"] for company in expected_companies)
    assert all(company not in payload["content"] for company in omitted_companies)


@pytest.mark.parametrize(
    ("request_keys", "expected_keys"),
    [
        (None, resume_app.EXPERIENCE_BLUEPRINT_KEYS),
        ([resume_app.EXPERIENCE_BLUEPRINT_KEYS[2]], [resume_app.EXPERIENCE_BLUEPRINT_KEYS[2]]),
    ],
)
def test_legacy_generate_core_resolves_enabled_experience_keys(
    monkeypatch,
    request_keys,
    expected_keys,
):
    monkeypatch.setattr(
        resume_app,
        "analyze_job_description",
        lambda **_kwargs: copy.deepcopy(ANALYSIS),
    )
    monkeypatch.setattr(
        resume_app,
        "generate_resume_core_from_analysis",
        lambda **_kwargs: core_payload(),
    )
    client = resume_app.app.test_client()
    analyze_response = client.post(
        "/api/ai/analyze",
        json={"job_description": JOB_DESCRIPTION},
    )
    assert analyze_response.status_code == 200

    request_payload = {
        "job_description": JOB_DESCRIPTION,
        "session_id": analyze_response.get_json()["session_id"],
    }
    if request_keys is not None:
        request_payload["enabled_experience_keys"] = request_keys

    response = client.post("/api/ai/generate-core", json=request_payload)
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["core"]["_enabled_experience_keys"] == expected_keys
    session = resume_app.ai_sessions[payload["session_id"]]
    assert session["enabled_experience_keys"] == expected_keys
    assert session["core_resume"]["_enabled_experience_keys"] == expected_keys

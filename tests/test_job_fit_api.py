import app as resume_app


def _context():
    return {
        "source": "greenhouse",
        "external_job_id": "123",
        "url": "https://example.com/jobs/123",
        "company_name": "Example",
        "role_title": "Application Engineer",
        "location": "Dallas, TX",
        "job_description": "Build backend services, APIs, and cloud automation using Python and AWS. " * 4,
    }


def test_job_fit_endpoint_uses_decisions_and_returns_suitable(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _key: None)
    monkeypatch.setattr(resume_app, "save_cached_ai_stage_result", lambda **_kwargs: None)

    def fake_request(**kwargs):
        captured.update(kwargs)
        return {
            "model": "gpt-6-luna",
            "answers": [
                {"type": "predicate", "name": "software_related", "probability": 0.98},
                {"type": "predicate", "name": "over_six_years_required", "probability": 0.02},
                {"type": "predicate", "name": "advanced_seniority_scope", "probability": 0.05},
            ],
        }

    monkeypatch.setattr(resume_app, "_request_openai_json", fake_request)
    response = resume_app.app.test_client().post("/api/job-fit/check", json={"context": _context()})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["job_fit"]["status"] == "suitable"
    assert captured["url"] == "https://api.openai.com/v1/decisions"
    assert captured["payload"]["model"] == "gpt-6-luna"
    assert [item["name"] for item in captured["payload"]["questions"]] == [
        "software_related", "over_six_years_required", "advanced_seniority_scope"
    ]
    assert "candidate_profile" not in captured["payload"]["input"]


def test_job_fit_rejects_non_software_application_engineer(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _key: None)
    monkeypatch.setattr(resume_app, "save_cached_ai_stage_result", lambda **_kwargs: None)
    monkeypatch.setattr(resume_app, "_request_openai_json", lambda **_kwargs: {
        "model": "gpt-6-luna",
        "answers": [
            {"type": "predicate", "name": "software_related", "probability": 0.04},
            {"type": "predicate", "name": "over_six_years_required", "probability": 0.02},
            {"type": "predicate", "name": "advanced_seniority_scope", "probability": 0.04},
        ],
    })

    response = resume_app.app.test_client().post("/api/job-fit/check", json={"context": _context()})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["job_fit"]["status"] == "not_suitable"
    assert payload["job_fit"]["suitable"] is False


def test_job_fit_rejects_software_role_that_requires_over_six_years(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _key: None)
    monkeypatch.setattr(resume_app, "save_cached_ai_stage_result", lambda **_kwargs: None)
    monkeypatch.setattr(resume_app, "_request_openai_json", lambda **_kwargs: {
        "model": "gpt-6-luna",
        "answers": [
            {"type": "predicate", "name": "software_related", "probability": 1.0},
            {"type": "predicate", "name": "over_six_years_required", "probability": 0.99},
            {"type": "predicate", "name": "advanced_seniority_scope", "probability": 0.30},
        ],
    })

    response = resume_app.app.test_client().post("/api/job-fit/check", json={"context": _context()})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["job_fit"]["status"] == "not_suitable"
    assert payload["job_fit"]["suitable"] is False
    assert payload["job_fit"]["reasons"] == [
        "The job requires more than six years of relevant professional experience."
    ]


def test_job_fit_rejects_principal_scope_without_numeric_years(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _key: None)
    monkeypatch.setattr(resume_app, "save_cached_ai_stage_result", lambda **_kwargs: None)
    monkeypatch.setattr(resume_app, "_request_openai_json", lambda **_kwargs: {
        "model": "gpt-6-luna",
        "answers": [
            {"type": "predicate", "name": "software_related", "probability": 1.0},
            {"type": "predicate", "name": "over_six_years_required", "probability": 0.10},
            {"type": "predicate", "name": "advanced_seniority_scope", "probability": 0.95},
        ],
    })

    response = resume_app.app.test_client().post("/api/job-fit/check", json={"context": _context()})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["job_fit"]["status"] == "not_suitable"
    assert "advanced scope" in payload["job_fit"]["message"]


def test_job_fit_cache_skips_decisions_call(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _key: {
        "status": "suitable", "suitable": True, "message": "Cached", "model": "gpt-6-luna"
    })
    monkeypatch.setattr(resume_app, "_request_openai_json", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("API called")))

    response = resume_app.app.test_client().post("/api/job-fit/check", json={"context": _context()})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["job_fit"]["cached"] is True


def test_job_fit_cache_only_does_not_call_decisions_when_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(resume_app, "get_cached_ai_stage_result", lambda _key: None)
    monkeypatch.setattr(resume_app, "_request_openai_json", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("API called")))

    response = resume_app.app.test_client().post(
        "/api/job-fit/check",
        json={"context": _context(), "cache_only": True},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["job_fit"] is None

import app as resume_app


def _cpt_result(blocked=True):
    return {
        "status": "review" if blocked else "green",
        "blocked": blocked,
        "company_name": "Apple",
        "matched_company_name": "Apple",
        "cpt_friendly": False,
        "cpt_onboard": False,
        "cpt_agreement": "Not Supporting" if blocked else "Supporting",
        "source_url": "https://day1cpt.org/day-1-cpt/employers",
        "checked_at": "2026-09-03T00:00:00+00:00",
        "expires_at": "2026-09-10T00:00:00+00:00",
        "message": "Company is not CPT onboarding friendly.",
        "source_snapshot": {},
    }


def test_cpt_check_endpoint_returns_structured_result(monkeypatch):
    monkeypatch.setattr(resume_app, "check_cpt_company", lambda company_name, force_refresh=False: _cpt_result(False))

    response = resume_app.app.test_client().post(
        "/api/cpt/check",
        json={"company_name": "Apple"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["cpt"]["status"] == "green"


def test_ai_analyze_warns_but_allows_non_green_company(monkeypatch):
    called = {"openai": False}
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(resume_app, "check_cpt_company", lambda company_name: _cpt_result(True))

    def fake_analyze(**_kwargs):
        called["openai"] = True
        return {"company_name": "Apple", "target_role": "Backend Engineer"}

    monkeypatch.setattr(resume_app, "analyze_job_description", fake_analyze)

    response = resume_app.app.test_client().post(
        "/api/ai/analyze",
        json={
            "company_name": "Apple",
            "job_description": "Company: Apple\nBuild reliable backend services with Python and PostgreSQL.",
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["preflight"]["cpt"]["blocked"] is True
    assert payload["preflight"]["blocked"] is False
    assert called["openai"] is True


def test_extension_draft_warns_but_allows_non_green_company(monkeypatch):
    monkeypatch.setattr(resume_app, "has_permanent_profile_doc", lambda: True)
    monkeypatch.setattr(resume_app, "check_cpt_company", lambda company_name: _cpt_result(True))
    monkeypatch.setattr(resume_app, "extension_profile_snapshot", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(resume_app, "tracker_company_history", lambda _company: {"count": 0, "applications": []})
    monkeypatch.setattr(resume_app, "create_extension_draft_with_gate", lambda context, *_args: {
        "id": "draft-cpt-warning",
        **context,
        "status": "queued",
        "stage": "waiting",
    })
    monkeypatch.setattr(resume_app, "extension_draft_payload", lambda draft: draft)
    monkeypatch.setattr(resume_app.extension_worker_event, "set", lambda: None)

    response = resume_app.app.test_client().post(
        "/api/extension/drafts",
        json={
            "context": {
                "source": "linkedin",
                "external_job_id": "123",
                "url": "https://www.linkedin.com/jobs/view/123/",
                "company_name": "Apple",
                "role_title": "Backend Engineer",
                "job_description": "Build reliable backend services with Python and PostgreSQL. " * 4,
            }
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["preflight"]["cpt"]["blocked"] is True
    assert payload["preflight"]["blocked"] is False
    assert payload["draft"]["id"] == "draft-cpt-warning"

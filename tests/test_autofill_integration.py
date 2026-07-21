import json
from pathlib import Path

import app as resume_app


def complete_profile(application=None):
    return {
        "name": "Test Candidate",
        "contact": {"location": "Austin, TX", "phone": "555-0100", "email": "test@example.com"},
        "application": application or {"workAuthorization": "yes", "autoFillEnabled": True},
        "projects": [{"name": "Project", "bullets": ["Built a working system."]}],
        "certifications": ["Certification"],
        "experience_history": [
            {
                "key": "mckinsey",
                "company": "Example Co",
                "location": "Austin, TX",
                "title": "Software Engineer",
                "dates": "2024 - Present",
                "enabled": True,
            }
        ],
    }


def configure_profile_files(monkeypatch, tmp_path, profile):
    permanent = tmp_path / "user_profile.json"
    session = tmp_path / "session_profile.json"
    permanent.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setattr(resume_app, "PERMANENT_PROFILE_FILE", permanent)
    monkeypatch.setattr(resume_app, "SESSION_PROFILE_FILE", session)
    return permanent, session


def test_autofill_profile_uses_identity_and_application_data(monkeypatch, tmp_path):
    configure_profile_files(monkeypatch, tmp_path, complete_profile({
        "firstName": "Test",
        "lastName": "Candidate",
        "workAuthorization": "yes",
        "autoFillEnabled": True,
    }))
    monkeypatch.setattr(resume_app, "settings", {
        "output_directory": str(tmp_path),
        "identities": [{
            "id": "primary",
            "label": "Primary",
            "location": "Dallas, TX",
            "phone": "555-0199",
            "email": "primary@example.com",
            "format_profile": "outlook",
        }],
    })

    payload = resume_app.app.test_client().get("/api/extension/autofill-profile?identity_id=primary").get_json()

    assert payload["success"] is True
    assert payload["profile"]["fullName"] == "Test Candidate"
    assert payload["profile"]["email"] == "primary@example.com"
    assert payload["profile"]["workAuthorization"] == "yes"


def test_regular_profile_save_preserves_application_section(monkeypatch, tmp_path):
    permanent, _ = configure_profile_files(
        monkeypatch,
        tmp_path,
        complete_profile({"githubUrl": "https://github.com/example", "autoFillEnabled": False}),
    )
    updated = complete_profile()
    updated.pop("application")
    updated["name"] = "Updated Candidate"
    updated["save_target"] = "permanent"

    response = resume_app.app.test_client().post("/api/profile", json=updated)

    assert response.status_code == 200
    saved = json.loads(permanent.read_text(encoding="utf-8"))
    assert saved["name"] == "Updated Candidate"
    assert saved["application"]["githubUrl"] == "https://github.com/example"
    assert saved["application"]["autoFillEnabled"] is False


def test_manifest_loads_autofill_runtime_for_original_platforms():
    manifest = json.loads(Path("extension/public/manifest.json").read_text(encoding="utf-8"))
    autofill_script = next(
        item for item in manifest["content_scripts"]
        if "autofill-content.js" in item.get("js", [])
    )

    matches = " ".join(autofill_script["matches"])
    for platform in ("greenhouse.io", "lever.co", "workday.com", "ashbyhq.com", "icims.com", "taleo.net", "oraclecloud.com", "smartrecruiters.com", "jobvite.com", "avature.net", "successfactors.com", "phenompeople.com"):
        assert platform in matches
    assert autofill_script["all_frames"] is True


def test_autofill_runtime_never_submits_application():
    source = Path("extension/public/autofill-content.js").read_text(encoding="utf-8")
    assert ".submit(" not in source
    assert "requestSubmit(" not in source


def test_embedded_panel_has_clipboard_write_access():
    manifest = json.loads(Path("extension/public/manifest.json").read_text(encoding="utf-8"))
    panel_host = Path("extension/public/panel-host.js").read_text(encoding="utf-8")

    assert "clipboardWrite" in manifest["permissions"]
    assert 'frame.setAttribute("allow", "clipboard-write")' in panel_host


def test_application_answer_rejects_sensitive_question(monkeypatch):
    monkeypatch.setattr(resume_app.extension_drafts, "get", lambda _draft_id: {
        "id": "draft-sensitive",
        "status": "pdf_ready",
        "stage": "complete",
        "pdf_path": "/tmp/resume.pdf",
        "pdf_stale": False,
        "resume_revision": 2,
        "pdf_revision": 2,
        "pdf_generated_at": "2026-07-21T12:00:00+00:00",
    })

    response = resume_app.app.test_client().post(
        "/api/extension/drafts/draft-sensitive/application-answer",
        json={"question": "Will you now or in the future require visa sponsorship?"},
    )

    assert response.status_code == 400
    assert "personal or legal confirmation" in response.get_json()["error"]


def test_followup_character_limit_is_given_to_model(monkeypatch):
    captured = {}

    def fake_text_output(**kwargs):
        captured.update(kwargs)
        return "A concise and grounded answer."

    monkeypatch.setattr(resume_app, "call_openai_text_output", fake_text_output)
    payload = resume_app.generate_followup_answer(
        api_key="test-key",
        job_description="Build reliable APIs.",
        analysis_payload={},
        question="Why are you interested in this role?",
        resume_pdf_text="Software engineer with API experience.",
        max_characters=300,
    )

    assert "at most 300 characters" in captured["user_prompt"]
    assert payload["char_count"] == len(payload["answer"])
    assert payload["max_characters"] == 300

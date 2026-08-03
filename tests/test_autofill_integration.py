import json
from datetime import datetime, timedelta, timezone
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


def test_company_owned_career_sites_use_detected_and_confirmed_generic_autofill():
    manifest = json.loads(Path("extension/public/manifest.json").read_text(encoding="utf-8"))
    service_worker = Path("extension/public/service-worker.js").read_text(encoding="utf-8")
    panel = Path("extension/src/panel-main.jsx").read_text(encoding="utf-8")
    autofill = Path("extension/public/autofill-content.js").read_text(encoding="utf-8")
    assistant = Path("extension/public/application-assistant.js").read_text(encoding="utf-8")
    assistant_script = next(
        item for item in manifest["content_scripts"]
        if "application-assistant.js" in item.get("js", [])
    )

    assert "http://*/*" in manifest["host_permissions"]
    assert "https://*/*" in manifest["host_permissions"]
    assert assistant_script["matches"] == ["http://*/*", "https://*/*"]
    assert assistant_script.get("all_frames") is not True
    assert "function isInspectableWebUrl" in service_worker
    assert "inspectGeneric" in service_worker
    assert "allowGeneric: genericInspection" in service_worker
    assert "AUTOFILL_APPLICATION_CANDIDATE" in assistant
    assert "AUTOFILL_CONFIRM_FILL" in assistant
    assert "AUTOFILL_ANSWER_QUESTION" in assistant
    assert "AUTOFILL_GET_RECENT_RESUMES" in assistant
    assert "AUTOFILL_ATTACH_RESUME" in assistant
    assert "Ask AI" in assistant
    assert "Attach selected resume" in assistant
    assert "Resume to attach and answer with" in assistant
    assert "Fill this application" in assistant
    assert "Needs attention" in assistant
    assert "applicationScope" in service_worker
    assert "chrome.storage.session" in service_worker
    assert "refreshAutofillStatus(identityId, false, true)" in panel
    assert "fields.length >= 3 && hasIdentity && hasApplicationField" in autofill


def test_autofill_runtime_never_submits_application():
    for source_path in (
        "extension/public/autofill-content.js",
        "extension/public/application-assistant.js",
    ):
        source = Path(source_path).read_text(encoding="utf-8")
        assert ".submit(" not in source
        assert "requestSubmit(" not in source


def test_continued_autofill_requires_application_approval_and_skips_sensitive_fields():
    source = Path("extension/public/autofill-content.js").read_text(encoding="utf-8")

    assert 'send({ type: "AUTOFILL_GET_APPROVAL" })' in source
    assert 'approval?.mode !== "application"' in source
    assert "if (!approved)" in source
    assert "safeOnly && config.sensitiveFields.has(match.dataField)" in source
    assert "userProfile?.autoFillEnabled === false" in source


def test_compact_widget_uses_the_existing_resume_grounded_answer_flow():
    service_worker = Path("extension/public/service-worker.js").read_text(encoding="utf-8")

    assert 'message?.type === "AUTOFILL_ANSWER_QUESTION"' in service_worker
    assert "/api/extension/drafts?limit=50" in service_worker
    assert "/application-answer" in service_worker
    assert "resumeAutofillAnswers:" in service_worker
    assert "currentRecentPdfDrafts" in service_worker


def test_compact_widget_uses_explicit_recent_pdf_attachment_flow():
    service_worker = Path("extension/public/service-worker.js").read_text(encoding="utf-8")
    assistant = Path("extension/public/application-assistant.js").read_text(encoding="utf-8")

    assert 'message?.type === "AUTOFILL_GET_RECENT_RESUMES"' in service_worker
    assert 'message?.type === "AUTOFILL_ATTACH_RESUME"' in service_worker
    assert "recentPdfDrafts" in service_worker
    assert "attachResumeForDraft" in service_worker
    assert "resumeFileForDraft(selectedDraft.id)" in service_worker
    assert "AUTOFILL_ATTACH_FRAME" in service_worker
    assert 'type: "AUTOFILL_ATTACH_RESUME"' in assistant
    assert "draftId: selectedResumeId" in assistant


def test_embedded_panel_has_clipboard_write_access():
    manifest = json.loads(Path("extension/public/manifest.json").read_text(encoding="utf-8"))
    panel_host = Path("extension/public/panel-host.js").read_text(encoding="utf-8")

    assert "clipboardWrite" in manifest["permissions"]
    assert 'frame.setAttribute("allow", "clipboard-write")' in panel_host


def test_injected_panels_reject_invalid_extension_urls_and_replace_stale_instances():
    for source_path in ("extension/public/content-script.js", "extension/public/panel-host.js"):
        source = Path(source_path).read_text(encoding="utf-8")
        assert 'value.startsWith("chrome-extension://invalid")' in source
        assert "resumeGeneratorInstance" in source
        assert "panelContextInvalid" in source
        assert "contextWatchdog = setInterval" in source
        assert "clearInterval(contextWatchdog)" in source


def test_embedded_panel_stops_messaging_after_extension_reload():
    source = Path("extension/src/panel-main.jsx").read_text(encoding="utf-8")

    assert "if (!chrome.runtime?.id)" in source
    assert "The extension was reloaded. Refresh this page to reconnect." in source
    assert "chrome.runtime.sendMessage(message).catch" in source


def test_manual_resume_edits_are_not_forced_through_ai_word_count_rules():
    issues = resume_app.validate_extension_manual_core(
        {
            "updated_title": "Software Engineer",
            "updated_summary": "Short, direct summary written by the candidate.",
        },
        {
            "updated_skills": [
                {"category": "Programming Languages", "items": ["Python", "Java"]},
            ]
        },
    )

    assert issues == []


def test_extension_copies_canonical_resume_content_after_saving_edits():
    source = Path("extension/src/panel-main.jsx").read_text(encoding="utf-8")

    assert "async function copyResumeContent()" in source
    assert "await persistQuickEdits()" in source
    assert "savedDraft?.resume_content" in source
    assert "Copy Content" in source


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


def test_application_answer_uses_current_pdf_metadata_not_status_label(monkeypatch, tmp_path):
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(resume_app.extension_drafts, "get", lambda _draft_id: {
        "id": "draft-current",
        "status": "ready",
        "pdf_path": str(pdf_path),
        "pdf_stale": False,
        "resume_revision": 3,
        "pdf_revision": 3,
        "pdf_generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis": {"role_family": "software_engineering"},
        "job_description": "Build reliable software products.",
    })
    monkeypatch.setattr(resume_app, "extract_text_from_pdf", lambda _path: "Current final resume.")
    monkeypatch.setattr(
        resume_app,
        "generate_followup_answer",
        lambda **_kwargs: {"answer": "I enjoy building reliable products.", "char_count": 36, "max_characters": None},
    )

    response = resume_app.app.test_client().post(
        "/api/extension/drafts/draft-current/application-answer",
        json={"question": "Why are you interested in this role?"},
    )

    assert response.status_code == 200
    assert response.get_json()["answer"]["answer"] == "I enjoy building reliable products."


def test_application_answer_reports_expired_pdf_before_ai_call(monkeypatch, tmp_path):
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(resume_app.extension_drafts, "get", lambda _draft_id: {
        "id": "draft-expired",
        "status": "pdf_ready",
        "pdf_path": str(pdf_path),
        "pdf_stale": False,
        "resume_revision": 1,
        "pdf_revision": 1,
        "pdf_generated_at": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(),
        "analysis": {"role_family": "software_engineering"},
    })
    monkeypatch.setattr(
        resume_app,
        "generate_followup_answer",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("AI should not be called for an expired PDF")),
    )

    response = resume_app.app.test_client().post(
        "/api/extension/drafts/draft-expired/application-answer",
        json={"question": "Why are you interested in this role?"},
    )

    assert response.status_code == 400
    assert "older than 24 hours" in response.get_json()["error"]


def test_message_followup_allows_older_current_pdf(monkeypatch, tmp_path):
    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(resume_app.extension_drafts, "get", lambda _draft_id: {
        "id": "draft-followup",
        "status": "pdf_ready",
        "pdf_path": str(pdf_path),
        "pdf_stale": False,
        "resume_revision": 2,
        "pdf_revision": 2,
        "pdf_generated_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
        "analysis": {"role_family": "software_engineering"},
        "job_description": "Build reliable software products.",
    })
    monkeypatch.setattr(resume_app, "extract_text_from_pdf", lambda _path: "Current final resume.")
    monkeypatch.setattr(
        resume_app,
        "generate_followup_answer",
        lambda **_kwargs: {"answer": "The work matches my backend experience.", "char_count": 39, "max_characters": None},
    )

    response = resume_app.app.test_client().post(
        "/api/extension/drafts/draft-followup/followup",
        json={"question": "Why are you interested in this role?"},
    )

    assert response.status_code == 200
    assert response.get_json()["followup"]["answer"] == "The work matches my backend experience."


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

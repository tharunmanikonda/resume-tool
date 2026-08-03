import copy
from pathlib import Path

import pytest

import app as resume_app


SUMMARY = (
    "Backend engineer with experience building reliable APIs and practical data workflows across "
    "enterprise and product environments. Delivered Python services, PostgreSQL integrations, cloud "
    "deployments, and observability improvements that made systems easier to operate. Work spans "
    "customer-facing delivery and internal platforms, with a focus on measurable outcomes, clear "
    "technical decisions, and dependable execution. Brings strong system design, testing, and "
    "collaboration skills to complex software problems without overstating domain experience. "
    "Communicates tradeoffs clearly and works closely with product and operations teams."
)

SKILLS = [
    {"category": "Programming Languages", "items": ["Python", "Java"]},
    {"category": "Backend Engineering", "items": ["RESTful APIs", "Microservices"]},
]


@pytest.fixture(autouse=True)
def isolated_sessions():
    resume_app.ai_sessions.clear()
    yield
    resume_app.ai_sessions.clear()


@pytest.fixture
def blueprints(monkeypatch):
    items = [copy.deepcopy(item) for item in resume_app.EXPERIENCE_BLUEPRINTS[:2]]
    for item in items:
        item["bullet_min"] = 2
        item["bullet_max"] = 2
    monkeypatch.setattr(
        resume_app,
        "current_experience_blueprints",
        lambda: copy.deepcopy(items),
    )
    return items


def canonical_resume(active_blueprints):
    return {
        "updated_title": "Backend Software Engineer",
        "updated_summary": SUMMARY,
        "updated_skills": copy.deepcopy(SKILLS),
        "experience": {
            blueprint["key"]: {
                "title": "Software Engineer",
                "bullets": [
                    (
                        f"Built reliable Python APIs that improved {blueprint['company']} workflow "
                        "reliability by 20% across delivery teams."
                    ),
                    (
                        "Delivered PostgreSQL integrations with cloud automation for dependable "
                        "customer-facing systems."
                    ),
                ],
            }
            for blueprint in active_blueprints
        },
    }


def completed_session(active_blueprints):
    session_id, session = resume_app.get_ai_session(
        None,
        "Build reliable Python APIs.",
        False,
    )
    enabled_keys = [blueprint["key"] for blueprint in active_blueprints]
    session["enabled_experience_keys"] = enabled_keys
    resume_app.update_ai_session_structured_resume(
        session,
        canonical_resume(active_blueprints),
        active_blueprints,
    )
    return session_id, session


def preview_override(active_blueprints):
    canonical = canonical_resume(active_blueprints)
    return {
        "title": canonical["updated_title"],
        "summary": canonical["updated_summary"],
        "technical_skills": copy.deepcopy(canonical["updated_skills"]),
        "experience": [
            {
                "company": blueprint["company"],
                "location": blueprint["location"],
                "title": canonical["experience"][blueprint["key"]]["title"],
                "dates": blueprint["dates"],
                "bullets": copy.deepcopy(
                    canonical["experience"][blueprint["key"]]["bullets"]
                ),
            }
            for blueprint in active_blueprints
        ],
        "_enabled_experience_keys": [
            blueprint["key"] for blueprint in active_blueprints
        ],
    }


def pdf_payload(
    *,
    content,
    active_blueprints,
    session_id=None,
    include_override=True,
    enabled_keys=None,
):
    payload = {
        "content": content,
        "company_name": "Example Company",
        "identity": "outlook",
        "enabled_experience_keys": (
            enabled_keys
            if enabled_keys is not None
            else [blueprint["key"] for blueprint in active_blueprints]
        ),
    }
    if session_id is not None:
        payload["ai_session_id"] = session_id
    if include_override:
        payload["resume_override"] = preview_override(active_blueprints)
    return payload


def block_build_side_effects(monkeypatch, tmp_path):
    monkeypatch.setitem(
        resume_app.settings,
        "output_directory",
        str(tmp_path),
    )

    def unexpected(*_args, **_kwargs):
        raise AssertionError("PDF build side effect occurred before the audit gate.")

    monkeypatch.setattr(resume_app, "build_resume_docx", unexpected)
    monkeypatch.setattr(resume_app, "start_pdf_conversion", unexpected)


def allow_build_side_effects(monkeypatch, tmp_path):
    calls = {"docx": 0, "pdf": 0}
    monkeypatch.setitem(
        resume_app.settings,
        "output_directory",
        str(tmp_path),
    )

    def build_docx(*_args, **_kwargs):
        calls["docx"] += 1

    def start_pdf(*_args, **_kwargs):
        calls["pdf"] += 1

    monkeypatch.setattr(resume_app, "build_resume_docx", build_docx)
    monkeypatch.setattr(resume_app, "start_pdf_conversion", start_pdf)
    return calls


def assert_no_output(tmp_path):
    assert list(Path(tmp_path).iterdir()) == []


def test_resume_override_without_ai_session_id_is_rejected_before_side_effects(
    monkeypatch,
    tmp_path,
    blueprints,
):
    active = blueprints[:1]
    content = resume_app.format_generated_resume_text(
        canonical_resume(active),
        active,
    )
    block_build_side_effects(monkeypatch, tmp_path)

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=pdf_payload(content=content, active_blueprints=active),
    )

    assert response.status_code == 400
    assert "active AI session" in response.get_json()["error"]
    assert_no_output(tmp_path)


def test_unknown_ai_session_is_rejected_before_side_effects(
    monkeypatch,
    tmp_path,
    blueprints,
):
    active = blueprints[:1]
    content = resume_app.format_generated_resume_text(
        canonical_resume(active),
        active,
    )
    block_build_side_effects(monkeypatch, tmp_path)

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=pdf_payload(
            content=content,
            active_blueprints=active,
            session_id="missing-session",
        ),
    )

    assert response.status_code == 404
    assert "session not found" in response.get_json()["error"].lower()
    assert_no_output(tmp_path)


@pytest.mark.parametrize(
    "audit_status",
    [
        "not_started",
        "running",
        "reviewing",
        "changes_suggested",
        "manual_attention",
        "technical_failed",
        "stale",
    ],
)
def test_unresolved_audit_states_are_rejected_before_build_side_effects(
    monkeypatch,
    tmp_path,
    blueprints,
    audit_status,
):
    active = blueprints[:1]
    session_id, session = completed_session(active)
    session["audit_status"] = audit_status
    block_build_side_effects(monkeypatch, tmp_path)

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=pdf_payload(
            content=session["resume_content"],
            active_blueprints=active,
            session_id=session_id,
        ),
    )

    assert response.status_code == 409
    assert response.get_json()["audit_status"] == audit_status
    assert_no_output(tmp_path)


@pytest.mark.parametrize(
    "audit_status",
    ["approved", "applied", "kept_current"],
)
def test_resolved_audit_states_are_allowed(
    monkeypatch,
    tmp_path,
    blueprints,
    audit_status,
):
    active = blueprints[:1]
    session_id, session = completed_session(active)
    session["audit_status"] = audit_status
    calls = allow_build_side_effects(monkeypatch, tmp_path)

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=pdf_payload(
            content=session["resume_content"],
            active_blueprints=active,
            session_id=session_id,
        ),
    )

    assert response.status_code == 200
    assert calls == {"docx": 1, "pdf": 1}


def test_edit_after_approval_advances_revision_and_allows_pdf(
    monkeypatch,
    tmp_path,
    blueprints,
):
    active = blueprints[:1]
    session_id, session = completed_session(active)
    session["audit_status"] = "approved"
    previous_revision = session["resume_revision"]
    edited = canonical_resume(active)
    edited["updated_title"] = "Senior Backend Software Engineer"
    edited_content = resume_app.format_generated_resume_text(edited, active)
    calls = allow_build_side_effects(monkeypatch, tmp_path)

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=pdf_payload(
            content=edited_content,
            active_blueprints=active,
            session_id=session_id,
        ),
    )

    assert response.status_code == 200
    assert session["resume_revision"] == previous_revision + 1
    assert session["audit_status"] == "kept_current"
    assert calls == {"docx": 1, "pdf": 1}


def test_unchanged_content_does_not_spuriously_stale_audit(
    monkeypatch,
    tmp_path,
    blueprints,
):
    active = blueprints[:1]
    session_id, session = completed_session(active)
    session["audit_status"] = "approved"
    previous_revision = session["resume_revision"]
    calls = allow_build_side_effects(monkeypatch, tmp_path)

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=pdf_payload(
            content=session["resume_content"],
            active_blueprints=active,
            session_id=session_id,
        ),
    )

    assert response.status_code == 200
    assert session["resume_revision"] == previous_revision
    assert session["audit_status"] == "approved"
    assert calls == {"docx": 1, "pdf": 1}


def test_tampered_resume_override_cannot_bypass_audited_content(
    monkeypatch,
    tmp_path,
    blueprints,
):
    active = blueprints[:1]
    session_id, session = completed_session(active)
    session["audit_status"] = "approved"
    captured_documents = []
    monkeypatch.setitem(
        resume_app.settings,
        "output_directory",
        str(tmp_path),
    )

    def capture_document(resume, *_args, **_kwargs):
        captured_documents.append(copy.deepcopy(resume))

    monkeypatch.setattr(resume_app, "build_resume_docx", capture_document)
    monkeypatch.setattr(
        resume_app,
        "start_pdf_conversion",
        lambda *_args, **_kwargs: None,
    )
    payload = pdf_payload(
        content=session["resume_content"],
        active_blueprints=active,
        session_id=session_id,
    )
    payload["resume_override"]["title"] = "Tampered Executive Title"
    payload["resume_override"]["summary"] = (
        "This replacement summary was never reviewed and must not reach the document builder."
    )
    payload["resume_override"]["experience"][0]["title"] = "Tampered Role"
    payload["resume_override"]["experience"][0]["bullets"] = [
        "Invented an unaudited achievement with a 999% result."
    ]

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=payload,
    )

    assert response.status_code == 409
    assert "does not match the reviewed resume content" in response.get_json()["error"]
    assert captured_documents == []
    assert_no_output(tmp_path)


def test_changed_enabled_experience_selection_keeps_current_and_allows_pdf(
    monkeypatch,
    tmp_path,
    blueprints,
):
    session_id, session = completed_session(blueprints)
    session["audit_status"] = "approved"
    previous_revision = session["resume_revision"]
    calls = allow_build_side_effects(monkeypatch, tmp_path)

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=pdf_payload(
            content=session["resume_content"],
            active_blueprints=blueprints,
            session_id=session_id,
            enabled_keys=[blueprints[0]["key"]],
        ),
    )

    assert response.status_code == 200
    assert session["resume_revision"] == previous_revision + 1
    assert session["audit_status"] == "kept_current"
    assert session["enabled_experience_keys"] == [blueprints[0]["key"]]
    assert calls == {"docx": 1, "pdf": 1}


def test_legacy_request_without_resume_override_remains_compatible(
    monkeypatch,
    tmp_path,
    blueprints,
):
    active = blueprints[:1]
    content = resume_app.format_generated_resume_text(
        canonical_resume(active),
        active,
    )
    calls = allow_build_side_effects(monkeypatch, tmp_path)

    response = resume_app.app.test_client().post(
        "/api/generate",
        json=pdf_payload(
            content=content,
            active_blueprints=active,
            include_override=False,
        ),
    )

    assert response.status_code == 200
    assert calls == {"docx": 1, "pdf": 1}


def test_react_pdf_payload_includes_active_ai_session_id():
    source = Path("src/App.jsx").read_text(encoding="utf-8")
    generate_block = source[source.index('fetchJson("/api/generate"'):]
    generate_block = generate_block[:generate_block.index("});") + 3]

    assert "ai_session_id: aiSessionId" in generate_block

import copy

import app as resume_app


ENABLED_KEYS = ["mckinsey", "uber", "kpmg", "trigent"]


def parsed_editor_resume():
    return {
        "title": "Platform Engineer",
        "summary": "Platform engineer building reliable systems with practical experience across APIs and operations.",
        "technical_skills": [
            {"category": "Programming Languages", "items": "Python, Java"},
            {"category": "Cloud & Infrastructure", "items": ["AWS", "Docker"]},
        ],
        "experience": [
            {"title": "Senior Platform Engineer", "bullets": ["Built reliable APIs.", "Improved service health."]},
            {"title": "Platform Engineer", "bullets": ["Automated operational workflows."]},
            {"title": "Software Engineer", "bullets": ["Delivered backend integrations."]},
            {"title": "Frontend Developer", "bullets": ["Built responsive interfaces."]},
        ],
    }


def test_extension_payloads_from_content_returns_all_editor_sections(monkeypatch):
    parsed = parsed_editor_resume()
    monkeypatch.setattr(resume_app, "load_base_resume", lambda: {})
    monkeypatch.setattr(
        resume_app,
        "parse_updated_content_to_resume",
        lambda content, base_resume: copy.deepcopy(parsed),
    )
    monkeypatch.setattr(resume_app, "normalize_updated_skills", lambda skills: skills)

    payload = resume_app.extension_payloads_from_content(
        "edited resume content",
        {},
        ENABLED_KEYS,
    )

    assert payload == {
        "title_summary": {
            "updated_title": parsed["title"],
            "updated_summary": parsed["summary"],
        },
        "skills": {
            "updated_skills": [
                {"category": "Programming Languages", "items": ["Python", "Java"]},
                {"category": "Cloud & Infrastructure", "items": ["AWS", "Docker"]},
            ],
        },
        "experience_recent": {
            "experience": {
                "mckinsey": parsed["experience"][0],
                "uber": parsed["experience"][1],
            },
        },
        "experience_older": {
            "experience": {
                "kpmg": parsed["experience"][2],
                "trigent": parsed["experience"][3],
            },
        },
    }


class CapturingDraftStore:
    def __init__(self, draft):
        self.draft = copy.deepcopy(draft)
        self.last_values = None
        self.last_invalidate_pdf = None

    def get(self, draft_id):
        return copy.deepcopy(self.draft) if draft_id == self.draft["id"] else None

    def update(self, draft_id, values, *, invalidate_pdf=False):
        assert draft_id == self.draft["id"]
        self.last_values = copy.deepcopy(values)
        self.last_invalidate_pdf = invalidate_pdf
        self.draft.update(copy.deepcopy(values))
        return copy.deepcopy(self.draft)


def test_extension_full_editor_patch_persists_parsed_resume_payload(monkeypatch):
    parsed = parsed_editor_resume()
    draft = {
        "id": "draft-editor-sync",
        "status": "ready",
        "locked": False,
        "enabled_experience_keys": ENABLED_KEYS,
        "title_summary": {
            "updated_title": "Old Title",
            "updated_summary": "Old summary.",
        },
        "skills": {
            "updated_skills": [
                {"category": "Programming Languages", "items": ["Python"]},
            ],
        },
        "experience_recent": {"experience": {}},
        "experience_older": {"experience": {}},
        "resume_content": "old resume content",
    }
    store = CapturingDraftStore(draft)
    monkeypatch.setattr(resume_app, "extension_drafts", store)
    monkeypatch.setattr(resume_app, "validate_updated_content", lambda content: ([], []))
    monkeypatch.setattr(resume_app, "load_base_resume", lambda: {})
    monkeypatch.setattr(
        resume_app,
        "parse_updated_content_to_resume",
        lambda content, base_resume: copy.deepcopy(parsed),
    )
    monkeypatch.setattr(resume_app, "normalize_updated_skills", lambda skills: skills)
    monkeypatch.setattr(
        resume_app,
        "draft_resume_snapshot",
        lambda candidate: {
            "title": candidate["title_summary"]["updated_title"],
            "summary": candidate["title_summary"]["updated_summary"],
        },
    )
    monkeypatch.setattr(resume_app, "extension_draft_payload", lambda updated: updated)

    response = resume_app.app.test_client().patch(
        f"/api/extension/drafts/{draft['id']}",
        json={"resume_content": "fully edited resume content"},
    )

    assert response.status_code == 200
    assert store.last_invalidate_pdf is True
    assert store.last_values["resume_content"] == "fully edited resume content"
    assert store.last_values["title_summary"] == {
        "updated_title": parsed["title"],
        "updated_summary": parsed["summary"],
    }
    assert store.last_values["skills"]["updated_skills"][0] == {
        "category": "Programming Languages",
        "items": ["Python", "Java"],
    }
    assert store.last_values["experience_recent"]["experience"]["mckinsey"] == parsed["experience"][0]
    assert store.last_values["experience_recent"]["experience"]["uber"] == parsed["experience"][1]
    assert store.last_values["experience_older"]["experience"]["kpmg"] == parsed["experience"][2]
    assert store.last_values["experience_older"]["experience"]["trigent"] == parsed["experience"][3]
    assert store.last_values["resume_snapshot"] == {
        "title": parsed["title"],
        "summary": parsed["summary"],
    }

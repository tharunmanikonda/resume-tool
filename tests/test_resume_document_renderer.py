import json
from pathlib import Path

import pytest
from docx import Document

import app as resume_app
from resume_document_renderer import (
    ResumeDocumentValidationError,
    render_resume_document,
)
from resume_mcp import service


def direct_payload():
    return {
        "resume": {
            "name": "Direct Candidate",
            "summary": "Only explicitly supplied resume content should render.",
            "experience": [
                {
                    "company": "Example Company",
                    "title": "Software Engineer",
                    "bullets": ["Built a deterministic document workflow."],
                }
            ],
        },
        "output": {
            "relative_directory": "Tesla/Direct Role",
            "docx_file_name": "Custom Resume Name.docx",
            "json_file_name": "request.json",
        },
    }


def test_direct_renderer_uses_exact_names_and_omits_missing_sections(tmp_path):
    payload = direct_payload()

    result = render_resume_document(payload, tmp_path)

    expected_dir = tmp_path / "Tesla" / "Direct Role"
    assert result["success"] is True
    assert result["ai_calls"] == 0
    assert result["files"]["docx"] == str(expected_dir / "Custom Resume Name.docx")
    assert result["files"]["json"] == str(expected_dir / "request.json")
    assert "pdf" not in result["files"]
    assert result["rendered_sections"] == ["summary", "experience"]

    document = Document(result["files"]["docx"])
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Direct Candidate" in text
    assert "Only explicitly supplied resume content should render." in text
    assert "PROFESSIONAL EXPERIENCE" in text
    assert "TECHNICAL SKILLS" not in text
    assert "PROJECTS" not in text
    assert "EDUCATION" not in text
    assert "CERTIFICATIONS" not in text
    assert "Austin, TX" not in text

    saved_payload = json.loads(Path(result["files"]["json"]).read_text(encoding="utf-8"))
    assert saved_payload == payload


@pytest.mark.parametrize(
    "output",
    [
        {"relative_directory": "../outside", "docx_file_name": "resume.docx"},
        {"docx_file_name": "nested/resume.docx"},
        {"docx_file_name": "resume.pdf"},
        {"json_file_name": "resume.json"},
    ],
)
def test_direct_renderer_rejects_unsafe_or_incomplete_output(tmp_path, output):
    with pytest.raises(ResumeDocumentValidationError):
        render_resume_document({"resume": {"name": "Candidate"}, "output": output}, tmp_path)


def test_direct_api_passes_authoritative_payload_without_merging(monkeypatch, tmp_path):
    payload = direct_payload()
    captured = {}

    def fake_render(value, output_root):
        captured["payload"] = value
        captured["output_root"] = output_root
        return {"success": True, "ai_calls": 0, "files": {}}

    monkeypatch.setattr(resume_app, "render_direct_resume_document", fake_render)
    monkeypatch.setitem(resume_app.settings, "output_directory", str(tmp_path))

    response = resume_app.app.test_client().post(
        "/api/resume-documents/render",
        json=payload,
    )

    assert response.status_code == 200
    assert response.get_json()["ai_calls"] == 0
    assert captured == {"payload": payload, "output_root": str(tmp_path)}


def test_mcp_direct_renderer_passes_resume_and_output_unchanged(monkeypatch):
    resume = {"name": "MCP Candidate"}
    output = {"docx_file_name": "MCP Resume.docx"}
    captured = {}

    def fake_render(payload, output_root):
        captured["payload"] = payload
        captured["output_root"] = output_root
        return {"success": True, "ai_calls": 0}

    monkeypatch.setattr(service.resume_app, "render_direct_resume_document", fake_render)
    monkeypatch.setitem(service.resume_app.settings, "output_directory", "/tmp/resumes")

    result = service.render_resume_document(resume=resume, output=output)

    assert result == {"success": True, "ai_calls": 0}
    assert captured == {
        "payload": {"resume": resume, "output": output},
        "output_root": "/tmp/resumes",
    }

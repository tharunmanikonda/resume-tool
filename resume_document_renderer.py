"""Deterministic, AI-free resume rendering from an authoritative JSON payload."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pdf_builder import build_resume_docx, convert_docx_to_pdf_via_libreoffice


class ResumeDocumentValidationError(ValueError):
    pass


RESUME_FIELDS = {
    "name",
    "title",
    "contact",
    "summary",
    "technical_skills",
    "experience",
    "projects",
    "education",
    "certifications",
}
OUTPUT_FIELDS = {
    "relative_directory",
    "docx_file_name",
    "pdf_file_name",
    "json_file_name",
    "format_profile",
}


def _reject_unknown_fields(value: dict, allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ResumeDocumentValidationError(
            f"Unsupported {label} field(s): {', '.join(unknown)}"
        )


def _safe_file_name(value: object, extension: str, field: str) -> str:
    name = str(value or "").strip()
    if not name:
        raise ResumeDocumentValidationError(f"{field} cannot be empty when provided.")
    if Path(name).name != name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ResumeDocumentValidationError(f"{field} must be a file name, not a path.")
    if Path(name).suffix.lower() != extension:
        raise ResumeDocumentValidationError(f"{field} must end with {extension}.")
    return name


def _safe_relative_directory(output_root: Path, value: object) -> Path:
    raw = str(value or "").strip()
    if not raw:
        return output_root
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ResumeDocumentValidationError("relative_directory must be relative to the configured output directory.")
    resolved = (output_root / candidate).resolve()
    try:
        resolved.relative_to(output_root)
    except ValueError as exc:
        raise ResumeDocumentValidationError("relative_directory cannot leave the configured output directory.") from exc
    return resolved


def _validate_resume_shape(resume: dict) -> None:
    _reject_unknown_fields(resume, RESUME_FIELDS, "resume")
    if not resume:
        raise ResumeDocumentValidationError("resume must contain at least one field.")

    object_fields = {"contact"}
    list_fields = {"technical_skills", "experience", "projects", "education", "certifications"}
    for field in object_fields:
        if field in resume and not isinstance(resume[field], dict):
            raise ResumeDocumentValidationError(f"resume.{field} must be an object.")
    for field in list_fields:
        if field in resume and not isinstance(resume[field], list):
            raise ResumeDocumentValidationError(f"resume.{field} must be an array.")
    for field in ("name", "title", "summary"):
        if field in resume and not isinstance(resume[field], str):
            raise ResumeDocumentValidationError(f"resume.{field} must be a string.")

    contact = resume.get("contact")
    if isinstance(contact, dict):
        _reject_unknown_fields(contact, {"location", "phone", "email"}, "resume.contact")
        for field, value in contact.items():
            if not isinstance(value, str):
                raise ResumeDocumentValidationError(f"resume.contact.{field} must be a string.")

    list_schemas = {
        "technical_skills": ({"category", "items"}, {"category"}, {"items"}),
        "experience": ({"company", "location", "title", "dates", "bullets"}, {"company", "location", "title", "dates"}, {"bullets"}),
        "projects": ({"name", "bullets"}, {"name"}, {"bullets"}),
        "education": ({"degree", "institution", "dates"}, {"degree", "institution", "dates"}, set()),
    }
    for field, (allowed, text_fields, array_fields) in list_schemas.items():
        items = resume.get(field)
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ResumeDocumentValidationError(f"resume.{field}[{index}] must be an object.")
            _reject_unknown_fields(item, allowed, f"resume.{field}[{index}]")
            for item_field in text_fields:
                if item_field in item and not isinstance(item[item_field], str):
                    raise ResumeDocumentValidationError(
                        f"resume.{field}[{index}].{item_field} must be a string."
                    )
            for item_field in array_fields:
                if item_field not in item:
                    continue
                value = item[item_field]
                if item_field == "items" and isinstance(value, str):
                    continue
                if not isinstance(value, list) or any(not isinstance(entry, str) for entry in value):
                    raise ResumeDocumentValidationError(
                        f"resume.{field}[{index}].{item_field} must be an array of strings."
                    )

    certifications = resume.get("certifications")
    if isinstance(certifications, list) and any(not isinstance(item, str) for item in certifications):
        raise ResumeDocumentValidationError("resume.certifications must be an array of strings.")


def normalize_resume_document_payload(payload: dict, output_root: str | Path) -> tuple[dict, dict, Path]:
    if not isinstance(payload, dict):
        raise ResumeDocumentValidationError("The request body must be a JSON object.")
    _reject_unknown_fields(payload, {"resume", "output"}, "top-level")
    resume = payload.get("resume")
    output = payload.get("output")
    if not isinstance(resume, dict):
        raise ResumeDocumentValidationError("resume is required and must be an object.")
    if not isinstance(output, dict):
        raise ResumeDocumentValidationError("output is required and must be an object.")
    _validate_resume_shape(resume)
    _reject_unknown_fields(output, OUTPUT_FIELDS, "output")

    normalized_output = dict(output)
    for field, extension in (
        ("docx_file_name", ".docx"),
        ("pdf_file_name", ".pdf"),
        ("json_file_name", ".json"),
    ):
        if field in output:
            normalized_output[field] = _safe_file_name(output[field], extension, field)

    if not normalized_output.get("docx_file_name") and not normalized_output.get("pdf_file_name"):
        raise ResumeDocumentValidationError(
            "Provide docx_file_name, pdf_file_name, or both. No artifact name is inferred."
        )

    if "format_profile" in normalized_output:
        profile = str(normalized_output["format_profile"] or "").strip().lower()
        if profile not in {"outlook", "gmail"}:
            raise ResumeDocumentValidationError("format_profile must be outlook or gmail.")
        normalized_output["format_profile"] = profile

    root = Path(output_root).expanduser().resolve()
    output_directory = _safe_relative_directory(root, normalized_output.get("relative_directory"))
    return dict(resume), normalized_output, output_directory


def rendered_section_names(resume: dict) -> list[str]:
    sections = []
    for field in ("summary", "technical_skills", "experience", "projects", "education", "certifications"):
        value = resume.get(field)
        if isinstance(value, str):
            included = bool(value.strip())
        else:
            included = bool(value)
        if included:
            sections.append(field)
    return sections


def render_resume_document(payload: dict, output_root: str | Path) -> dict:
    """Render exactly the supplied resume fields without reading saved profile data."""
    resume, output, output_directory = normalize_resume_document_payload(payload, output_root)
    output_directory.mkdir(parents=True, exist_ok=True)

    docx_name = output.get("docx_file_name")
    pdf_name = output.get("pdf_file_name")
    json_name = output.get("json_file_name")
    format_profile = output.get("format_profile", "outlook")

    docx_path = output_directory / docx_name if docx_name else None
    pdf_path = output_directory / pdf_name if pdf_name else None
    temporary_docx: Path | None = None

    if docx_path is None:
        handle = tempfile.NamedTemporaryFile(
            prefix="resume-render-",
            suffix=".docx",
            dir=output_directory,
            delete=False,
        )
        handle.close()
        temporary_docx = Path(handle.name)
        build_path = temporary_docx
    else:
        build_path = docx_path

    try:
        build_resume_docx(resume, str(build_path), format_profile=format_profile)
        if pdf_path is not None:
            convert_docx_to_pdf_via_libreoffice(str(build_path), str(pdf_path))
    finally:
        if temporary_docx is not None:
            temporary_docx.unlink(missing_ok=True)

    json_path = None
    if json_name:
        json_path = output_directory / json_name
        reproducible_payload = {"resume": resume, "output": output}
        json_path.write_text(
            json.dumps(reproducible_payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    files = {}
    if docx_path is not None:
        files["docx"] = str(docx_path)
    if pdf_path is not None:
        files["pdf"] = str(pdf_path)
    if json_path is not None:
        files["json"] = str(json_path)

    return {
        "success": True,
        "ai_calls": 0,
        "output_directory": str(output_directory),
        "files": files,
        "rendered_sections": rendered_section_names(resume),
    }

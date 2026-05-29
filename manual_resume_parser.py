from __future__ import annotations

import copy
import re
from typing import Any

# Fixed experience order. Titles and bullets are parsed from user input.
COMPANIES = [
    {
        "key": "mckinsey",
        "company": "McKinsey & Company",
        "location": "CA, USA",
        "dates": "May 2025 – Present",
    },
    {
        "key": "uber",
        "company": "Uber",
        "location": "CA, USA",
        "dates": "February 2024 – May 2025",
    },
    {
        "key": "kpmg",
        "company": "KPMG",
        "location": "India",
        "dates": "September 2021 – July 2022",
    },
    {
        "key": "trigent",
        "company": "Trigent Software",
        "location": "India",
        "dates": "March 2020 – August 2021",
    },
]


def _clean_bullet(line: str) -> str:
    """Remove bullet markers and leading whitespace."""
    line = line.strip()
    # Remove bullet markers: •, -, *, ●, etc.
    line = re.sub(r"^[•\-\*\u2022\u25CF]\s*", "", line)
    return line.strip()


def _is_separator(line: str) -> bool:
    """Check if line is a separator (empty, dashes, etc)."""
    stripped = line.strip()
    return stripped in {"---", "—", "–", "⸻", "|", "||"} or not stripped


def _remove_unknown_sections(text: str) -> str:
    """Remove lines that are clearly extraneous sections (e.g., MATCH SCORE (%): 97%).
    Preserves bold markers and regular skill/bullet content.
    """
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that match patterns like "MATCH SCORE (%): 97%" or "CORE JOB FOCUS"
        # These typically have: ALL_CAPS with parentheses and/or percentage symbols, followed by optional value
        if re.match(r'^[A-Z][A-Z\s]*(\([^)]*\))?:\s*\d+%?\s*$', stripped):
            continue  # Skip lines like "MATCH SCORE (%): 97%"
        if re.match(r'^[A-Z][A-Z\s]+$', stripped) and len(stripped) > 10 and not any(c in stripped for c in ['•', '-', '*', '**']):
            # Skip ALL CAPS headers that are longer than 10 chars and don't contain bullet markers
            # But keep things like "PROFESSIONAL EXPERIENCE"
            if stripped not in {"PROFESSIONAL EXPERIENCE", "MODIFIED EXPERIENCE", "UPDATED TITLE", "UPDATED SUMMARY", "UPDATED SKILLS"}:
                continue
        result.append(line)
    return "\n".join(result)


def _marker_pattern(marker: str) -> re.Pattern:
    """Build a case-insensitive section marker pattern.

    The UI examples often use all-caps section headers, but pasted LLM output
    commonly uses title case and sometimes prefixes experience with "Updated".
    """
    normalized = marker.rstrip(":").strip()
    prefix = r"(?:UPDATED\s+)?" if normalized in {"PROFESSIONAL EXPERIENCE", "MODIFIED EXPERIENCE"} else ""
    return re.compile(rf"(?im)^\s*{prefix}{re.escape(normalized)}\s*:?\s*$")


def _between(text: str, start: str, end: str | None) -> str:
    """Extract text between two section markers."""
    start_match = _marker_pattern(start).search(text)
    if not start_match:
        return ""
    start_idx = start_match.end()
    if end is None:
        extracted = text[start_idx:].strip()
    else:
        end_match = _marker_pattern(end).search(text, start_idx)
        if not end_match:
            extracted = text[start_idx:].strip()
        else:
            extracted = text[start_idx:end_match.start()].strip()

    # For sections, remove extraneous content but preserve structure
    if end is not None:  # For intermediate sections
        extracted = _remove_unknown_sections(extracted)

    return extracted


def _parse_skills(skills_block: str) -> list[dict[str, str]]:
    """Parse skills section into category: items format."""
    skills: list[dict[str, str]] = []
    for raw in skills_block.splitlines():
        line = _clean_bullet(raw)
        if _is_separator(line):
            continue
        if ":" in line:
            category, items = line.split(":", 1)
            category = category.strip()
            items = items.strip()
            # Skip lines that look like extraneous metadata (e.g., "MATCH SCORE (%)" or "%)")
            if re.match(r'^[A-Z\s]*(\([^)]*\))?$', category) and items and items[0].isdigit():
                # Looks like "MATCH SCORE (%): 97%" - skip it
                continue
            if category and items:  # Only add if both parts are non-empty
                skills.append({"category": category, "items": items})
    return skills


def _clean_title(title: str) -> str:
    """Remove dates from title since they're hardcoded."""
    # Remove patterns like "| September 2021" or "| September 2021 – July 2022"
    title = re.sub(r'\s*\|\s*\w+\s+\d{4}.*', '', title)  # Remove "| Month Year ..."
    # Remove patterns like "– September 2021" or "- September 2021"
    title = re.sub(r'\s*[\–\-]\s*\w+\s+\d{4}.*', '', title)  # Remove "– Month Year ..."
    return title.strip()


def _looks_like_company_header(line: str) -> bool:
    cleaned = line.strip()
    if not cleaned or "|" not in cleaned:
        return False
    parts = [part.strip() for part in cleaned.split("|")]
    if len(parts) < 2:
        return False
    left, right = parts[0], parts[1]
    if not left or not right:
        return False
    if re.search(r"\d{4}", left):
        return False
    location_signals = {",", "usa", "india", "canada", "remote", "uk", "ca", "tx", "nc", "ny"}
    lower_right = right.lower()
    return any(signal in lower_right for signal in location_signals)


def _parse_experience_titles_and_bullets(text: str) -> list[dict[str, Any]]:
    """
    Parse experience sections in order rather than by exact company name.
    Returns one entry per fixed experience slot.
    """
    lines = text.split("\n")
    sections: list[list[str]] = []
    current_section: list[str] = []

    for raw_line in lines:
        cleaned = raw_line.strip()
        if _looks_like_company_header(cleaned):
            if current_section:
                sections.append(current_section)
            current_section = [cleaned]
            continue
        if current_section:
            current_section.append(raw_line)

    if current_section:
        sections.append(current_section)

    parsed: list[dict[str, Any]] = []
    for index in range(len(COMPANIES)):
        if index >= len(sections):
            parsed.append({"title": "", "bullets": []})
            continue

        section = sections[index]
        title = ""
        bullets: list[str] = []
        company_line_consumed = False

        for line in section:
            cleaned = _clean_bullet(line)
            if not cleaned or _is_separator(cleaned):
                continue
            if not company_line_consumed and _looks_like_company_header(cleaned):
                company_line_consumed = True
                continue
            if not title:
                if "|" in cleaned:
                    parts = [part.strip() for part in cleaned.split("|") if part.strip()]
                    title = _clean_title(parts[0] if parts else cleaned)
                else:
                    title = _clean_title(cleaned)
                continue
            bullets.append(cleaned)

        parsed.append({"title": title, "bullets": bullets})

    return parsed


def parse_updated_content_to_resume(updated_text: str, base_resume: dict) -> dict:
    """Parse updated content and merge with base resume."""
    resume = copy.deepcopy(base_resume)

    if not updated_text:
        return resume

    text = updated_text.replace("\r\n", "\n").replace("\r", "\n")

    # Extract top-level sections
    title = _between(text, "UPDATED TITLE", "UPDATED SUMMARY")
    if not title:
        title = _between(text, "UPDATED TITLE:", "UPDATED SUMMARY")

    summary = _between(text, "UPDATED SUMMARY", "UPDATED SKILLS")
    if not summary:
        summary = _between(text, "UPDATED SUMMARY:", "UPDATED SKILLS")

    # Skills section
    skills_text = _between(text, "UPDATED SKILLS", "PROFESSIONAL EXPERIENCE")
    if not skills_text:
        skills_text = _between(text, "UPDATED SKILLS:", "PROFESSIONAL EXPERIENCE")
    if not skills_text:
        skills_text = _between(text, "UPDATED SKILLS", "MODIFIED EXPERIENCE")
    if not skills_text:
        skills_text = _between(text, "UPDATED SKILLS:", "MODIFIED EXPERIENCE")

    # Experience section (everything after PROFESSIONAL EXPERIENCE or MODIFIED EXPERIENCE)
    exp_text = _between(text, "PROFESSIONAL EXPERIENCE", None)
    if not exp_text:
        exp_text = _between(text, "MODIFIED EXPERIENCE", None)

    # Parse sections
    skills = _parse_skills(skills_text) if skills_text else []
    company_data = _parse_experience_titles_and_bullets(exp_text) if exp_text else []

    # Update resume
    if title:
        resume["title"] = " ".join(title.split())
    if summary:
        resume["summary"] = " ".join(summary.split())
    if skills:
        resume["technical_skills"] = skills

    # Update experience with parsed titles and bullets
    # If the experience section exists but no company content has been generated yet,
    # do not fall back to the base resume's experience bullets.
    if exp_text is not None:
        for exp_entry in resume.get("experience", []):
            exp_entry["title"] = ""
            exp_entry["bullets"] = []

    # Keep slot order stable; titles and bullets come from parsed content.
    if company_data:
        for index, exp_entry in enumerate(resume.get("experience", [])):
            if index >= len(company_data):
                continue
            data = company_data[index]
            if data["title"]:
                exp_entry["title"] = data["title"]
            if data["bullets"]:
                exp_entry["bullets"] = data["bullets"]

    return resume


def validate_updated_content(updated_text: str) -> tuple[list[str], list[str]]:
    """Validate resume content."""
    errors, warnings = [], []

    if not updated_text or not updated_text.strip():
        errors.append("No content provided")
        return errors, warnings

    text = updated_text.lower()

    # Check for required sections
    has_title = "updated title" in text
    has_summary = "updated summary" in text
    has_skills = "updated skills" in text
    has_exp = "professional experience" in text or "modified experience" in text

    if not all([has_title, has_summary, has_skills, has_exp]):
        missing = []
        if not has_title:
            missing.append("UPDATED TITLE")
        if not has_summary:
            missing.append("UPDATED SUMMARY")
        if not has_skills:
            missing.append("UPDATED SKILLS")
        if not has_exp:
            missing.append("PROFESSIONAL EXPERIENCE or MODIFIED EXPERIENCE")
        errors.append(f"Missing sections: {', '.join(missing)}")

    return errors, warnings

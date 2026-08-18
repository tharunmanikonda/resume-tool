"""Deterministic job-description preflight checks."""

from __future__ import annotations

import re
from typing import Any


ALLOW_CLEARANCE_JOBS_SETTING = "allow_security_clearance_jobs"


SECURITY_RESTRICTED_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "security_clearance",
        "Security clearance",
        re.compile(
            r"\b(?:active\s+|current\s+)?(?:secret|top\s+secret|ts\/sci|ts-sci|sci|dod)\s+"
            r"(?:security\s+)?clearance\b",
            re.IGNORECASE,
        ),
    ),
    (
        "clearance_required",
        "Security clearance required",
        re.compile(
            r"\b(?:security\s+)?clearance\s+(?:is\s+)?(?:required|needed|mandatory)\b|"
            r"\brequires?\s+(?:an?\s+)?(?:active\s+|current\s+)?(?:security\s+)?clearance\b",
            re.IGNORECASE,
        ),
    ),
    (
        "clearance_eligibility",
        "Ability to obtain or maintain clearance",
        re.compile(
            r"\b(?:ability|eligible|eligibility|willingness)\s+to\s+"
            r"(?:obtain|hold|maintain)\s+(?:an?\s+)?(?:security\s+)?clearance\b",
            re.IGNORECASE,
        ),
    ),
    (
        "public_trust",
        "Public Trust",
        re.compile(
            r"\bpublic\s+trust\b(?:[\s\S]{0,100})\b(?:required|needed|mandatory|eligible|obtain|clearance)\b|"
            r"\b(?:required|need|must|ability|eligible|eligibility)(?:[\s\S]{0,100})\bpublic\s+trust\b",
            re.IGNORECASE,
        ),
    ),
    (
        "us_citizenship",
        "U.S. citizenship required",
        re.compile(
            r"\b(?:u\.?s\.?|united\s+states)\s+citizenship\s+(?:is\s+)?(?:required|needed|mandatory)\b|"
            r"\bmust\s+be\s+(?:a\s+)?(?:u\.?s\.?|united\s+states)\s+citizen\b|"
            r"\b(?:u\.?s\.?|united\s+states)\s+citizens?\s+only\b",
            re.IGNORECASE,
        ),
    ),
    (
        "export_control",
        "Export-control or ITAR restriction",
        re.compile(
            r"\b(?:itar|export\s+control(?:led)?|export\s+authorization)\b(?:[\s\S]{0,120})"
            r"\b(?:required|eligible|citizen|authorized|restriction|compliance)\b|"
            r"\b(?:required|eligible|citizen|authorized|restriction|compliance)(?:[\s\S]{0,120})"
            r"\b(?:itar|export\s+control(?:led)?|export\s+authorization)\b",
            re.IGNORECASE,
        ),
    ),
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _snippet(text: str, start: int, end: int, radius: int = 90) -> str:
    left = max(start - radius, 0)
    right = min(end + radius, len(text))
    return _compact(text[left:right])


def scan_security_restricted_job(job_description: str) -> dict[str, Any]:
    """Return matched clearance/citizenship/export-control requirements."""
    text = job_description or ""
    matches: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for code, label, pattern in SECURITY_RESTRICTED_PATTERNS:
        for match in pattern.finditer(text):
            excerpt = _snippet(text, match.start(), match.end())
            key = (code, excerpt.lower())
            if key in seen:
                continue
            seen.add(key)
            matches.append({
                "code": code,
                "label": label,
                "match": _compact(match.group(0)),
                "excerpt": excerpt,
            })
    return {"found": bool(matches), "matches": matches}


def evaluate_job_preflight(job_description: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Decide whether the JD should be blocked before AI generation."""
    current_settings = settings or {}
    scan = scan_security_restricted_job(job_description)
    allowed = bool(current_settings.get(ALLOW_CLEARANCE_JOBS_SETTING, False))
    blocked = bool(scan["found"] and not allowed)
    if blocked:
        message = (
            "This job mentions clearance, citizenship, Public Trust, ITAR, or export-control requirements. "
            "Your settings block these roles before resume generation because you marked them as not eligible."
        )
    elif scan["found"]:
        message = (
            "This job mentions clearance, citizenship, Public Trust, ITAR, or export-control requirements, "
            "but your settings allow these roles."
        )
    else:
        message = ""
    return {
        "blocked": blocked,
        "allowed": allowed,
        "category": "security_clearance",
        "message": message,
        "matches": scan["matches"],
    }

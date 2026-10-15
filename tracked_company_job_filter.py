"""Deterministic filtering shared by the tracked-company monitors."""

from __future__ import annotations

import re
from dataclasses import dataclass

from tesla_job_filter import PROFILE_SIGNALS, TeslaFilterResult


TARGET_TITLES = (
    ("database", r"\bdatabase (?:technician|administrator|analyst|coordinator|engineer)\b|\bjunior dba\b|\bsql developer\b"),
    ("debug_test", r"\bdebug technician\b|\bsoftware test technician\b|\bsystems? test technician\b"),
    ("systems_analysis", r"\bapplication systems? analyst\b|\bprogrammer analyst\b|\bit systems? analyst\b|\bcomputer systems? analyst\b"),
    ("integration", r"\b(?:application|systems?|software) integration engineer\b|\bintegration developer\b"),
    ("production", r"\bproduction engineer\b|\bsoftware operations engineer\b|\brelease engineer\b|\bbuild engineer\b|\bdeployment engineer\b"),
    ("backend", r"\bbackend\b"),
    ("full_stack", r"\bfull[ -]?stack\b|\bfullstack\b"),
    ("frontend", r"\bfront[ -]?end\b|\bfrontend\b"),
    ("mobile", r"\bmobile (?:app|application|software)\b|\bios engineer\b|\bandroid engineer\b"),
    ("data", r"\bdata engineer\b|\bdata platform\b|\bdata science engineer\b|\betl\b"),
    ("ai_ml", r"\b(?:ai|machine learning|ml) engineer\b"),
    ("qa", r"\bsoftware qa\b|\bqa automation\b|\bsdet\b|\bsoftware development engineer in test\b|\bsoftware (?:test|quality) engineer\b|\btest automation engineer\b|\bautomation tester\b|\bsoftware tester\b|\bsoftware validation engineer\b"),
    ("reliability", r"\bsite reliability\b|\bsre\b|\breliability engineer\b"),
    ("platform", r"\bplatform engineer\b|\bdevops engineer\b|\bcloud engineer\b|\bkubernetes.*engineer\b"),
    ("application", r"\bapplication (?:software )?(?:engineer|developer)\b"),
    ("software", r"\bsoftware (?:engineer|developer)\b|\bsoftware development engineer\b"),
)

TITLE_EXCLUSIONS = {
    "internship": r"\bintern(?:ship)?\b|\bco-?op\b|\bapprentice\b",
    "management": r"\bmanager\b|\bdirector\b|\bprogram manager\b",
    "support": r"\bsupport engineer\b|\bhelp desk\b|\bdesktop support\b|\btechnician\b",
    "level_too_senior": r"\bstaff\b|\bprincipal\b|\btechnical leader\b|\barchitect\b|\blead (?:software|site reliability|platform|data)\b",
    "embedded_or_hardware": r"\bembedded\b|\bfirmware\b|\bsilicon\b|\bfpga\b|\bhardware\b|\bcontrols?\b",
    "specialized_low_level": (
        r"\bc\+\+(?:\s|$)|\bcuda driver\b|\bgpu performance\b|\b(?:dft|dfx)\b|\beda\b|"
        r"\bcad tool\b|\bvlsi\b|\bcircuits?\b|\bsonic\b|\bcutlass\b|"
        r"\bautonomous vehicles?\b|\bgnn\b|\babap\b"
    ),
    "not_an_open_role": r"\btalent community\b|\bexpression of interest\b",
}

SUPPORTABLE_CATEGORIES = {"database", "debug_test"}
HARDWARE_DEBUG_PATTERN = (
    r"\bsolder(?:ing)?\b|\boscilloscope\b|\bmultimeter\b|\bpcb\b|\bcircuit boards?\b|"
    r"\bboard rework\b|\belectrical schematics?\b|\bbench equipment\b|\bcomponent-level\b"
)

NON_US = (
    r"\bindia\b", r"\bcanada\b", r"\bmexico\b", r"\bgermany\b", r"\bnetherlands\b",
    r"\bunited kingdom\b", r"\bfrance\b", r"\bitaly\b", r"\baustralia\b", r"\bchina\b",
    r"\bpoland\b", r"\btaiwan\b", r"\bjapan\b", r"\bsingapore\b", r"\bireland\b",
    r"\bisrael\b", r"\bnorway\b", r"\bsweden\b", r"\bromania\b", r"\bhungary\b",
    r"\bcosta rica\b", r"\bserbia\b", r"\bbelgium\b", r"\bspain\b", r"\bportugal\b",
    r"\bswitzerland\b", r"\bczechia\b", r"\bslovakia\b", r"\bthailand\b", r"\bvietnam\b",
)


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _category(title: str) -> str:
    for name, pattern in TARGET_TITLES:
        if re.search(pattern, title, re.IGNORECASE):
            return name
    return ""


def prefilter_company_job(job: dict) -> TeslaFilterResult:
    title = _text(job.get("title") or job.get("role_title"))
    location = _text(job.get("location"))
    job_type = _text(job.get("job_type") or job.get("type")).replace("_", " ")
    blockers = []
    category = _category(title)

    if job_type and not any(value in job_type for value in ("full time", "full-time", "contract")):
        blockers.append("not_target_employment_type")
    # A multi-location label needs the detail page before its country can be decided.
    if location and "location" not in location and any(re.search(pattern, location) for pattern in NON_US):
        blockers.append("non_us_location")
    for name, pattern in TITLE_EXCLUSIONS.items():
        if name == "support" and category in SUPPORTABLE_CATEGORIES:
            continue
        if re.search(pattern, title, re.IGNORECASE):
            blockers.append(name)

    if not category:
        blockers.append("title_not_targeted")
    if blockers:
        return TeslaFilterResult("filtered_out", "none", category or "other", 0, [], blockers)
    return TeslaFilterResult("needs_detail", "unranked", category, 0, [f"target_title:{category}"], [])


def _required_section(description: str) -> str:
    match = re.search(
        r"(?:minimum|required|basic) qualifications?\s*:?(.*?)(?:preferred|desired|nice to have|why cisco|ways to stand out|$)|"
        r"what we need to see\s*:?(.*?)(?:ways to stand out|preferred|desired|nice to have|$)",
        description,
        re.IGNORECASE | re.DOTALL,
    )
    return next((group for group in match.groups() if group), description) if match else description


def _requires_five_or_more(description: str) -> bool:
    required = _required_section(description)
    # A 3-5 year range remains eligible because the candidate satisfies its lower bound.
    required = re.sub(
        r"\b[0-4]\s*[-–]\s*(?:[5-9]|\d{2,})\s*\+?\s*(?:years?|yrs?)\b",
        "",
        required,
        flags=re.IGNORECASE,
    )
    return bool(re.search(
        r"\b(?:[5-9]|\d{2,})\s*\+?\s*(?:years?|yrs?)\b|"
        r"\b(?:at least|minimum(?:\s+of)?)\s+(?:[5-9]|\d{2,})\s*(?:years?|yrs?)\b|"
        r"\b(?:[5-9]|\d{2,})\s+(?:or more|plus)\s+(?:years?|yrs?)\b|"
        r"\b(?:five|six|seven|eight|nine|ten)\s+(?:years?|yrs?)\b",
        required,
        re.IGNORECASE,
    ))


def classify_company_job(job: dict) -> TeslaFilterResult:
    preflight = prefilter_company_job(job)
    if preflight.decision == "filtered_out":
        return preflight

    description = _text(job.get("description"))
    location = _text(job.get("location"))
    if location and not any(value in location for value in ("united states", " usa", " us", "remote")):
        if any(re.search(pattern, location) for pattern in NON_US):
            return TeslaFilterResult("filtered_out", "none", preflight.category, 0, preflight.reasons, ["non_us_location"])
    if _requires_five_or_more(description):
        return TeslaFilterResult(
            "filtered_out", "none", preflight.category, 0, preflight.reasons, ["minimum_experience_at_least_5_years"]
        )
    if preflight.category == "debug_test" and re.search(HARDWARE_DEBUG_PATTERN, description, re.IGNORECASE):
        return TeslaFilterResult(
            "filtered_out", "none", preflight.category, 0, preflight.reasons, ["hardware_debug_role"]
        )

    haystack = f"{_text(job.get('title'))} {description}"
    score = 0
    reasons = list(preflight.reasons)
    for name, (points, pattern) in PROFILE_SIGNALS.items():
        if re.search(pattern, haystack, re.IGNORECASE):
            score += points
            reasons.append(f"profile_signal:{name}:+{points}")

    if score >= 10:
        if preflight.category == "debug_test":
            return TeslaFilterResult("needs_review", "low", preflight.category, score, reasons, [])
        return TeslaFilterResult("candidate", "high", preflight.category, score, reasons, [])
    if score >= 6:
        if preflight.category == "debug_test":
            return TeslaFilterResult("needs_review", "low", preflight.category, score, reasons, [])
        return TeslaFilterResult("candidate", "medium", preflight.category, score, reasons, [])
    if score >= 3:
        return TeslaFilterResult("needs_review", "low", preflight.category, score, reasons, [])
    return TeslaFilterResult("filtered_out", "none", preflight.category, score, reasons, ["insufficient_profile_overlap"])


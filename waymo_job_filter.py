"""Incremental discovery and deterministic filtering for Waymo careers."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from tesla_job_filter import TeslaFilterResult, classify_tesla_job, prefilter_tesla_job


def canonical_waymo_url(value: str) -> str:
    parts = urlsplit(str(value or "").strip())
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def url_identity_hash(value: str) -> str:
    """Return the same compact FNV-1a identity used by the browser monitor."""
    result = 0x811C9DC5
    for byte in canonical_waymo_url(value).encode("utf-8"):
        result ^= byte
        result = (result * 0x01000193) & 0xFFFFFFFF
    return f"{result:08x}"


def select_new_listing_urls(jobs: list[dict], state: dict) -> list[dict]:
    known_hashes = {str(value) for value in state.get("known_url_hashes", [])}
    selected = []
    for job in jobs:
        identity = url_identity_hash(job.get("url", ""))
        if not job.get("url") or identity in known_hashes:
            continue
        selected.append({**job, "url_identity_hash": identity, "freshness_signal": "new_listing_url"})
    return selected


def prefilter_waymo_listing(job: dict):
    metadata = [str(value).lower() for value in job.get("metadata", [])]
    normalized = {
        **job,
        "job_type": "Full-Time" if "full-time" in metadata else " ".join(metadata),
        "location": " ".join(metadata),
    }
    return prefilter_tesla_job(normalized)


def classify_waymo_job(job: dict):
    metadata = [str(value).lower() for value in job.get("metadata", [])]
    normalized = {
        **job,
        "job_type": "Full-Time" if "full-time" in metadata else " ".join(metadata),
        "location": " ".join(metadata),
    }
    result = classify_tesla_job(normalized)
    requirements = " ".join(
        str(job.get(field) or "")
        for field in ("requirements", "description", "what_you_bring")
    )
    required_section = requirements
    section_match = re.search(r"\byou have\s*:\s*(.*?)(?:\bwe prefer\s*:|$)", requirements, re.IGNORECASE)
    if section_match:
        required_section = section_match.group(1)
    without_ranges = re.sub(
        r"\b[0-4]\s*[-–]\s*(?:[5-9]|\d{2,})\s+years?\b",
        "",
        required_section,
        flags=re.IGNORECASE,
    )
    minimum_five = re.search(
        r"\b(?:[5-9]|\d{2,})(?:\+|\s+or more)?\s+years?\b|"
        r"\b(?:at least|minimum(?:\s+of)?)\s+(?:[5-9]|\d{2,})\s+years?\b|"
        r"\b(?:minimum(?:\s+of)?\s+)?(?:five|six|seven|eight|nine|ten)\s+years?\b|"
        r">\s*4\s+years?\b",
        without_ranges,
        re.IGNORECASE,
    )
    if minimum_five:
        blockers = list(result.blockers)
        if "minimum_experience_at_least_5_years" not in blockers:
            blockers.append("minimum_experience_at_least_5_years")
        return TeslaFilterResult(
            "filtered_out",
            "none",
            result.category,
            result.score,
            list(result.reasons),
            blockers,
        )
    range_match = re.search(r"\b[0-4]\s*[-–]\s*5\s+years?\b", requirements, re.IGNORECASE)
    stretch_reason = "experience_stretch:5_years:-2"
    if range_match and stretch_reason in result.reasons and not result.blockers:
        score = result.score + 2
        reasons = [reason for reason in result.reasons if reason != stretch_reason]
        if score >= 10:
            decision, priority = "candidate", "high"
        elif score >= 6:
            decision, priority = "candidate", "medium"
        elif score >= 3:
            decision, priority = "needs_review", "low"
        else:
            decision, priority = "filtered_out", "none"
        return TeslaFilterResult(
            decision,
            priority,
            result.category,
            score,
            reasons,
            list(result.blockers),
        )
    return result


def extract_waymo_job_id(text: str) -> str | None:
    patterns = (
        r"(?:full-time|intern|temporary)\s+software engineering\s+(\d{3,8}(?:-\d+)?)\b",
        r"\bjob(?: id| requisition)?\s*[:#]?\s*(\d{3,8}(?:-\d+)?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, str(text or ""), re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def update_waymo_state(state: dict, observed_jobs: list[dict], scanned_at: str = "") -> dict:
    hashes = {str(value) for value in state.get("known_url_hashes", [])}
    ids = {str(value) for value in state.get("known_job_ids", []) if str(value)}
    for job in observed_jobs:
        if job.get("url"):
            hashes.add(url_identity_hash(job["url"]))
        job_id = job.get("job_id")
        if re.fullmatch(r"\d{3,8}(?:-\d+)?", str(job_id or "")):
            ids.add(str(job_id))
    numeric_bases = [int(value.split("-", 1)[0]) for value in ids]
    return {
        **state,
        "known_url_hashes": sorted(hashes),
        "known_job_ids": sorted(ids, key=lambda value: (int(value.split("-", 1)[0]), value)),
        "highest_seen_job_id": max(numeric_bases, default=state.get("highest_seen_job_id")),
        **({"last_successful_scan_at": scanned_at} if scanned_at else {}),
    }

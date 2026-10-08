"""Deterministic two-stage filtering for Tesla career listings."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


TARGET_TITLE_PATTERNS = (
    ("backend", r"\bbackend\b"),
    ("full_stack", r"\bfull[ -]?stack\b|\bfullstack\b"),
    ("frontend", r"\bfront[ -]?end\b|\bfrontend\b"),
    ("mobile", r"\bmobile (?:app|application|software)\b"),
    ("data", r"\bdata engineer\b|\bdata platform\b|\betl\b"),
    ("qa", r"\bsoftware qa\b|\bqa automation\b|\bsoftware validation\b|\btest automation\b"),
    ("reliability", r"\bsite reliability\b|\bsre\b"),
    ("software", r"\bsoftware engineer\b"),
)

TITLE_EXCLUSIONS = {
    "internship": r"\bintern(?:ship)?\b|\bco-?op\b|\bapprentice\b",
    "management": r"\bmanager\b|\bdirector\b|\btechnical program manager\b|\bprogram manager\b",
    "recruiting": r"\brecruiter\b|\bsourcer\b|\btalent acquisition\b",
    "support": r"\bapplication support\b|\bsupport engineer\b|\bhelp desk\b|\btechnician\b",
    "level_too_senior": r"\bstaff\b|\bprincipal\b|\blead (?:software|site reliability|platform|data)\b",
    "embedded_or_hardware": (
        r"\bembedded\b|\bfirmware\b|\bsilicon\b|\bfpga\b|\bhardware\b|"
        r"\bpower electronics\b|\bchassis controls\b|\bthermal systems\b"
    ),
    "specialized_non_target": r"\bbim\b|\btax\b|\bplm\b|\bmes support\b",
}

NON_US_LOCATION_PATTERNS = (
    r"\bindia\b", r"\bcanada\b", r"\bmexico\b", r"\bgermany\b", r"\bnetherlands\b",
    r"\bunited kingdom\b", r"\bfrance\b", r"\bitaly\b", r"\baustralia\b", r"\bchina\b",
    r"\bpoland\b", r"\bwarsaw\b", r"\btaiwan\b", r"\btaipei\b", r"\bhsinchu\b",
    r"\bjapan\b", r"\btokyo\b", r"\bsingapore\b",
    r"\bbengaluru\b", r"\bbangalore\b", r"\bkarnataka\b", r"\bhyderabad\b", r"\btelangana\b",
)

PROFILE_SIGNALS = {
    "python": (2, r"\bpython\b"),
    "go": (2, r"\bgo(?:lang)?\b"),
    "java": (1, r"\bjava\b"),
    "javascript_react": (1, r"\bjavascript\b|\btypescript\b|\breact\b"),
    "backend_apis": (2, r"\bbackend\b|\brest\b|\bgrpc\b|\bapi(?:s)?\b|\bmicroservices?\b"),
    "distributed_systems": (2, r"\bdistributed systems?\b|\bevent-driven\b|\basync(?:hronous)?\b"),
    "data_streaming": (2, r"\bkafka\b|\bflink\b|\betl\b|\bdata pipelines?\b|\bstream processing\b"),
    "databases": (1, r"\bpostgres(?:ql)?\b|\bredis\b|\bsql\b|\bnosql\b|\bclickhouse\b"),
    "cloud_containers": (2, r"\baws\b|\bcloud\b|\bdocker\b|\bkubernetes\b|\bargocd\b"),
    "observability": (1, r"\bobservability\b|\bprometheus\b|\bgrafana\b|\bopentelemetry\b"),
    "qa_automation": (2, r"\btest automation\b|\btest framework\b|\bsoftware testing\b|\bci/cd\b"),
    "agentic_tooling": (3, r"\bagent(?:ic|s)?\b|\bmcp\b|\bevaluation pipelines?\b|\bdeveloper tooling\b"),
}

DOMAIN_BLOCKERS = {
    "tax_domain": r"\btax engine\b|\bindirect tax\b|\bvertex\b|\bavalara\b",
    "embedded_core": r"\breal-time embedded\b|\bmicrocontroller\b|\bboard bring-up\b|\bautosar\b",
    "graphics_core": r"\bwebgl\b|\bopengl\b|\bthree\.js\b|\b2d/3d graphics\b",
}


@dataclass(frozen=True)
class TeslaFilterResult:
    decision: str
    priority: str
    category: str
    score: int
    reasons: list[str]
    blockers: list[str]


def job_id_number(job: dict) -> int | None:
    raw_value = job.get("id") or job.get("job_id") or job.get("external_job_id")
    match = re.search(r"\d+", str(raw_value or ""))
    return int(match.group()) if match else None


def select_unseen_jobs(jobs: list[dict], state: dict) -> dict:
    """Return unseen IDs above the completed-baseline high-water mark."""
    known_ids = {str(value) for value in state.get("known_job_ids", [])}
    previous_high = int(state.get("highest_seen_job_id") or 0)
    observed_ids = [value for job in jobs if (value := job_id_number(job)) is not None]
    highest_observed = max(observed_ids, default=previous_high)
    unseen = []
    for job in jobs:
        numeric_id = job_id_number(job)
        if numeric_id is None or numeric_id <= previous_high or str(numeric_id) in known_ids:
            continue
        unseen.append({**job, "freshness_signal": "above_high_watermark"})
    return {
        "previous_highest_seen_job_id": previous_high,
        "highest_observed_job_id": max(previous_high, highest_observed),
        "unseen_count": len(unseen),
        "jobs": unseen,
    }


def update_monitor_state(state: dict, jobs: list[dict], scanned_at: str = "") -> dict:
    known_ids = {str(value) for value in state.get("known_job_ids", [])}
    observed_ids = [value for job in jobs if (value := job_id_number(job)) is not None]
    known_ids.update(str(value) for value in observed_ids)
    highest_seen = max(
        [int(state.get("highest_seen_job_id") or 0), *observed_ids],
        default=0,
    )
    return {
        **state,
        "highest_seen_job_id": highest_seen,
        "known_job_ids": sorted(known_ids, key=int),
        **({"last_successful_scan_at": scanned_at} if scanned_at else {}),
    }


def _text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _first_match(patterns, text: str) -> str:
    for name, pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return ""


def prefilter_tesla_job(job: dict) -> TeslaFilterResult:
    title = _text(job.get("title") or job.get("role_title"))
    job_type = _text(job.get("type") or job.get("job_type"))
    location = _text(job.get("location"))

    blockers = []
    if job_type and not any(term in job_type for term in ("full-time", "full time")):
        blockers.append("not_full_time")
    if any(re.search(pattern, location) for pattern in NON_US_LOCATION_PATTERNS):
        blockers.append("non_us_location")
    for name, pattern in TITLE_EXCLUSIONS.items():
        if re.search(pattern, title):
            blockers.append(name)

    category = _first_match(TARGET_TITLE_PATTERNS, title)
    if not category:
        blockers.append("title_not_targeted")
    if blockers:
        return TeslaFilterResult("filtered_out", "none", category or "other", 0, [], blockers)
    return TeslaFilterResult("needs_detail", "unranked", category, 0, [f"target_title:{category}"], [])


def classify_tesla_job(job: dict) -> TeslaFilterResult:
    preflight = prefilter_tesla_job(job)
    if preflight.decision == "filtered_out":
        return preflight

    title = _text(job.get("title") or job.get("role_title"))
    description = _text(job.get("description"))
    requirements = _text(job.get("requirements") or job.get("what_you_bring"))
    haystack = " ".join((title, description, requirements))
    reasons = list(preflight.reasons)
    blockers = []
    score = 0

    for name, (points, pattern) in PROFILE_SIGNALS.items():
        if re.search(pattern, haystack):
            score += points
            reasons.append(f"profile_signal:{name}:+{points}")

    years = [int(value) for value in re.findall(r"\b(\d{1,2})\+?\s+years?\b", requirements)]
    minimum_years = max(years, default=0)
    if minimum_years >= 6:
        blockers.append(f"minimum_experience:{minimum_years}_years")
    elif minimum_years == 5:
        score -= 2
        reasons.append("experience_stretch:5_years:-2")

    for name, pattern in DOMAIN_BLOCKERS.items():
        if re.search(pattern, haystack):
            blockers.append(name)

    if blockers:
        return TeslaFilterResult("filtered_out", "none", preflight.category, score, reasons, blockers)
    if score >= 10:
        return TeslaFilterResult("candidate", "high", preflight.category, score, reasons, [])
    if score >= 6:
        return TeslaFilterResult("candidate", "medium", preflight.category, score, reasons, [])
    if score >= 3:
        return TeslaFilterResult("needs_review", "low", preflight.category, score, reasons, [])
    return TeslaFilterResult("filtered_out", "none", preflight.category, score, reasons, ["insufficient_profile_overlap"])


def filter_jobs(jobs: list[dict], include_review: bool = False) -> list[dict]:
    accepted = []
    allowed = {"candidate", "needs_review"} if include_review else {"candidate"}
    for job in jobs:
        result = classify_tesla_job(job) if job.get("description") or job.get("requirements") or job.get("what_you_bring") else prefilter_tesla_job(job)
        if result.decision in allowed or (result.decision == "needs_detail" and include_review):
            accepted.append({**job, "filter": asdict(result)})
    return accepted


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter Tesla jobs against Tharun's target profile.")
    parser.add_argument("input", type=Path, help="JSON file containing a job list or {'jobs': [...]}.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--state", type=Path, help="Optional monitor-state JSON used to skip known job IDs.")
    parser.add_argument("--update-state", action="store_true", help="Commit observed IDs after a successful scan.")
    parser.add_argument("--scanned-at", default="")
    parser.add_argument("--include-review", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text())
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else payload
    delta = None
    jobs_to_filter = jobs
    state = None
    if args.state:
        state = json.loads(args.state.read_text()) if args.state.exists() else {}
        delta = select_unseen_jobs(jobs, state)
        jobs_to_filter = delta["jobs"]
    result = {
        "input_count": len(jobs),
        "unseen_count": len(jobs_to_filter),
        "highest_observed_job_id": delta["highest_observed_job_id"] if delta else max(
            (job_id_number(job) or 0 for job in jobs), default=0
        ),
        "jobs": filter_jobs(jobs_to_filter, args.include_review),
    }
    if args.state and args.update_state:
        args.state.write_text(json.dumps(update_monitor_state(state or {}, jobs, args.scanned_at), indent=2) + "\n")
    rendered = json.dumps(result, indent=2, ensure_ascii=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    else:
        print(rendered)


if __name__ == "__main__":
    main()

"""Programmatic company job monitors with stable-ID state."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from tracked_company_job_filter import FILTER_VERSION, classify_company_job, prefilter_company_job


ROOT = Path(__file__).resolve().parent
FETCH_SCRIPT = ROOT / "ops" / "company_jobs_fetch.mjs"
COMPANIES = {
    "cbre",
    "cdk",
    "cisco",
    "ebay",
    "intepros",
    "iqvia",
    "nbcu",
    "nvidia",
    "occ",
    "ocient",
    "rivian",
}


def default_state_path(company: str) -> Path:
    return ROOT / "docs" / f"{company}-job-monitor-state.json"


def _run_fetcher(company: str, mode: str, payload: dict | None = None) -> dict:
    result = subprocess.run(
        ["node", str(FETCH_SCRIPT), company, mode],
        cwd=ROOT,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{company} fetcher exited with {result.returncode}.")
    return json.loads(result.stdout)


def fetch_listings(company: str, known_job_ids: set[str] | None = None) -> list[dict]:
    return _run_fetcher(company, "list", {"known_job_ids": sorted(known_job_ids or set())}).get("jobs", [])


def fetch_details(company: str, jobs: list[dict]) -> list[dict]:
    if not jobs:
        return []
    return _run_fetcher(company, "details", {"jobs": jobs}).get("details", [])


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")
    temporary.replace(path)


def _rejection_summary(job: dict, stage: str) -> dict:
    result = job.get("prefilter") if stage == "prefilter" else job.get("filter")
    return {
        "external_job_id": job.get("external_job_id"),
        "title": job.get("title"),
        "location": job.get("location"),
        "posted_at": job.get("posted_at"),
        "url": job.get("url"),
        "stage": stage,
        "category": (result or {}).get("category", "other"),
        "score": (result or {}).get("score", 0),
        "blockers": (result or {}).get("blockers", []),
        "reasons": (result or {}).get("reasons", []),
    }


def run_company_scan(
    company: str,
    state_path: Path | None = None,
    *,
    dry_run: bool = False,
    scanned_at: str | None = None,
) -> dict:
    if company not in COMPANIES:
        raise ValueError(f"Unsupported company: {company}")
    state_path = state_path or default_state_path(company)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    known_ids = {str(value) for value in state.get("known_job_ids", [])}
    rules_changed = int(state.get("filter_version") or 0) != FILTER_VERSION
    # Keep each source's normal newest-first stopping boundary during a rules
    # migration. Known jobs returned inside that bounded window are rechecked
    # below without forcing a full historical catalog download.
    listings = fetch_listings(company, known_ids)
    if not listings:
        raise RuntimeError(f"{company.title()} returned no listings; state was not changed.")

    candidate_ids = {str(value) for value in state.get("candidate_catalog", {})}
    unseen = [job for job in listings if str(job.get("external_job_id") or "") not in known_ids]
    recheck = [
        job for job in listings
        if rules_changed
        and str(job.get("external_job_id") or "") in known_ids
        and str(job.get("external_job_id") or "") not in candidate_ids
    ]
    jobs_to_evaluate = [*unseen, *recheck]
    survivors = []
    prefilter_rejections = []
    for job in jobs_to_evaluate:
        result = prefilter_company_job(job)
        enriched = {**job, "prefilter": asdict(result)}
        (survivors if result.decision == "needs_detail" else prefilter_rejections).append(enriched)

    details = fetch_details(company, survivors) if survivors else []
    detail_by_id = {str(item.get("external_job_id")): item for item in details}
    candidates = []
    needs_ai_review = []
    filtered_after_detail = []
    errors = []
    for job in survivors:
        external_id = str(job.get("external_job_id") or "")
        detail = detail_by_id.get(external_id, {})
        if detail.get("error") or not detail.get("description"):
            errors.append({**job, "error": detail.get("error") or "Empty detail page"})
            continue
        normalized = {**job, **detail}
        result = classify_company_job(normalized)
        enriched = {**normalized, "filter": asdict(result)}
        if result.decision == "candidate" and result.priority in {"high", "medium"}:
            candidates.append(enriched)
        elif result.decision == "needs_review":
            # This is the only bucket that may merit an AI call later. The normal
            # monitor path remains deterministic and incurs no model cost.
            needs_ai_review.append(enriched)
        else:
            filtered_after_detail.append(enriched)

    timestamp = scanned_at or datetime.now().astimezone().isoformat(timespec="seconds")
    if not dry_run and not errors:
        all_ids = known_ids | {
            str(job.get("external_job_id")) for job in listings if job.get("external_job_id")
        }
        candidate_catalog = dict(state.get("candidate_catalog", {}))
        rejected_catalog = dict(state.get("rejected_catalog", {}))
        for job in [*candidates, *needs_ai_review]:
            external_id = str(job.get("external_job_id") or "")
            if external_id:
                previous = candidate_catalog.get(external_id, {})
                candidate_catalog[external_id] = {
                    "title": job.get("title"),
                    "location": job.get("location"),
                    "url": job.get("url"),
                    "posted_at": job.get("posted_at"),
                    "first_seen_at": previous.get("first_seen_at", timestamp),
                    "priority": job.get("filter", {}).get("priority"),
                    "category": job.get("filter", {}).get("category"),
                }
                rejected_catalog.pop(external_id, None)
        rejected_jobs = [
            *[(job, "prefilter") for job in prefilter_rejections],
            *[(job, "detail") for job in filtered_after_detail],
        ]
        for job, stage in rejected_jobs:
            external_id = str(job.get("external_job_id") or "")
            if not external_id:
                continue
            result = job.get("prefilter") if stage == "prefilter" else job.get("filter")
            previous = rejected_catalog.get(external_id, {})
            rejected_catalog[external_id] = {
                "title": job.get("title"),
                "location": job.get("location"),
                "url": job.get("url"),
                "posted_at": job.get("posted_at"),
                "stage": stage,
                "blockers": (result or {}).get("blockers", []),
                "category": (result or {}).get("category", "other"),
                "filter_version": FILTER_VERSION,
                "first_seen_at": previous.get("first_seen_at", timestamp),
                "last_seen_at": timestamp,
            }
        compact_state = {key: value for key, value in state.items() if key != "catalog"}
        _write_json_atomic(state_path, {
            **compact_state,
            "company": company,
            "filter_version": FILTER_VERSION,
            "known_job_ids": sorted(all_ids),
            "candidate_catalog": candidate_catalog,
            "rejected_catalog": rejected_catalog,
            "last_successful_scan_at": timestamp,
        })

    candidates.sort(key=lambda job: (job.get("posted_at") or "", job.get("external_job_id") or ""), reverse=True)
    needs_ai_review.sort(key=lambda job: (job.get("posted_at") or "", job.get("external_job_id") or ""), reverse=True)
    return {
        "success": not errors,
        "company": company,
        "dry_run": dry_run,
        "scanned_at": timestamp,
        "fetched": len(listings),
        "unseen": len(unseen),
        "rechecked_after_filter_change": len(recheck),
        "filter_version": FILTER_VERSION,
        "filter_rules_changed": rules_changed,
        "prefilter_survivors": len(survivors),
        "detail_pages_fetched": len(details),
        "candidates": candidates,
        "needs_ai_review": needs_ai_review,
        "filtered_before_detail": len(prefilter_rejections),
        "filtered_after_detail": len(filtered_after_detail),
        "prefilter_rejections": [_rejection_summary(job, "prefilter") for job in prefilter_rejections],
        "detail_rejections": [_rejection_summary(job, "detail") for job in filtered_after_detail],
        "errors": errors,
        "state_updated": not dry_run and not errors,
        "ai_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan a supported company for new matching software jobs.")
    parser.add_argument("company", choices=sorted(COMPANIES))
    parser.add_argument("--state", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scanned-at")
    args = parser.parse_args()
    result = run_company_scan(args.company, args.state, dry_run=args.dry_run, scanned_at=args.scanned_at)
    rendered = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()


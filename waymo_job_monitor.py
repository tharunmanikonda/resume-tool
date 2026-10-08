"""Run the Waymo careers monitor without manual browser work."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from waymo_job_filter import (
    classify_waymo_job,
    extract_waymo_job_id,
    prefilter_waymo_listing,
    select_new_listing_urls,
    update_waymo_state,
    url_identity_hash,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_STATE = ROOT / "docs" / "waymo-job-monitor-state.json"
FETCH_SCRIPT = ROOT / "ops" / "waymo_fetch.mjs"


def _run_fetcher(mode: str, payload: dict | None = None) -> dict:
    result = subprocess.run(
        ["node", str(FETCH_SCRIPT), mode],
        cwd=ROOT,
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
        check=False,
        timeout=240,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or f"Waymo fetcher exited with {result.returncode}."
        raise RuntimeError(message)
    return json.loads(result.stdout)


def fetch_waymo_listings() -> list[dict]:
    return _run_fetcher("list").get("jobs", [])


def fetch_waymo_details(urls: list[str]) -> list[dict]:
    if not urls:
        return []
    return _run_fetcher("details", {"urls": urls}).get("details", [])


def _write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n")
    temporary.replace(path)


def run_waymo_scan(
    state_path: Path = DEFAULT_STATE,
    *,
    dry_run: bool = False,
    scanned_at: str | None = None,
) -> dict:
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    listings = fetch_waymo_listings()
    if not listings:
        raise RuntimeError("Waymo returned no Software Engineering listings; state was not changed.")

    new_listings = select_new_listing_urls(listings, state)
    prefilter_survivors = []
    prefilter_rejections = []
    for job in new_listings:
        result = prefilter_waymo_listing(job)
        enriched = {**job, "prefilter": asdict(result)}
        if result.decision == "needs_detail":
            prefilter_survivors.append(enriched)
        else:
            prefilter_rejections.append(enriched)

    # Waymo hides requisition IDs on detail pages. Fetch every unseen URL once so
    # the high-water mark reflects all new software listings, including noise.
    details = fetch_waymo_details([job["url"] for job in new_listings]) if new_listings else []
    detail_by_url = {detail["url"]: detail for detail in details}
    survivor_urls = {job["url"] for job in prefilter_survivors}
    candidates = []
    detail_rejections = []
    detail_errors = []
    resolved_ids = {}
    for job in new_listings:
        detail = detail_by_url.get(job["url"], {})
        if detail.get("error") or not detail.get("text"):
            detail_errors.append({**job, "error": detail.get("error") or "Empty detail page"})
            continue
        job_id = extract_waymo_job_id(detail["text"])
        resolved_ids[job["url"]] = job_id
        if job["url"] not in survivor_urls:
            continue
        result = classify_waymo_job({
            **job,
            "description": detail["text"],
            "requirements": detail["text"],
            "job_id": job_id,
        })
        enriched = {**job, "job_id": job_id, "filter": asdict(result)}
        if result.decision == "candidate" and result.priority in {"high", "medium"}:
            candidates.append(enriched)
        else:
            detail_rejections.append(enriched)

    previous_highest = int(state.get("highest_seen_job_id") or 0)
    newly_resolved = [
        {
            "url": job["url"],
            "title": job.get("title", ""),
            "job_id": resolved_ids.get(job["url"]),
            "freshness_signal": (
                "above_high_watermark"
                if _job_id_base(resolved_ids.get(job["url"])) > previous_highest
                else "new_url_at_or_below_high_watermark"
            ),
        }
        for job in new_listings
        if resolved_ids.get(job["url"])
    ]
    newly_resolved.sort(key=lambda job: _job_id_base(job["job_id"]), reverse=True)
    candidates.sort(key=lambda job: _job_id_base(job.get("job_id")), reverse=True)
    highest_observed = max(
        [previous_highest, *[_job_id_base(job["job_id"]) for job in newly_resolved]],
        default=previous_highest,
    )

    timestamp = scanned_at or datetime.now().astimezone().isoformat(timespec="seconds")
    if not dry_run and not detail_errors:
        observed = [{**job, "job_id": resolved_ids.get(job["url"])} for job in listings]
        _write_json_atomic(state_path, update_waymo_state(state, observed, timestamp))

    return {
        "success": not detail_errors,
        "dry_run": dry_run,
        "scanned_at": timestamp,
        "fetched": len(listings),
        "new_urls": len(new_listings),
        "previous_highest_job_id": previous_highest,
        "highest_observed_job_id": highest_observed,
        "new_jobs_by_id": newly_resolved,
        "prefilter_survivors": len(prefilter_survivors),
        "detail_pages_fetched": len(details),
        "candidates": candidates,
        "filtered_before_classification": len(prefilter_rejections),
        "filtered_after_detail": len(detail_rejections),
        "errors": detail_errors,
        "state_updated": not dry_run and not detail_errors,
    }


def _job_id_base(value: str | int | None) -> int:
    try:
        return int(str(value).split("-", 1)[0])
    except (TypeError, ValueError):
        return 0


def run_recent_waymo_matches(
    limit: int,
    state_path: Path = DEFAULT_STATE,
    *,
    scanned_at: str | None = None,
) -> dict:
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    listings = fetch_waymo_listings()
    if not listings:
        raise RuntimeError("Waymo returned no Software Engineering listings; state was not changed.")

    survivors = []
    for job in listings:
        result = prefilter_waymo_listing(job)
        if result.decision == "needs_detail":
            survivors.append(job)

    catalog = dict(state.get("listing_catalog", {})) if state.get("catalog_version") == 4 else {}
    uncached = [job for job in survivors if url_identity_hash(job["url"]) not in catalog]
    details = fetch_waymo_details([job["url"] for job in uncached]) if uncached else []
    detail_by_url = {detail["url"]: detail for detail in details}
    errors = []
    timestamp = scanned_at or datetime.now().astimezone().isoformat(timespec="seconds")

    for job in uncached:
        detail = detail_by_url.get(job["url"], {})
        if detail.get("error") or not detail.get("text"):
            errors.append({"url": job["url"], "error": detail.get("error") or "Empty detail page"})
            continue
        job_id = extract_waymo_job_id(detail["text"])
        result = classify_waymo_job({
            **job,
            "description": detail["text"],
            "requirements": detail["text"],
            "job_id": job_id,
        })
        catalog[url_identity_hash(job["url"])] = {
            "url": job["url"],
            "title": job["title"],
            "metadata": job.get("metadata", []),
            "job_id": job_id,
            "filter": asdict(result),
            "checked_at": timestamp,
        }

    if errors:
        return {
            "success": False,
            "scanned_at": timestamp,
            "fetched": len(listings),
            "eligible_titles": len(survivors),
            "detail_pages_fetched": len(details),
            "matches": [],
            "errors": errors,
            "state_updated": False,
        }

    active_hashes = {url_identity_hash(job["url"]) for job in survivors}
    matches = [
        entry for identity, entry in catalog.items()
        if identity in active_hashes
        and (
            (
                entry.get("filter", {}).get("decision") == "candidate"
                and entry.get("filter", {}).get("priority") in {"high", "medium"}
            )
            or entry.get("filter", {}).get("decision") == "needs_review"
        )
    ]
    matches.sort(key=lambda entry: (_job_id_base(entry.get("job_id")), entry.get("job_id", "")), reverse=True)

    updated_state = {
        **state,
        "catalog_version": 4,
        "listing_catalog": catalog,
        "recent_catalog_checked_at": timestamp,
    }
    resolved = [
        {"url": entry["url"], "job_id": entry.get("job_id")}
        for entry in catalog.values()
    ]
    _write_json_atomic(state_path, update_waymo_state(updated_state, resolved, timestamp))
    return {
        "success": True,
        "scanned_at": timestamp,
        "fetched": len(listings),
        "eligible_titles": len(survivors),
        "detail_pages_fetched": len(details),
        "cached_entries_reused": len(survivors) - len(uncached),
        "matching_count": len(matches),
        "strong_match_count": sum(
            entry.get("filter", {}).get("decision") == "candidate" for entry in matches
        ),
        "review_match_count": sum(
            entry.get("filter", {}).get("decision") == "needs_review" for entry in matches
        ),
        "matches": matches[:limit],
        "errors": [],
        "state_updated": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan Waymo for new matching software jobs.")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--scanned-at")
    parser.add_argument("--recent", type=int, metavar="COUNT")
    args = parser.parse_args()

    if args.recent:
        result = run_recent_waymo_matches(args.recent, args.state, scanned_at=args.scanned_at)
    else:
        result = run_waymo_scan(args.state, dry_run=args.dry_run, scanned_at=args.scanned_at)
    rendered = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()

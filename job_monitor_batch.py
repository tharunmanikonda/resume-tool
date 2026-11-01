"""Run all programmatic job monitors and produce a daily audit report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from company_job_monitor import COMPANIES, run_company_scan
from waymo_job_monitor import run_waymo_scan


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "docs" / "job-monitor-runs" / "latest.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "job-monitor-runs" / "latest.md"
DEFAULT_MONITORS = [*sorted(COMPANIES), "waymo"]


def _compact_candidate(candidate: dict) -> dict:
    result = candidate.get("filter", {})
    return {
        "job_id": candidate.get("external_job_id") or candidate.get("job_id"),
        "title": candidate.get("title"),
        "location": candidate.get("location") or candidate.get("metadata"),
        "posted_at": candidate.get("posted_at"),
        "url": candidate.get("url"),
        "priority": result.get("priority"),
        "matching_requirements": result.get("reasons", []),
        "material_gaps": result.get("blockers", []),
    }


def _compact_result(name: str, result: dict) -> dict:
    return {
        "monitor": name,
        "success": bool(result.get("success")),
        "scanned_at": result.get("scanned_at"),
        "fetched": result.get("fetched", 0),
        "unseen": result.get("unseen", result.get("new_urls", 0)),
        "state_updated": bool(result.get("state_updated")),
        "candidates": [
            _compact_candidate(candidate) for candidate in result.get("candidates", [])
        ],
        "needs_ai_review": [
            _compact_candidate(candidate) for candidate in result.get("needs_ai_review", [])
        ],
        "errors": result.get("errors", []),
    }


def run_batch(monitors: list[str], *, scanned_at: str | None = None) -> dict:
    timestamp = scanned_at or datetime.now().astimezone().isoformat(timespec="seconds")
    results = []
    for name in monitors:
        try:
            if name == "waymo":
                raw = run_waymo_scan(scanned_at=timestamp)
            else:
                raw = run_company_scan(name, scanned_at=timestamp)
            results.append(_compact_result(name, raw))
        except Exception as exc:  # A failed source must not stop successful sources.
            results.append({
                "monitor": name,
                "success": False,
                "scanned_at": timestamp,
                "fetched": 0,
                "unseen": 0,
                "state_updated": False,
                "candidates": [],
                "needs_ai_review": [],
                "errors": [{"error": str(exc)}],
            })

    candidates = [
        {"monitor": item["monitor"], **candidate}
        for item in results
        for candidate in item["candidates"]
    ]
    review = [
        {"monitor": item["monitor"], **candidate}
        for item in results
        for candidate in item["needs_ai_review"]
    ]
    failed = [item["monitor"] for item in results if not item["success"]]
    return {
        "success": not failed,
        "scanned_at": timestamp,
        "monitor_count": len(results),
        "successful_monitors": [item["monitor"] for item in results if item["success"]],
        "failed_monitors": failed,
        "candidate_count": len(candidates),
        "needs_ai_review_count": len(review),
        "candidates": candidates,
        "needs_ai_review": review,
        "results": results,
        "not_automated": {
            "tesla": "Tesla still requires a dedicated virtual-list browser runner with complete index coverage."
        },
    }


def render_markdown(report: dict) -> str:
    status = "Successful" if report["success"] else "Completed with failures"
    lines = [
        "# Daily job monitor report",
        "",
        f"- Status: **{status}**",
        f"- Scanned at: `{report['scanned_at']}`",
        f"- Monitors: {report['monitor_count']}",
        f"- New candidates: {report['candidate_count']}",
        f"- Needs review: {report['needs_ai_review_count']}",
        "",
        "## Monitor results",
        "",
        "| Monitor | Status | Fetched | Unseen | Candidates | Review | State updated |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["results"]:
        lines.append(
            f"| {item['monitor']} | {'ok' if item['success'] else 'failed'} | "
            f"{item['fetched']} | {item['unseen']} | {len(item['candidates'])} | "
            f"{len(item['needs_ai_review'])} | {'yes' if item['state_updated'] else 'no'} |"
        )

    if report["candidates"]:
        lines.extend(["", "## New candidates", ""])
        for candidate in report["candidates"]:
            label = candidate.get("title") or candidate.get("job_id") or "Job"
            url = candidate.get("url") or ""
            location = candidate.get("location") or "Location not provided"
            lines.append(
                f"- **{candidate['monitor']}**: [{label}]({url}) "
                f"({candidate.get('priority') or 'unranked'}; {location})"
            )
            reasons = candidate.get("matching_requirements") or []
            gaps = candidate.get("material_gaps") or []
            if reasons:
                lines.append(f"  Match: {', '.join(map(str, reasons))}")
            if gaps:
                lines.append(f"  Gaps: {', '.join(map(str, gaps))}")

    if report["failed_monitors"]:
        lines.extend(["", "## Failures", ""])
        for item in report["results"]:
            if item["success"]:
                continue
            message = item["errors"][0].get("error", "Unknown error") if item["errors"] else "Unknown error"
            message = str(message).replace("\n", " ")
            if len(message) > 1000:
                message = message[:997] + "..."
            lines.append(f"- **{item['monitor']}**: {message}")

    lines.extend([
        "",
        "## Not automated",
        "",
        f"- **Tesla**: {report['not_automated']['tesla']}",
        "",
    ])
    return "\n".join(lines)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the daily programmatic job-monitor batch.")
    parser.add_argument("--monitors", nargs="+", choices=DEFAULT_MONITORS, default=DEFAULT_MONITORS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--scanned-at")
    parser.add_argument("--allow-partial-success", action="store_true")
    args = parser.parse_args()

    report = run_batch(args.monitors, scanned_at=args.scanned_at)
    _write(args.output, json.dumps(report, indent=2, ensure_ascii=True) + "\n")
    _write(args.markdown, render_markdown(report))
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if not report["success"] and not args.allow_partial_success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

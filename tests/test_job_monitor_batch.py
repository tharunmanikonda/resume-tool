import job_monitor_batch


def test_batch_keeps_successful_results_when_another_monitor_fails(monkeypatch):
    def fake_company(name, scanned_at=None):
        if name == "cisco":
            raise RuntimeError("temporary fetch failure")
        return {
            "success": True,
            "scanned_at": scanned_at,
            "fetched": 10,
            "unseen": 1,
            "state_updated": True,
            "candidates": [{
                "external_job_id": "R1",
                "title": "Software Engineer",
                "url": "https://example.test/job/R1",
                "filter": {"priority": "high", "reasons": ["Python"], "gaps": []},
            }],
            "needs_ai_review": [],
            "errors": [],
        }

    monkeypatch.setattr(job_monitor_batch, "run_company_scan", fake_company)
    report = job_monitor_batch.run_batch(
        ["cisco", "tiktok"], scanned_at="2026-11-01T09:00:00-06:00"
    )

    assert report["success"] is False
    assert report["failed_monitors"] == ["cisco"]
    assert report["successful_monitors"] == ["tiktok"]
    assert report["candidate_count"] == 1
    assert report["candidates"][0]["job_id"] == "R1"


def test_markdown_contains_candidate_and_failure():
    report = {
        "success": False,
        "scanned_at": "2026-11-01T09:00:00-06:00",
        "monitor_count": 2,
        "candidate_count": 1,
        "needs_ai_review_count": 0,
        "failed_monitors": ["cisco"],
        "candidates": [{
            "monitor": "tiktok",
            "job_id": "1",
            "title": "Backend Engineer",
            "url": "https://example.test/1",
            "priority": "high",
            "location": "San Jose, CA",
            "matching_requirements": ["Python", "distributed systems"],
            "material_gaps": ["privacy platform experience"],
        }],
        "results": [
            {
                "monitor": "tiktok", "success": True, "fetched": 5, "unseen": 1,
                "candidates": [{}], "needs_ai_review": [], "state_updated": True, "errors": [],
            },
            {
                "monitor": "cisco", "success": False, "fetched": 0, "unseen": 0,
                "candidates": [], "needs_ai_review": [], "state_updated": False,
                "errors": [{"error": "fetch failed"}],
            },
        ],
        "not_automated": {"tesla": "needs browser runner"},
    }

    rendered = job_monitor_batch.render_markdown(report)

    assert "[Backend Engineer](https://example.test/1)" in rendered
    assert "Match: Python, distributed systems" in rendered
    assert "Gaps: privacy platform experience" in rendered
    assert "**cisco**: fetch failed" in rendered
    assert "**Tesla**: needs browser runner" in rendered


def test_markdown_truncates_large_browser_errors():
    report = {
        "success": False,
        "scanned_at": "2026-11-01T09:00:00-06:00",
        "monitor_count": 1,
        "candidate_count": 0,
        "needs_ai_review_count": 0,
        "failed_monitors": ["ebay"],
        "candidates": [],
        "results": [{
            "monitor": "ebay", "success": False, "fetched": 0, "unseen": 0,
            "candidates": [], "needs_ai_review": [], "state_updated": False,
            "errors": [{"error": "x" * 5000}],
        }],
        "not_automated": {"tesla": "needs browser runner"},
    }

    rendered = job_monitor_batch.render_markdown(report)

    failure = rendered.split("**ebay**: ", 1)[1].splitlines()[0]
    assert len(failure) == 1000
    assert failure.endswith("...")

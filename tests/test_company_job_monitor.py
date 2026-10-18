import json

import company_job_monitor
from tracked_company_job_filter import FILTER_VERSION


def listing(job_id="one", title="Backend Software Engineer"):
    return {
        "external_job_id": job_id,
        "title": title,
        "location": "Dallas, Texas, US",
        "job_type": "Full time",
        "posted_at": "Posted Today",
        "url": f"https://example.com/{job_id}",
    }


def detail(job_id="one"):
    return {
        **listing(job_id),
        "description": "3+ years building Python backend APIs, distributed systems, Kafka, PostgreSQL, AWS, Docker, Kubernetes, CI/CD and observability.",
        "error": None,
    }


def test_known_jobs_do_not_fetch_details(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"filter_version": FILTER_VERSION, "known_job_ids": ["one"]}))
    monkeypatch.setattr(company_job_monitor, "fetch_listings", lambda company, known: [listing()])
    monkeypatch.setattr(company_job_monitor, "fetch_details", lambda company, jobs: (_ for _ in ()).throw(AssertionError()))

    result = company_job_monitor.run_company_scan("cisco", state)

    assert result["unseen"] == 0
    assert result["detail_pages_fetched"] == 0
    assert result["ai_calls"] == 0


def test_filter_change_rechecks_known_non_candidates(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"filter_version": FILTER_VERSION - 1, "known_job_ids": ["one"]}))
    def listings(company, known):
        assert known == {"one"}
        return [listing()]

    monkeypatch.setattr(company_job_monitor, "fetch_listings", listings)
    monkeypatch.setattr(company_job_monitor, "fetch_details", lambda company, jobs: [detail()])

    result = company_job_monitor.run_company_scan("iqvia", state)

    assert result["unseen"] == 0
    assert result["rechecked_after_filter_change"] == 1
    assert result["candidates"][0]["external_job_id"] == "one"
    assert json.loads(state.read_text())["filter_version"] == FILTER_VERSION


def test_rejection_evidence_is_returned_and_persisted(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    rejected = listing(title="Warehouse Associate")
    monkeypatch.setattr(company_job_monitor, "fetch_listings", lambda company, known: [rejected])
    monkeypatch.setattr(company_job_monitor, "fetch_details", lambda company, jobs: [])

    result = company_job_monitor.run_company_scan("cbre", state, scanned_at="2026-10-17T20:00:00-05:00")

    assert result["prefilter_rejections"][0]["title"] == "Warehouse Associate"
    assert result["prefilter_rejections"][0]["blockers"] == ["title_not_targeted"]
    saved = json.loads(state.read_text())
    assert saved["rejected_catalog"]["one"]["stage"] == "prefilter"
    assert saved["rejected_catalog"]["one"]["filter_version"] == FILTER_VERSION


def test_new_match_is_returned_and_state_is_updated(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    monkeypatch.setattr(company_job_monitor, "fetch_listings", lambda company, known: [listing()])
    monkeypatch.setattr(company_job_monitor, "fetch_details", lambda company, jobs: [detail()])

    result = company_job_monitor.run_company_scan("intepros", state, scanned_at="2026-10-10T09:00:00-05:00")

    assert result["candidates"][0]["external_job_id"] == "one"
    assert result["ai_calls"] == 0
    assert json.loads(state.read_text())["known_job_ids"] == ["one"]


def test_detail_error_preserves_state(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    original = {"known_job_ids": []}
    state.write_text(json.dumps(original))
    monkeypatch.setattr(company_job_monitor, "fetch_listings", lambda company, known: [listing()])
    monkeypatch.setattr(company_job_monitor, "fetch_details", lambda company, jobs: [{"external_job_id": "one", "error": "timeout"}])

    result = company_job_monitor.run_company_scan("cisco", state)

    assert result["success"] is False
    assert json.loads(state.read_text()) == original


def test_all_configured_companies_are_supported(tmp_path, monkeypatch):
    monkeypatch.setattr(company_job_monitor, "fetch_listings", lambda company, known: [listing(company)])
    monkeypatch.setattr(company_job_monitor, "fetch_details", lambda company, jobs: [detail(company)])

    for company in sorted(company_job_monitor.COMPANIES):
        result = company_job_monitor.run_company_scan(company, tmp_path / f"{company}.json")
        assert result["success"] is True
        assert result["candidates"][0]["external_job_id"] == company


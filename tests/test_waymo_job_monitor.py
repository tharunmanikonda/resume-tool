import json

import waymo_job_monitor
from waymo_job_filter import url_identity_hash


def listing(title, url, metadata=None):
    return {
        "title": title,
        "url": url,
        "metadata": metadata or ["California", "Software Engineering", "Full-Time", "Mid Career"],
    }


def test_known_urls_do_not_fetch_details(tmp_path, monkeypatch):
    url = "https://careers.withwaymo.com/jobs/backend-engineer"
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"known_url_hashes": [url_identity_hash(url)]}))
    monkeypatch.setattr(waymo_job_monitor, "fetch_waymo_listings", lambda: [listing("Backend Engineer", url)])
    monkeypatch.setattr(
        waymo_job_monitor,
        "fetch_waymo_details",
        lambda urls: (_ for _ in ()).throw(AssertionError("details should not be fetched")),
    )

    result = waymo_job_monitor.run_waymo_scan(state_path, scanned_at="2026-10-07T08:15:00-05:00")

    assert result["new_urls"] == 0
    assert result["detail_pages_fetched"] == 0
    assert result["state_updated"] is True


def test_new_noise_fetches_once_to_advance_id_high_watermark(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"known_url_hashes": []}))
    job = listing("Staff Software Engineer", "https://careers.withwaymo.com/jobs/staff-engineer")
    monkeypatch.setattr(waymo_job_monitor, "fetch_waymo_listings", lambda: [job])
    monkeypatch.setattr(
        waymo_job_monitor,
        "fetch_waymo_details",
        lambda urls: [{
            "url": urls[0],
            "error": None,
            "text": "California Full-Time Software Engineering 5600",
        }],
    )

    result = waymo_job_monitor.run_waymo_scan(state_path)

    assert result["new_urls"] == 1
    assert result["filtered_before_classification"] == 1
    assert result["detail_pages_fetched"] == 1
    assert result["highest_observed_job_id"] == 5600
    saved = json.loads(state_path.read_text())
    assert url_identity_hash(job["url"]) in saved["known_url_hashes"]
    assert saved["highest_seen_job_id"] == 5600


def test_new_matching_role_fetches_detail_and_returns_candidate(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"known_url_hashes": [], "known_job_ids": []}))
    job = listing("Backend Software Engineer", "https://careers.withwaymo.com/jobs/backend-engineer")
    monkeypatch.setattr(waymo_job_monitor, "fetch_waymo_listings", lambda: [job])
    monkeypatch.setattr(
        waymo_job_monitor,
        "fetch_waymo_details",
        lambda urls: [{
            "url": urls[0],
            "error": None,
            "text": (
                "Mountain View Full-Time Software Engineering 5601 "
                "3+ years building Python and Go backend APIs, distributed systems, Kafka, PostgreSQL, "
                "Docker, Kubernetes, AWS, CI/CD, and observability."
            ),
        }],
    )

    result = waymo_job_monitor.run_waymo_scan(state_path)

    assert result["detail_pages_fetched"] == 1
    assert result["candidates"][0]["job_id"] == "5601"
    assert json.loads(state_path.read_text())["highest_seen_job_id"] == 5601


def test_detail_error_preserves_previous_state(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    original = {"known_url_hashes": []}
    state_path.write_text(json.dumps(original))
    job = listing("Backend Software Engineer", "https://careers.withwaymo.com/jobs/backend-engineer")
    monkeypatch.setattr(waymo_job_monitor, "fetch_waymo_listings", lambda: [job])
    monkeypatch.setattr(
        waymo_job_monitor,
        "fetch_waymo_details",
        lambda urls: [{"url": urls[0], "text": "", "error": "timeout"}],
    )

    result = waymo_job_monitor.run_waymo_scan(state_path)

    assert result["success"] is False
    assert result["state_updated"] is False
    assert json.loads(state_path.read_text()) == original


def test_recent_matches_are_sorted_by_id_and_cached(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"known_url_hashes": [], "known_job_ids": []}))
    jobs = [
        listing("Backend Software Engineer", "https://careers.withwaymo.com/jobs/backend-a"),
        listing("Software Engineer, Platform", "https://careers.withwaymo.com/jobs/platform-b"),
    ]
    monkeypatch.setattr(waymo_job_monitor, "fetch_waymo_listings", lambda: jobs)
    calls = []

    def details(urls):
        calls.append(urls)
        ids = {jobs[0]["url"]: "5601", jobs[1]["url"]: "5603"}
        return [{
            "url": url,
            "error": None,
            "text": (
                f"California Full-Time Software Engineering {ids[url]} "
                "3+ years building Python and Go backend APIs, distributed systems, Kafka, PostgreSQL, "
                "Docker, Kubernetes, AWS, CI/CD, and observability."
            ),
        } for url in urls]

    monkeypatch.setattr(waymo_job_monitor, "fetch_waymo_details", details)
    first = waymo_job_monitor.run_recent_waymo_matches(10, state_path)
    second = waymo_job_monitor.run_recent_waymo_matches(10, state_path)

    assert [item["job_id"] for item in first["matches"]] == ["5603", "5601"]
    assert first["detail_pages_fetched"] == 2
    assert second["detail_pages_fetched"] == 0
    assert len(calls) == 1

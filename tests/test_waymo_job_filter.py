from waymo_job_filter import (
    canonical_waymo_url,
    classify_waymo_job,
    extract_waymo_job_id,
    prefilter_waymo_listing,
    select_new_listing_urls,
    update_waymo_state,
    url_identity_hash,
)


def test_canonical_url_ignores_query_fragment_and_trailing_slash():
    left = "https://careers.withwaymo.com/jobs/backend-engineer/?source=test#apply"
    right = "https://careers.withwaymo.com/jobs/backend-engineer"
    assert canonical_waymo_url(left) == right
    assert url_identity_hash(left) == url_identity_hash(right)


def test_known_listing_is_skipped_before_detail_fetch():
    url = "https://careers.withwaymo.com/jobs/backend-engineer"
    state = {"known_url_hashes": [url_identity_hash(url)]}
    jobs = [{"url": url}, {"url": "https://careers.withwaymo.com/jobs/full-stack-engineer"}]
    assert [job["url"] for job in select_new_listing_urls(jobs, state)] == [jobs[1]["url"]]


def test_waymo_listing_prefilter_rejects_intern_and_staff_roles():
    intern = {"title": "2027 Software Engineer Intern", "metadata": ["United States", "Intern"]}
    staff = {"title": "Staff Software Engineer", "metadata": ["California", "Full-Time"]}
    assert prefilter_waymo_listing(intern).decision == "filtered_out"
    assert prefilter_waymo_listing(staff).decision == "filtered_out"


def test_waymo_listing_prefilter_keeps_full_time_backend_role():
    role = {"title": "Backend Software Engineer", "metadata": ["California", "Full-Time", "Mid Career"]}
    assert prefilter_waymo_listing(role).decision == "needs_detail"


def test_waymo_classifier_rejects_explicit_five_plus_year_requirement():
    role = {
        "title": "Senior Software Engineer, Developer AI",
        "metadata": ["California", "Full-Time", "Mid Career"],
        "description": "5+ years software development experience with Python backend APIs.",
    }
    result = classify_waymo_job(role)
    assert result.decision == "filtered_out"
    assert "minimum_experience_at_least_5_years" in result.blockers


def test_waymo_classifier_keeps_three_to_five_year_range():
    role = {
        "title": "Senior Software Engineer, Evaluation",
        "metadata": ["California", "Full-Time", "Mid Career"],
        "description": (
            "3-5 years of experience with Python backend APIs, distributed systems, "
            "Kafka, PostgreSQL, Docker, Kubernetes, and AWS."
        ),
    }
    result = classify_waymo_job(role)
    assert result.decision == "candidate"
    assert "experience_stretch:5_years:-2" not in result.reasons


def test_waymo_classifier_does_not_block_five_plus_when_only_preferred():
    role = {
        "title": "Software Engineer, Evaluation",
        "metadata": ["California", "Full-Time", "Mid Career"],
        "description": (
            "You have: 3+ years building Python backend APIs and distributed systems. "
            "We prefer: 5+ years working with autonomous vehicles."
        ),
    }
    assert classify_waymo_job(role).decision != "filtered_out"


def test_waymo_classifier_rejects_written_five_year_minimum_and_greater_than_four():
    base = {
        "title": "Software Engineer, Platform",
        "metadata": ["California", "Full-Time", "Mid Career"],
    }
    written = {
        **base,
        "description": "You have: a minimum of five years of industry experience with backend APIs.",
    }
    greater_than = {
        **base,
        "description": "You have: > 4 years of total experience building server-side infrastructure.",
    }
    assert classify_waymo_job(written).decision == "filtered_out"
    assert classify_waymo_job(greater_than).decision == "filtered_out"


def test_extracts_waymo_requisition_number_from_detail_text():
    assert extract_waymo_job_id("Mountain View Full-Time Software Engineering 4911 Apply now") == "4911"
    assert extract_waymo_job_id("Mountain View Full-Time Software Engineering 4070-3 Apply now") == "4070-3"


def test_state_adds_urls_and_resolved_ids():
    updated = update_waymo_state(
        {"known_url_hashes": [], "known_job_ids": [], "highest_seen_job_id": None},
        [{"url": "https://careers.withwaymo.com/jobs/backend-engineer", "job_id": 5012}],
        "2026-10-07T08:15:00-05:00",
    )
    assert updated["highest_seen_job_id"] == 5012
    assert updated["known_job_ids"] == ["5012"]
    assert len(updated["known_url_hashes"]) == 1

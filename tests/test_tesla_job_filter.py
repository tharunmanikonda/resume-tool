from tesla_job_filter import (
    classify_tesla_job,
    prefilter_tesla_job,
    select_unseen_jobs,
    select_unseen_jobs_across_queries,
    update_monitor_state,
    update_monitor_state_for_queries,
)


def job(title, *, job_type="Full-Time", location="Palo Alto, California", requirements=""):
    return {
        "title": title,
        "type": job_type,
        "location": location,
        "requirements": requirements,
    }


def test_prefilter_rejects_trial_noise():
    cases = [
        job("Internship, Software Engineer, Data Platforms", job_type="Intern/Apprentice"),
        job("Technical Sourcer, Software Engineering"),
        job("Software Engineering Manager, Analytics Platform"),
        job("Staff Software Engineer, Infrastructure Engineering"),
        job("Embedded Software Engineer, Silicon Development"),
        job("Application Support Engineer, Factory Software"),
        job("BIM Software Engineer"),
    ]
    assert all(prefilter_tesla_job(item).decision == "filtered_out" for item in cases)


def test_prefilter_rejects_additional_non_us_locations():
    assert prefilter_tesla_job(job("Software Engineer", location="Warsaw, Poland")).decision == "filtered_out"
    assert prefilter_tesla_job(job("Software Engineer", location="Taipei City, Taiwan")).decision == "filtered_out"
    assert prefilter_tesla_job(job("Software Engineer", location="Bengaluru, Karnataka")).decision == "filtered_out"


def test_prefilter_keeps_target_application_roles():
    titles = [
        "Backend Engineer, Toolbox Diagnostics",
        "Full Stack Engineer, Integration Tools",
        "Software Engineer, Frontend, AI Tooling",
        "LFP Data Engineer, Manufacturing Software & Analytics",
        "Software QA Engineer, Update Systems Validation",
        "Database Technician",
        "Application Systems Analyst",
        "Systems Integration Engineer",
        "Release Engineer",
        "Debug Technician",
        "Systems Support Developer",
        "Business Systems Analyst",
        "System Verification Engineer",
        "Automation Engineer",
        "Senior Information Security Analyst",
        "Agent Evaluation Engineer",
    ]
    assert all(prefilter_tesla_job(job(title)).decision == "needs_detail" for title in titles)


def test_ambiguous_systems_role_is_rejected_after_hardware_details():
    result = classify_tesla_job(job(
        "System Verification Engineer",
        requirements="2+ years performing RTL simulation and PCB design with oscilloscopes and multimeters.",
    ))

    assert result.decision == "filtered_out"
    assert "non_software_engineering_role" in result.blockers


def test_hardware_debug_technician_is_rejected():
    result = classify_tesla_job(job(
        "Debug Technician",
        requirements="Use oscilloscopes, multimeters, soldering, PCB rework, and electrical schematics.",
    ))

    assert result.decision == "filtered_out"
    assert "hardware_debug_role" in result.blockers


def test_software_debug_technician_needs_manual_review():
    result = classify_tesla_job(job(
        "Debug Technician",
        requirements="Debug Linux services using Python, SQL, APIs, AWS, Docker, and observability tools.",
    ))

    assert result.decision == "needs_review"


def test_backend_trial_role_is_high_priority():
    result = classify_tesla_job(job(
        "Backend Engineer, Toolbox Diagnostics",
        requirements=(
            "3+ years backend software development using Python or Go. Design APIs and distributed systems "
            "with PostgreSQL, Redis, Kafka, Docker, Kubernetes, AWS, GitHub Actions, and ArgoCD."
        ),
    ))
    assert result.decision == "candidate"
    assert result.priority == "high"


def test_sre_telemetry_role_is_a_candidate():
    result = classify_tesla_job(job(
        "Site Reliability Engineer, Optimus",
        requirements=(
            "2+ years in data engineering, telemetry, reliability engineering, or fleet analytics. "
            "Build reproducible pipelines with Python, Pandas, NumPy, SQL, PostgreSQL, and ClickHouse. "
            "Participate in on-call incident response."
        ),
    ))

    assert result.decision == "candidate"
    assert result.priority in {"medium", "high"}


def test_agentic_tooling_role_is_high_priority():
    result = classify_tesla_job(job(
        "Software Engineer, Agentic Tooling, Tesla AI",
        requirements=(
            "Python, Go, distributed systems, orchestration, agents, skills, MCP, evaluation pipelines, "
            "observability, relational and vector databases, Docker, and Kubernetes."
        ),
    ))
    assert result.decision == "candidate"
    assert result.priority == "high"


def test_specialized_tax_role_is_filtered_before_detail_review():
    result = classify_tesla_job(job(
        "Software Engineer, Tax",
        requirements="3+ years configuring a tax engine with indirect tax, Vertex, and Avalara.",
    ))
    assert result.decision == "filtered_out"
    assert "specialized_non_target" in result.blockers


def test_five_year_architecture_role_is_only_a_stretch():
    result = classify_tesla_job(job(
        "Software Engineer, Architecture Review Board",
        requirements=(
            "5+ years in software architecture, distributed systems, cloud platforms, microservices, "
            "CI/CD, security, and generative AI."
        ),
    ))
    assert result.priority != "high"
    assert "experience_stretch:5_years:-2" in result.reasons


def test_six_year_requirement_is_filtered_out():
    result = classify_tesla_job(job(
        "Senior Backend Software Engineer",
        requirements="6+ years building Python APIs, distributed systems, Kafka, PostgreSQL, Docker, and Kubernetes.",
    ))
    assert result.decision == "filtered_out"
    assert "minimum_experience:6_years" in result.blockers


def test_only_unseen_ids_above_high_watermark_are_selected():
    state = {"highest_seen_job_id": 285797, "known_job_ids": ["279041", "285797"]}
    result = select_unseen_jobs([
        {"id": "279041", "title": "Known backend role"},
        {"id": "285900", "title": "New higher ID"},
        {"id": "270500", "title": "Unseen lower ID"},
    ], state)

    assert [item["id"] for item in result["jobs"]] == ["285900"]
    assert result["jobs"][0]["freshness_signal"] == "above_high_watermark"
    assert result["highest_observed_job_id"] == 285900


def test_state_keeps_max_id_and_all_seen_ids():
    state = {"highest_seen_job_id": 285797, "known_job_ids": ["279041"]}
    updated = update_monitor_state(
        state,
        [{"id": "285900"}, {"id": "270500"}],
        "2026-10-07T08:00:00-05:00",
    )

    assert updated["highest_seen_job_id"] == 285900
    assert updated["known_job_ids"] == ["270500", "279041", "285900"]
    assert updated["last_successful_scan_at"] == "2026-10-07T08:00:00-05:00"


def test_multi_query_scan_does_not_hide_lower_unseen_id():
    state = {
        "highest_seen_job_id": 286874,
        "known_job_ids": ["286874"],
        "query_states": {
            "software_engineer": {"highest_seen_job_id": 286874, "known_job_ids": ["286874"]},
        },
    }
    result = select_unseen_jobs_across_queries({
        "software_engineer": [{"id": "286874", "title": "Known software role"}],
        "site_reliability": [{"id": "286844", "title": "Site Reliability Engineer, Optimus"}],
    }, state)

    assert [item["id"] for item in result["jobs"]] == ["286844"]
    assert result["jobs"][0]["freshness_signal"] == "above_query_high_watermark"
    assert result["jobs"][0]["discovered_by_queries"] == ["site_reliability"]


def test_multi_query_state_tracks_each_search_independently():
    state = {
        "version": 1,
        "highest_seen_job_id": 286874,
        "known_job_ids": ["286874"],
        "query_states": {
            "software_engineer": {"highest_seen_job_id": 286874, "known_job_ids": ["286874"]},
        },
    }
    updated = update_monitor_state_for_queries(
        state,
        {
            "software_engineer": [{"id": "286874"}],
            "site_reliability": [{"id": "286844"}],
        },
        "2026-10-15T10:00:00-05:00",
    )

    assert updated["version"] == 2
    assert updated["highest_seen_job_id"] == 286874
    assert updated["query_states"]["site_reliability"]["highest_seen_job_id"] == 286844
    assert updated["query_states"]["site_reliability"]["known_job_ids"] == ["286844"]
    assert updated["known_job_ids"] == ["286844", "286874"]

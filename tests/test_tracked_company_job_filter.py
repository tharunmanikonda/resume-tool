from tracked_company_job_filter import classify_company_job, prefilter_company_job


def job(**overrides):
    value = {
        "title": "Backend Software Engineer",
        "location": "Dallas, Texas, US",
        "job_type": "Full time",
        "description": "3+ years building Python backend APIs, distributed systems, Kafka, PostgreSQL, AWS, Docker, Kubernetes, CI/CD and observability.",
    }
    value.update(overrides)
    return value


def test_broader_software_titles_are_supported():
    for title in (
        "Software Development Engineer in Test (SDET)",
        "Senior Kubernetes Platform Engineer",
        "AI/Data Science Engineer II",
        "iOS Engineer",
        "Android Engineer",
        "Database Technician",
        "Database Analyst",
        "Application Systems Analyst",
        "Systems Integration Engineer",
        "Release Engineer",
        "Software Test Engineer",
        "Debug Technician",
    ):
        assert prefilter_company_job(job(title=title)).decision == "needs_detail"


def test_hardware_debug_technician_is_rejected_after_detail_fetch():
    result = classify_company_job(job(
        title="Debug Technician",
        description="Use oscilloscopes, multimeters, soldering, PCB board rework, and electrical schematics.",
    ))

    assert result.decision == "filtered_out"
    assert "hardware_debug_role" in result.blockers


def test_software_debug_technician_requires_review():
    result = classify_company_job(job(
        title="Debug Technician",
        description="Debug Linux services using Python, SQL, logs, APIs, AWS, Docker, and observability tools.",
    ))

    assert result.decision == "needs_review"


def test_title_noise_is_rejected_before_details():
    result = prefilter_company_job(job(title="Principal Embedded Software Engineer"))
    assert result.decision == "filtered_out"
    assert "level_too_senior" in result.blockers
    assert "embedded_or_hardware" in result.blockers


def test_talent_community_and_abap_specialist_roles_are_rejected():
    talent = prefilter_company_job(job(title="Talent Community Senior Application Engineer"))
    abap = prefilter_company_job(job(title="Senior Software Engineer (SAP ABAP)"))

    assert talent.decision == "filtered_out"
    assert "not_an_open_role" in talent.blockers
    assert abap.decision == "filtered_out"
    assert "specialized_low_level" in abap.blockers


def test_required_five_years_is_rejected_but_three_to_five_is_kept():
    rejected = classify_company_job(job(description="Minimum Qualifications: 5+ years of Python backend engineering."))
    accepted = classify_company_job(job(description="Minimum Qualifications: 3-5 years building Python backend APIs, AWS, Docker and Kubernetes."))
    assert "minimum_experience_at_least_5_years" in rejected.blockers
    assert accepted.decision in {"candidate", "needs_review"}


def test_required_experience_variants_are_rejected():
    descriptions = [
        "Minimum Qualifications: 8+ yrs building distributed systems.",
        "Minimum Qualifications: 12 + years building cloud platforms.",
        "Minimum Qualifications: 5 or more years of backend engineering.",
    ]

    for description in descriptions:
        result = classify_company_job(job(description=description))
        assert "minimum_experience_at_least_5_years" in result.blockers


def test_three_to_five_year_range_with_abbreviation_remains_eligible():
    result = classify_company_job(job(
        description="Minimum Qualifications: 3-5 yrs building Python APIs, AWS, Docker and Kubernetes."
    ))

    assert "minimum_experience_at_least_5_years" not in result.blockers


def test_matching_profile_is_high_or_medium_candidate():
    result = classify_company_job(job())
    assert result.decision == "candidate"
    assert result.priority in {"high", "medium"}


def test_nvidia_required_section_stops_before_preferred_experience():
    result = classify_company_job(job(description=(
        "What we need to see: 3+ years building Python backend APIs, distributed systems, AWS and Kubernetes. "
        "Ways to stand out: 7+ years of related experience."
    )))
    assert "minimum_experience_at_least_5_years" not in result.blockers


def test_nvidia_low_level_specialist_titles_are_rejected_before_details():
    for title in (
        "System Software Engineer, Performance - CUDA Driver",
        "Senior Software Engineer, System Validation - EDA Infrastructure",
        "C++ Software Engineer, Infrastructure Tools",
        "Senior DFX Software Engineer - Machine Learning",
    ):
        result = prefilter_company_job(job(title=title))
        assert result.decision == "filtered_out"
        assert "specialized_low_level" in result.blockers


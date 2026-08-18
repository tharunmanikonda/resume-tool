from job_preflight import evaluate_job_preflight


def test_blocks_active_secret_clearance():
    result = evaluate_job_preflight(
        "Candidates must have an active Secret security clearance.",
        {},
    )
    assert result["blocked"] is True
    assert result["matches"]


def test_blocks_us_citizenship_requirement():
    result = evaluate_job_preflight(
        "U.S. citizenship is required due to federal contract requirements.",
        {},
    )
    assert result["blocked"] is True
    assert result["matches"][0]["code"] == "us_citizenship"


def test_does_not_block_generic_security_language():
    result = evaluate_job_preflight(
        "Build secure APIs and follow application security best practices.",
        {},
    )
    assert result["blocked"] is False
    assert result["matches"] == []


def test_setting_allows_detected_clearance_job():
    result = evaluate_job_preflight(
        "Ability to obtain and maintain a Public Trust clearance is required.",
        {"allow_security_clearance_jobs": True},
    )
    assert result["blocked"] is False
    assert result["matches"]

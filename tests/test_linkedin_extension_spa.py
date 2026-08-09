from pathlib import Path


def test_linkedin_reader_waits_for_stable_spa_context():
    source = Path("extension/public/content-script.js").read_text(encoding="utf-8")

    assert "STABLE_CONTEXT_OBSERVATIONS = 2" in source
    assert "descriptionNodeStillBelongsToPreviousJob" in source
    assert 'sendRuntimeMessage({ type: "JOB_CONTEXT_CLEARED" })' in source
    assert "currentDescriptionSignature === lastPublishedDescriptionSignature" in source


def test_linkedin_reader_prefers_url_bound_visible_job_data_over_stale_json_ld():
    source = Path("extension/public/content-script.js").read_text(encoding="utf-8")

    role_candidates = source[source.index("const roleCandidates = ["):source.index("const selectedRole =")]
    assert role_candidates.index("selected_job_card") < role_candidates.index("structured_data")

    read_context = source[source.index("function readContext()"):]
    company_assignment = next(line for line in read_context.splitlines() if "const companyName =" in line)
    assert company_assignment.index("detail.companyName") < company_assignment.index("structured?.hiringOrganization")

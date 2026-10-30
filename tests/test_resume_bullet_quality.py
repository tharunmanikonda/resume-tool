import pytest

import app as resume_app
from resume_bullet_quality import (
    bullet_quality_findings, experience_entry_schema, project_characteristics,
    requirement_link_issues,
)


BLUEPRINT = {
    "key": "mckinsey", "company": "Example", "location": "US",
    "dates": "2024 - Present", "default_title": "Software Engineer",
    "anchor": "",
    "bullet_min": 1, "bullet_max": 1,
}
ANALYSIS = {
    "target_role": "Frontend Engineer", "core_problem": "Build trading admin interfaces",
    "top_requirements": ["React tables, filters and pagination"],
    "workflows": ["Operators review and resolve transactions"],
    "skills_mentioned": ["React", "TypeScript"],
    "prompt_family_key": "software_engineering",
}
GOOD_BULLET = "Built React transaction tables with pagination and status filters, reducing operator review time by 25% across recurring exception-handling workflows."


def payload(bullet):
    return {"experience": {"mckinsey": {"title": "Software Engineer", "bullets": [bullet]}}}


@pytest.mark.parametrize("bullet,code", [
    ("Authored system design and scalability plans for retrieval tiers, increasing throughput capacity by 3x.", "action_result_gap"),
    ("Built retrieval systems using Python, improving demo readiness by 60%.", "undefined_metric"),
    ("Integrated systems using Zapier-style automation, reducing handoff time by 30%.", "platform_analogy"),
    ("Optimized UniQuery-like queries using Oracle and SQL.", "platform_analogy"),
    ("Led AI delivery, building ingestion systems and coordinated cross-functional teams.", "parallel_grammar"),
    ("Built real-time routing and webhook workflows using REST APIs and JSON, increasing routing accuracy by 18%.", "unnamed_workflow_object"),
])
def test_observed_rejected_resume_defects_are_detected(bullet, code):
    findings = bullet_quality_findings(payload(bullet), [BLUEPRINT])
    assert code in {item["code"] for item in findings}
    assert all(item["role_key"] == "mckinsey" and item["bullet_number"] == 1 for item in findings)


@pytest.mark.parametrize("bullet", [
    GOOD_BULLET,
    "Authored and implemented a caching plan, increasing throughput by 3x in production load tests.",
    "Authored scalability plans with projected throughput increasing by 3x.",
    "Improved demo readiness by 60%, measured as preparation time for recurring customer demonstrations.",
    "Integrated HubSpot with Zapier, reducing lead handoff time by 30%.",
    "Reduced errors by 25% while improving demo readiness.",
    "Built routing and webhook workflows for inbound sales leads, improving assignment accuracy by 18%.",
])
def test_meaningful_metrics_and_direct_tools_are_not_blanket_rejected(bullet):
    assert bullet_quality_findings(payload(bullet), [BLUEPRINT]) == []


def test_project_focus_follows_jd_and_never_injects_fixed_ai_context():
    frontend = project_characteristics(ANALYSIS, "Build React admin tooling")
    gtm = project_characteristics({
        "target_role": "GTM Engineer", "core_problem": "Automate CRM lead handoffs",
        "top_requirements": ["HubSpot lifecycle management"],
        "workflows": ["Qualify and route inbound sales leads"],
    })
    assert frontend["problem_to_solve"] != gtm["problem_to_solve"]
    assert "React" in frontend["priority_requirements"][0]
    assert "HubSpot" in gtm["priority_requirements"][0]
    assert "not_candidate_evidence" in frontend["authority"]
    assert "AI" not in str(frontend) + str(gtm)
    assert all(not bp["anchor"] for bp in resume_app.EXPERIENCE_BLUEPRINTS)


def test_schema_requires_narrative_and_bullet_level_requirement_links():
    schema = experience_entry_schema(BLUEPRINT)
    assert set(schema["required"]) == {"title", "contribution_plan", "project_narrative", "bullets", "bullet_evidence", "requirement_evidence"}
    assert "evidence_limits" in schema["properties"]["project_narrative"]["required"]
    for build in (resume_app.ai_resume_schema, resume_app.ai_experience_schema, resume_app.ai_experience_subset_schema):
        entry = build([BLUEPRINT])["properties"]["experience"]["properties"]["mckinsey"]
        assert entry == schema


def test_requirement_links_cannot_point_at_missing_bullets_or_hide_gaps():
    data = payload(GOOD_BULLET)
    role = data["experience"]["mckinsey"]
    role["requirement_evidence"] = [{"requirement_number": 1, "fit": "direct", "bullet_numbers": [2]}]
    assert any("nonexistent bullet" in issue for issue in requirement_link_issues(data, [BLUEPRINT], ANALYSIS))
    role["requirement_evidence"][0]["bullet_numbers"] = [1]
    assert requirement_link_issues(data, [BLUEPRINT], ANALYSIS) == []
    role["requirement_evidence"][0].update(fit="gap", bullet_numbers=[])
    assert requirement_link_issues(data, [BLUEPRINT], ANALYSIS) == []
    role["requirement_evidence"] = []
    assert any("every priority requirement" in issue for issue in requirement_link_issues(data, [BLUEPRINT], ANALYSIS))


def test_role_sources_survive_profile_and_snapshot_round_trip():
    history = [{**BLUEPRINT, "title": "Software Engineer", "enabled": True,
                "source_bullets": [GOOD_BULLET], "metric_evidence": "Review time decreased by 25%."}]
    profile = resume_app.normalize_profile({"experience_history": history})
    assert profile["experience_history"][0]["source_bullets"] == [GOOD_BULLET]
    live = resume_app.current_experience_blueprints(profile)
    snap = resume_app.experience_blueprints_from_snapshot({
        "profile_snapshot": profile, "experience_history_snapshot": profile["experience_history"],
    })
    assert live[0]["source_bullets"] == snap[0]["source_bullets"] == [GOOD_BULLET]
    live[0]["source_bullets"].append("mutated")
    assert profile["experience_history"][0]["source_bullets"] == [GOOD_BULLET]


def test_generated_claims_are_not_labeled_as_independent_evidence():
    profile = {"experience_history": [{"key": "mckinsey", "source_bullets": [GOOD_BULLET]}]}
    manifest = resume_app._quality_audit_evidence_manifest(payload(GOOD_BULLET), [BLUEPRINT], profile)
    assert manifest["upstream.mckinsey.bullet.1"]["source"] == "draft_claim"
    assert manifest["profile.mckinsey.source_bullets"]["source"] == "profile"
    assert all(item["source"] != "upstream_validated" for item in manifest.values())


@pytest.mark.parametrize("entrypoint", ["subset", "legacy", "full"])
def test_generation_repairs_sentence_defects_and_revalidates(monkeypatch, entrypoint):
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        return payload("Built Python ingestion pipelines, improving demo readiness by 60%." if len(calls) == 1 else GOOD_BULLET)

    monkeypatch.setattr(resume_app, "call_openai_structured_output", fake_call)
    monkeypatch.setattr(resume_app, "current_experience_blueprints", lambda **kwargs: [BLUEPRINT])
    common = dict(api_key="test", analysis_payload=ANALYSIS, job_description="Build React admin tools")
    if entrypoint == "subset":
        result = resume_app.generate_experience_subset_from_analysis(
            **common, blueprints=[BLUEPRINT], model="test", timeout_seconds=1,
            preliminary_skills_payload={"updated_skills": []},
        )
    elif entrypoint == "legacy":
        result = resume_app.generate_resume_experience_from_analysis(**common, core_payload={})
    else:
        result = resume_app.generate_resume_from_analysis(**common)
    assert len(calls) == 2
    assert "undefined_metric" in calls[1]["user_prompt"]
    assert "Build React admin tools" in calls[0]["user_prompt"]
    assert "Target project characteristics" in calls[0]["user_prompt"]
    assert result["experience"]["mckinsey"]["bullets"] == [GOOD_BULLET]


def test_unrepaired_sentence_defects_block_generation(monkeypatch):
    monkeypatch.setattr(resume_app, "call_openai_structured_output", lambda **kwargs: payload(
        "Authored scalability plans, increasing throughput by 3x."
    ))
    with pytest.raises(ValueError, match="action_result_gap"):
        resume_app.generate_experience_subset_from_analysis(
            api_key="test", analysis_payload=ANALYSIS, blueprints=[BLUEPRINT], model="test", timeout_seconds=1,
        )


def test_new_checks_apply_to_software_engineering_not_only_gtm():
    issues = resume_app.validate_experience_subset_payload_with_analysis(
        payload("Built systems using Zapier-style automation, improving demo readiness by 60%."),
        [BLUEPRINT], ANALYSIS,
    )
    assert any("platform_analogy" in issue for issue in issues)
    assert any("undefined_metric" in issue for issue in issues)


def test_audit_cannot_approve_known_sentence_defects():
    from test_resume_quality_audit import audit_result, current_resume, active_blueprints, ANALYSIS as AUDIT_ANALYSIS
    current = current_resume()
    current["experience"]["mckinsey"]["bullets"][0] = "Built APIs, improving demo readiness by 60%."
    with pytest.raises(resume_app.ResumeQualityAuditValidationError, match="undefined_metric"):
        resume_app.validate_resume_quality_audit_result(
            audit_result(), current_resume=current, analysis_payload=AUDIT_ANALYSIS,
            active_blueprints=active_blueprints(),
        )


def test_withheld_patch_cannot_make_a_defective_original_approved(monkeypatch):
    from test_resume_quality_audit import audit_result, current_resume, active_blueprints, title_change, ANALYSIS as AUDIT_ANALYSIS
    current = current_resume()
    current["experience"]["mckinsey"]["bullets"][0] = "Built APIs, improving demo readiness by 60%."
    monkeypatch.setattr(resume_app, "_quality_audit_resume_validation_issues", lambda *args: [])
    changes = title_change()
    changes["top_title"]["suggested"] = "Quantum Imaginary Platform Engineer"
    with pytest.raises(resume_app.ResumeQualityAuditValidationError, match="undefined_metric"):
        resume_app.validate_resume_quality_audit_result(
            audit_result("changes_suggested", changes), current_resume=current,
            analysis_payload=AUDIT_ANALYSIS, active_blueprints=active_blueprints(),
        )


def test_project_planning_metadata_is_not_rendered_as_resume_text(monkeypatch):
    role = {"title": "Software Engineer", "bullets": [GOOD_BULLET],
            "project_narrative": {"system": "INTERNAL_PLAN_ONLY"},
            "requirement_evidence": [{"reason": "INTERNAL_LINK_ONLY"}]}
    data = {"experience": {"mckinsey": role}, "updated_title": "Frontend Engineer",
            "updated_summary": "Build useful interfaces", "updated_skills": []}
    content = resume_app.format_generated_resume_text(data, [BLUEPRINT])
    assert GOOD_BULLET in content
    assert "INTERNAL_PLAN_ONLY" not in content
    assert "INTERNAL_LINK_ONLY" not in content


def sourced_payload(bullet, refs=None, questions=None):
    result = payload(bullet)
    result['experience']['mckinsey']['bullet_evidence'] = [{
        'bullet_number': 1, 'source_refs': refs or [], 'confirmation_questions': questions or [],
    }]
    return result


def test_actual_requirement_count_constrains_remote_schema():
    analysis = {'top_requirements': ['React', 'Tables', 'Ownership']}
    schema = resume_app.ai_experience_subset_schema([BLUEPRINT], analysis)
    links = schema['properties']['experience']['properties']['mckinsey']['properties']['requirement_evidence']
    assert links['minItems'] == links['maxItems'] == 3
    assert links['items']['properties']['requirement_number']['maximum'] == 3
    assert project_characteristics(analysis)['valid_requirement_numbers'] == [1, 2, 3]


def test_missing_sources_require_visible_confirmation_instead_of_credible_sounding_claims():
    from resume_bullet_quality import claim_evidence_issues
    invented = sourced_payload(GOOD_BULLET)
    issues = claim_evidence_issues(invented, [BLUEPRINT], resume_app._numeric_tokens)
    assert any('missing inline' in i for i in issues)
    assert any('unsupported metrics' in i for i in issues)
    marked = sourced_payload(
        '[Confirm: proposed work] Could build React transaction tables with pagination to streamline operator reviews. [Confirm metric: review time reduction]',
        questions=['Did you build this workflow, and what change in review time did you measure?'],
    )
    assert claim_evidence_issues(marked, [BLUEPRINT], resume_app._numeric_tokens) == []


def test_metric_cannot_borrow_number_from_a_different_source_accomplishment():
    from resume_bullet_quality import claim_evidence_issues
    bp = {**BLUEPRINT, 'source_bullets': [
        'Virtualized 10,000-record React lists, reducing measured render duration by 45%.',
        'Automated transaction reconciliation, reducing manual processing time by 45%.',
    ]}
    draft = sourced_payload('Automated reconciliation of 10,000 records nightly, reducing processing time by 45%.', ['source_bullets.2'])
    assert any('10000' in issue for issue in claim_evidence_issues(draft, [bp], resume_app._numeric_tokens))
    supported = sourced_payload(bp['source_bullets'][0], ['source_bullets.1'])
    assert claim_evidence_issues(supported, [bp], resume_app._numeric_tokens) == []


def test_hyphenated_source_quantity_can_support_a_repair():
    assert '10000' in resume_app._numeric_tokens('Virtualized 10,000-record React lists.')
    assert resume_app._numeric_tokens('Rendered 10,000 records.') == resume_app._numeric_tokens('Rendered 10,000-record lists.')


def test_confirmation_draft_cannot_be_approved_even_when_model_says_approved():
    from test_resume_quality_audit import audit_result, current_resume, active_blueprints, ANALYSIS as AUDIT_ANALYSIS
    current = current_resume()
    current['experience']['mckinsey']['bullets'][0] = '[Confirm: proposed work] Could build transaction integrations. [Confirm metric: processing time reduction]'
    checked = resume_app.validate_resume_quality_audit_result(
        audit_result(), current_resume=current, analysis_payload=AUDIT_ANALYSIS,
        active_blueprints=active_blueprints(),
    )
    assert checked['decision'] == 'manual_attention'
    assert checked['manual_findings'][0]['id'] == 'confirmation.required'
    assert not checked['review_groups']


def test_final_pdf_rejects_pending_confirmation_even_with_stale_approved_status():
    with pytest.raises(ValueError, match='Confirm the marked'):
        resume_app.generate_extension_pdf({'audit_status': 'approved', 'status': 'ready', 'resume_content': '[Confirm metric: latency reduction]'})


def test_known_live_grammar_defect_and_duplicate_accomplishments_are_repair_targets():
    broken = 'Virtualized lists through windowing and batching strategies memoization.'
    assert any(f['code'] == 'broken_grammar' for f in bullet_quality_findings(payload(broken), [BLUEPRINT]))
    draft = payload(GOOD_BULLET)
    draft['experience']['mckinsey']['bullets'].append(GOOD_BULLET)
    assert any(f['code'] == 'duplicate_accomplishment' for f in bullet_quality_findings(draft, [BLUEPRINT]))


def test_small_supported_skill_set_needs_no_filler_categories():
    draft = {'updated_skills': [{'category': 'Programming Languages', 'items': ['Python', 'TypeScript']}]}
    assert not any('6 categories' in i for i in resume_app.validate_skills_only_payload(draft, ANALYSIS))
    cleaned = resume_app.normalize_skills_for_order({'updated_skills': [
        {'category': 'AI & LLM Systems', 'items': ['None', 'Not applicable']},
        *draft['updated_skills'],
    ]}, ['Programming Languages', 'AI & LLM Systems'])
    assert cleaned == draft


def test_confirmation_labels_are_rendered_even_when_model_only_returns_metadata():
    from resume_bullet_quality import prepare_experience_draft, claim_evidence_issues
    original = sourced_payload('Built Python integration handlers for transaction reconciliation.', questions=['Did you implement these handlers?'])
    original['experience']['mckinsey']['requirement_evidence'] = [{'requirement_number': 1, 'fit': 'direct', 'bullet_numbers': [1], 'reason': 'Draft matches target'}]
    prepared = prepare_experience_draft(original, [BLUEPRINT], resume_app._numeric_tokens)
    role = prepared['experience']['mckinsey']
    assert role['bullets'][0].startswith('[Confirm: proposed work]')
    assert '[Confirm metric:' in role['bullets'][0]
    assert role['requirement_evidence'][0]['fit'] == 'gap'
    assert not resume_app._numeric_tokens(role['bullets'][0])
    assert claim_evidence_issues(prepared, [BLUEPRINT], resume_app._numeric_tokens) == []
    assert '[Confirm:' not in original['experience']['mckinsey']['bullets'][0]
    # The draft reserves the 80% target but cannot pass final review as evidence.
    assert resume_app.validate_experience_numeric_coverage(prepared, [BLUEPRINT], ANALYSIS) == []
    assert resume_app._quality_audit_preflight(prepared, [BLUEPRINT])['pending_confirmations']


def test_supported_sources_and_metrics_need_no_confirmation_labels():
    from resume_bullet_quality import prepare_experience_draft, claim_evidence_issues
    bp = {**BLUEPRINT, 'source_bullets': [GOOD_BULLET]}
    original = sourced_payload(GOOD_BULLET, ['mckinsey.source_bullets.1'])
    prepared = prepare_experience_draft(original, [bp], resume_app._numeric_tokens)
    assert prepared == original
    assert claim_evidence_issues(prepared, [bp], resume_app._numeric_tokens) == []


def test_audit_resolves_only_unambiguous_actual_source_references():
    bp = {**BLUEPRINT, 'source_bullets': [GOOD_BULLET]}
    manifest = resume_app._quality_audit_evidence_manifest(payload(GOOD_BULLET), [bp])
    result = resume_app._resolve_quality_audit_source_refs({'role_key': 'mckinsey', 'evidence_refs': ['source_bullets.1', 'invented.1']}, manifest)
    assert result['evidence_refs'] == ['profile.mckinsey.source_bullets.1', 'invented.1']
    manifest['profile.uber.source_bullets.1'] = manifest['profile.mckinsey.source_bullets.1']
    assert resume_app._resolve_quality_audit_source_refs({'evidence_refs': ['source_bullets.1']}, manifest)['evidence_refs'] == ['source_bullets.1']


def test_ordinary_outreach_wording_is_distinct_from_platform_claim():
    analysis = {'skills_mentioned': ['Python']}
    assert resume_app.gtm_tool_mentions_not_in_jd('Streamlined outreach sequencing for outbound reps.', analysis) == []
    assert resume_app.gtm_tool_mentions_not_in_jd('Integrated Outreach platform APIs with Python.', analysis) == ['outreach']


def test_synthesis_schema_preserves_historical_titles():
    schema = resume_app.ai_final_synthesis_schema(['Programming Languages'], [BLUEPRINT])
    assert schema['properties']['experience_titles']['properties']['mckinsey']['enum'] == ['Software Engineer']


def test_main_pdf_endpoint_rejects_confirmation_markers_before_writing_files(monkeypatch):
    monkeypatch.setattr(resume_app, 'start_pdf_conversion', lambda *_args, **_kwargs: pytest.fail('Unconfirmed draft must not export'))
    response = resume_app.app.test_client().post('/api/generate', json={
        'content': '[Confirm: proposed work] Could build integrations. [Confirm metric: processing time]',
    })
    assert response.status_code == 409
    assert 'Confirm the marked' in response.get_json()['error']

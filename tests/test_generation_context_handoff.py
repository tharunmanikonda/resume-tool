import copy
import json

import pytest
import app as resume_app
from resume_generation_context import candidate_generation_context, profile_with_resume_context
from resume_bullet_quality import resume_body_issues

SOURCE = 'Built Python REST integrations for reconciliation, reducing manual processing time by 45% for 60 operations users.'
SUMMARY = ('Software engineer building practical API integrations, operational tools and reliable data workflows. '
           'Experience includes Python services, PostgreSQL reconciliation, testing and production support. '
           'Works with product and operations teams to deliver maintainable systems and measurable improvements. '
           'Brings hands-on implementation experience, clear technical communication and a focus on dependable software delivery across internal workflows and customer-facing systems.')
BASE = {
    'name': 'Candidate', 'summary': SUMMARY,
    'technical_skills': [{'category': 'Programming Languages', 'items': ['Python', 'SQL']}],
    'education': [{'degree': 'Computer Science'}],
    'experience': [{'company': 'Example', 'title': 'Software Engineer', 'dates': '2022 - Present', 'location': 'US', 'bullets': [SOURCE]}],
}
PROFILE = {'name': 'Candidate', 'experience_history': [{
    'key': 'mckinsey', 'company': 'Example', 'title': 'Software Engineer',
    'dates': '2022 – Present', 'location': 'US', 'enabled': True,
}]}
ANALYSIS = {'target_role': 'Customer Integration Engineer', 'role_family': 'solutions engineering',
            'prompt_family_key': 'solutions_customer', 'top_requirements': ['Vehicle data acquisition', 'Customer integration'],
            'skills_mentioned': ['CAN', 'DAQ', 'Python'], 'core_problem': 'Integrate customer systems'}


def test_matching_base_resume_reaches_app_and_extension_with_same_role_sources(monkeypatch):
    monkeypatch.setattr(resume_app, 'load_base_resume', lambda: copy.deepcopy(BASE))
    app_roles = resume_app.current_experience_blueprints(PROFILE)
    extension_roles = resume_app.experience_blueprints_from_snapshot({
        'profile_snapshot': PROFILE, 'experience_history_snapshot': PROFILE['experience_history'],
    })
    assert app_roles[0]['source_bullets'] == extension_roles[0]['source_bullets'] == [SOURCE]
    assert 'source_bullets' not in PROFILE['experience_history'][0]
    context = profile_with_resume_context(PROFILE, BASE)
    assert context['technical_skills'] == BASE['technical_skills']
    assert context['summary'] == SUMMARY
    assert context['education'] == BASE['education']


@pytest.mark.parametrize('change', [{'company': 'Different'}, {'title': 'Hardware Engineer'}, {'dates': '2019 - 2020'}])
def test_source_fallback_cannot_move_work_to_another_employer_or_role(change):
    profile = copy.deepcopy(PROFILE)
    profile['experience_history'][0].update(change)
    assert 'source_bullets' not in profile_with_resume_context(profile, BASE)['experience_history'][0]
    profile = copy.deepcopy(PROFILE)
    profile['name'] = 'Another Candidate'
    assert 'source_bullets' not in profile_with_resume_context(profile, BASE)['experience_history'][0]


def test_explicit_role_sources_and_empty_overrides_take_precedence_over_template():
    for bullets in [[], ['A different explicitly supplied accomplishment.']]:
        profile = copy.deepcopy(PROFILE)
        profile['experience_history'][0]['source_bullets'] = bullets
        assert profile_with_resume_context(profile, BASE)['experience_history'][0]['source_bullets'] == bullets


def test_import_normalization_and_snapshot_roundtrip_preserve_full_context(monkeypatch):
    profile = resume_app.normalize_profile(resume_app.profile_from_resume(BASE))
    assert profile['experience_history'][0]['source_bullets'] == [SOURCE]
    assert profile['technical_skills'] == BASE['technical_skills']
    assert profile['education'] == BASE['education']
    assert profile['summary'] == SUMMARY
    monkeypatch.setattr(resume_app, 'load_base_resume', lambda: {})
    roles = resume_app.experience_blueprints_from_snapshot({
        'profile_snapshot': profile,
        'experience_history_snapshot': PROFILE['experience_history'],
    })
    assert roles[0]['source_bullets'] == [SOURCE]
    changed = resume_app.merge_experience_history_lists(profile['experience_history'], [{**PROFILE['experience_history'][0], 'company': 'Different'}])
    assert 'source_bullets' not in changed[0]


def test_summary_skills_and_synthesis_receive_actual_candidate_context(monkeypatch):
    monkeypatch.setattr(resume_app, 'load_base_resume', lambda: copy.deepcopy(BASE))
    requests = []
    skills = {'updated_skills': [{'category': 'Programming Languages', 'items': ['Python', 'SQL']}]}
    def call(**kwargs):
        requests.append(kwargs)
        if kwargs['schema_name'] == 'resume_title_summary_generation':
            return {'updated_title': 'Customer Integration Engineer', 'updated_summary': SUMMARY}
        if kwargs['schema_name'] == 'resume_skills_generation':
            return copy.deepcopy(skills)
        return {'updated_title': 'Customer Integration Engineer', 'updated_summary': SUMMARY, **copy.deepcopy(skills), 'experience_titles': {'mckinsey': 'Software Engineer'}}
    monkeypatch.setattr(resume_app, 'call_openai_structured_output', call)
    monkeypatch.setattr(resume_app, 'validate_skills_only_payload', lambda *args: [])
    resume_app.generate_title_summary_from_analysis(api_key='test', analysis_payload=ANALYSIS, candidate_profile=PROFILE)
    generated_skills = resume_app.generate_skills_from_analysis(api_key='test', analysis_payload=ANALYSIS, candidate_profile=PROFILE)
    bps = resume_app.current_experience_blueprints(PROFILE)[:1]
    resume_app.generate_final_synthesis_from_analysis(
        api_key='test', analysis_payload=ANALYSIS, job_description='Vehicle integrations',
        preliminary_skills_payload=generated_skills, combined_experience_payload={'experience': {}},
        active_blueprints=bps, candidate_profile=PROFILE,
    )
    assert len(requests) == 3
    for request in requests:
        assert SOURCE in request['user_prompt']
        assert 'technical_skills' in request['user_prompt']
        assert 'Computer Science' in request['user_prompt']


def test_pasted_failure_is_rejected_before_delivery_not_hidden(monkeypatch):
    bad = {'updated_title': 'Customer Integration Engineer',
           'updated_summary': "The supplied experience record does not include verified accomplishment bullets. This resume therefore identifies evidence needed to validate alignment.",
           'updated_skills': [],
           'experience': {'mckinsey': {'title': 'Software Engineer', 'bullets': ['[Confirm: proposed work] Installed vehicle DAQ hardware. [Confirm metric: deployments]']}}}
    monkeypatch.setattr(resume_app, 'load_base_resume', lambda: copy.deepcopy(BASE))
    bps = resume_app.current_experience_blueprints(PROFILE)[:1]
    issues = resume_body_issues(bad, bps)
    assert any('internal review commentary' in i for i in issues)
    assert any('unverified proposal' in i for i in issues)
    with pytest.raises(ValueError, match='needs repair before display'):
        resume_app.format_generated_resume_text(bad, bps)
    bad['updated_summary'] = SUMMARY
    bad['experience']['mckinsey']['bullets'] = [SOURCE]
    with pytest.raises(ValueError, match='empty Skills section'):
        resume_app.format_generated_resume_text(bad, bps)


def test_missing_measurements_stay_in_review_not_the_resume_body(monkeypatch):
    monkeypatch.setattr(resume_app, 'load_base_resume', lambda: copy.deepcopy(BASE))
    bps = resume_app.current_experience_blueprints(PROFILE)[:1]
    payload = {'experience': {'mckinsey': {'title': 'Software Engineer',
               'bullets': ['Built Python integration tests for reconciliation services.'],
               'bullet_evidence': [{'bullet_number': 1, 'source_refs': ['source_bullets.1'], 'confirmation_questions': []}]}}}
    prepared = resume_app.prepare_experience_draft(payload, bps, resume_app._numeric_tokens)
    assert '[Confirm' not in json.dumps(prepared)
    assert resume_app.validate_experience_numeric_coverage(prepared, bps, ANALYSIS) == []
    preflight = resume_app._quality_audit_preflight(prepared, bps)
    assert preflight['pending_confirmations'] == []
    assert preflight['numerical_target_notes'] and '80%' in preflight['numerical_target_notes'][0]['confirmation']


def test_empty_skills_are_retried_then_fail_as_a_stage_error(monkeypatch):
    monkeypatch.setattr(resume_app, 'load_base_resume', lambda: copy.deepcopy(BASE))
    calls = []
    def empty(**kwargs):
        calls.append(kwargs)
        return {'updated_skills': []}
    monkeypatch.setattr(resume_app, 'call_openai_structured_output', empty)
    with pytest.raises(ValueError, match='empty section despite available candidate resume context'):
        resume_app.generate_skills_from_analysis(api_key='test', analysis_payload=ANALYSIS, candidate_profile=PROFILE)
    assert len(calls) == 2


def test_explicit_regeneration_refreshes_sources_without_changing_inline_job_identity():
    from resume_generation_context import refresh_profile_evidence
    old = copy.deepcopy(PROFILE)
    old['experience_history'][0]['source_bullets'] = ['Old source']
    current = copy.deepcopy(PROFILE)
    current['experience_history'][0]['source_bullets'] = [SOURCE]
    assert refresh_profile_evidence(old, current)['experience_history'][0]['source_bullets'] == [SOURCE]
    old['experience_history'][0]['company'] = 'Inline edited company'
    refreshed = refresh_profile_evidence(old, current)
    assert refreshed['experience_history'][0]['company'] == 'Inline edited company'
    assert refreshed['experience_history'][0]['source_bullets'] == ['Old source']


def test_app_bundle_is_revalidated_after_build():
    response = resume_app.app.test_client().get('/static/react/app.js')
    assert response.status_code == 200
    assert response.cache_control.no_cache
    assert response.cache_control.max_age == 0
    response.close()


def test_main_app_endpoints_forward_frozen_candidate_context(monkeypatch):
    from test_resume_pipeline_stages import SUMMARY as VALID_SUMMARY
    monkeypatch.setattr(resume_app, 'load_base_resume', lambda: copy.deepcopy(BASE))
    monkeypatch.setattr(resume_app, 'ai_sessions', {'handoff-test': {
        'profile_snapshot': copy.deepcopy(PROFILE), 'analysis': ANALYSIS,
        'enabled_experience_keys': ['mckinsey'], 'resume_mode': 'professional',
    }})
    requests = []
    def call(**kwargs):
        requests.append(kwargs)
        if kwargs['schema_name'] == 'resume_skills_generation':
            return {'updated_skills': [{'category': 'Programming Languages', 'items': ['Python', 'SQL']}]}
        return {'updated_title': 'Customer Integration Engineer', 'updated_summary': VALID_SUMMARY}
    monkeypatch.setattr(resume_app, 'call_openai_structured_output', call)
    client = resume_app.app.test_client()
    for route in ('generate-title-summary', 'generate-skills'):
        response = client.post('/api/ai/' + route, json={'session_id': 'handoff-test'})
        assert response.status_code == 200, response.get_json()
    assert len(requests) == 2
    assert all(SOURCE in request['user_prompt'] and 'Computer Science' in request['user_prompt'] for request in requests)


def test_hardware_requirements_cannot_become_software_employment_claims():
    from resume_bullet_quality import claim_evidence_issues
    bp = {'key': 'mckinsey', 'default_title': 'Software Engineer', 'source_bullets': [SOURCE]}
    payload = {'experience': {'mckinsey': {'title': 'Software Engineer',
        'bullets': ['Installed portable DAQ and captured CAN bus signals at customer vehicle sites.'],
        'bullet_evidence': [{'bullet_number': 1, 'source_refs': ['source_bullets.1'], 'confirmation_questions': []}]}}}
    assert any('hardware or controls claim' in issue for issue in claim_evidence_issues(payload, [bp], resume_app._numeric_tokens))
    bp['source_bullets'] = ['Installed portable DAQ and captured CAN bus signals at customer vehicle sites.']
    assert claim_evidence_issues(payload, [bp], resume_app._numeric_tokens) == []

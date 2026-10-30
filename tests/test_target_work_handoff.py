import copy

import pytest
import app as resume_app
from resume_bullet_quality import project_characteristics
from resume_target_work import target_work_issues, jd_source_spans, normalize_target_work


JD = 'Software Engineer II. Native App Qualifications: Proficiency in Kotlin and/or Swift. Consume RESTful JSON services.'
WORK = {
    'system_type': 'Native mobile applications',
    'primary_workflow': 'Implement native application modules that consume RESTful JSON services',
    'users': [], 'work_objects': ['RESTful JSON services'],
    'engineering_changes': ['Implement and test native application modules'],
    'specialist_requirements': [{'capability': 'Proficiency in Kotlin and/or Swift', 'jd_quote': 'Proficiency in Kotlin and/or Swift.'}],
    'evidence_expectations': ['Native implementation and API-consumption evidence'],
    'unknowns': ['Specific product and end-user workflow are not stated'],
}
ANALYSIS = {'target_role': 'Software Engineer II', 'role_family': 'native application engineering',
            'generation_route_key': 'fullstack_product', 'target_work': WORK,
            'top_requirements': ['Native application development in Kotlin and/or Swift']}


def test_target_work_survives_normalization_compaction_and_characteristics():
    for result in [resume_app.normalize_analysis_payload(ANALYSIS),
                   resume_app.compact_analysis_for_generation(ANALYSIS), project_characteristics(ANALYSIS, JD)]:
        assert result['target_work'] == WORK
    output = project_characteristics(ANALYSIS, JD)
    output['target_work']['engineering_changes'].clear()
    assert WORK['engineering_changes']
    assert resume_app.normalize_analysis_payload(ANALYSIS)['role_family'] == 'native application engineering'


def test_target_work_requires_posting_grounded_specialist_evidence():
    assert target_work_issues(ANALYSIS, JD) == []
    bad = copy.deepcopy(ANALYSIS)
    bad['target_work']['specialist_requirements'][0]['jd_quote'] = 'Build a pizza ordering app'
    assert target_work_issues(bad, JD)
    assert target_work_issues({}, JD)
    bad = copy.deepcopy(ANALYSIS)
    bad['target_work']['specialist_requirements'][0]['jd_quote'] = 'Software Engineer II'
    assert any('unrelated evidence' in issue for issue in target_work_issues(bad, JD))
    bad = copy.deepcopy(ANALYSIS)
    bad['target_work']['users'] = ['Customers ordering pizza']
    assert any('inferred product context' in issue for issue in target_work_issues(bad, JD))


def test_old_analysis_cache_is_not_used_as_new_target_work(monkeypatch):
    calls = []
    monkeypatch.setattr(resume_app, 'get_cached_ai_stage_result', lambda key: {'role_family': 'backend application engineering'})
    monkeypatch.setattr(resume_app, 'save_cached_ai_stage_result', lambda **kwargs: None)
    def generate(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(ANALYSIS)
    monkeypatch.setattr(resume_app, 'call_openai_structured_output', generate)
    assert resume_app.analyze_job_description(api_key='test', job_description=JD)['target_work'] == WORK
    assert len(calls) == 1


def test_new_analysis_rejects_unsubstantiated_target_work_before_caching(monkeypatch):
    monkeypatch.setattr(resume_app, 'get_cached_ai_stage_result', lambda key: None)
    monkeypatch.setattr(resume_app, 'call_openai_structured_output', lambda **kwargs: {'role_family': 'backend'})
    def forbidden(**kwargs):
        raise AssertionError('Invalid analysis must not be cached')
    monkeypatch.setattr(resume_app, 'save_cached_ai_stage_result', forbidden)
    with pytest.raises(ValueError, match='Missing target_work'):
        resume_app.analyze_job_description(api_key='test', job_description=JD)


def test_analysis_selects_source_ids_and_server_supplies_original_quotes(monkeypatch):
    jd = 'Required: C#/.NET Core, LINQ and SQL. Python experience is optional.'
    spans = jd_source_spans(jd)
    source_id = next(k for k,v in spans.items() if 'C#' in v)
    raw = copy.deepcopy(ANALYSIS)
    raw['target_work'].update(users=[], work_objects=[], specialist_requirements=[{'source_span_id': source_id}])
    saved, requests = [], []
    monkeypatch.setattr(resume_app, 'get_cached_ai_stage_result', lambda key: None)
    monkeypatch.setattr(resume_app, 'save_cached_ai_stage_result', lambda **kwargs: saved.append(kwargs))
    def generate(**kwargs):
        requests.append(kwargs)
        shape = kwargs['schema']['properties']['target_work']['properties']['specialist_requirements']['items']
        assert shape['required'] == ['source_span_id']
        assert source_id in shape['properties']['source_span_id']['enum']
        assert 'job_description_spans' in kwargs['user_prompt']
        return raw
    monkeypatch.setattr(resume_app, 'call_openai_structured_output', generate)
    result = resume_app.analyze_job_description(api_key='test', job_description=jd)
    assert len(requests) == 1
    requirement = result['target_work']['specialist_requirements'][0]
    assert requirement == {'capability': spans[source_id], 'jd_quote': spans[source_id]}
    assert target_work_issues(result, jd) == []
    assert saved[0]['result'] == result
    assert raw['target_work']['specialist_requirements'] == [{'source_span_id': source_id}]


def test_typographic_variants_are_accepted_but_unrelated_evidence_is_rejected():
    jd = 'Build C# and C++ applications using API’s and object‐oriented patterns.'
    analysis = copy.deepcopy(ANALYSIS)
    analysis['target_work'].update(users=[], work_objects=[], specialist_requirements=[{
        'capability': 'C# and C++', 'jd_quote': "Build C# and C++ applications using API's and object-oriented patterns."}])
    assert target_work_issues(analysis, jd) == []
    analysis['target_work']['specialist_requirements'][0]['capability'] = 'Kotlin'
    assert any('unrelated evidence' in s for s in target_work_issues(analysis, jd))
    analysis['target_work']['specialist_requirements'][0]['jd_quote'] = 'Build Kotlin mobile applications.'
    assert any('absent from the JD' in s for s in target_work_issues(analysis, jd))


def test_unknown_source_references_and_invented_requirements_still_fail():
    analysis = copy.deepcopy(ANALYSIS)
    analysis['target_work']['specialist_requirements'] = [{'source_span_id': 'jd_span_99999'}]
    normalized = normalize_target_work(analysis, JD)
    assert any('invalid JD source reference' in s for s in target_work_issues(normalized, JD))


@pytest.mark.parametrize('field,unsupported', [('users', 'customers'), ('work_objects', 'iOS app')])
def test_optional_context_is_omitted_and_recorded_without_blocking(field, unsupported):
    analysis = copy.deepcopy(ANALYSIS)
    analysis['target_work'][field] = ['RESTful JSON services', unsupported]
    original = copy.deepcopy(analysis)
    result = normalize_target_work(analysis, JD)
    assert result['target_work'][field] == ['RESTful JSON services']
    assert any(unsupported in note and 'Unconfirmed' in note for note in result['target_work']['unknowns'])
    assert target_work_issues(result, JD) == []
    assert analysis == original
    assert normalize_target_work(result, JD) == result
    assert result['target_work']['specialist_requirements'] == WORK['specialist_requirements']


def test_optional_context_does_not_mask_real_specialist_errors():
    analysis = copy.deepcopy(ANALYSIS)
    analysis['target_work']['users'] = ['Invented customers']
    analysis['target_work']['specialist_requirements'][0]['jd_quote'] = 'Unrelated invented project'
    result = normalize_target_work(analysis, JD)
    assert result['target_work']['users'] == []
    assert any('absent from the JD' in s for s in target_work_issues(result, JD))


def test_cached_optional_context_is_normalized_without_another_model_call(monkeypatch):
    cached = copy.deepcopy(ANALYSIS)
    cached['target_work']['users'] = ['customers']
    monkeypatch.setattr(resume_app, 'get_cached_ai_stage_result', lambda key: cached)
    monkeypatch.setattr(resume_app, 'call_openai_structured_output', lambda **kwargs: pytest.fail('Unnecessary extra model call'))
    result = resume_app.analyze_job_description(api_key='test', job_description=JD)
    assert result['target_work']['users'] == []
    assert target_work_issues(result, JD) == []
    assert cached['target_work']['users'] == ['customers']


@pytest.mark.parametrize('stage', ['skills', 'recent', 'synthesis', 'audit'])
def test_downstream_production_requests_retain_system_workflow_and_specialization(monkeypatch, stage):
    class Captured(Exception):
        pass
    requests = []
    def capture(**kwargs):
        requests.append(kwargs)
        raise Captured()
    monkeypatch.setattr(resume_app, 'call_openai_structured_output', capture)
    bp = copy.deepcopy(resume_app.EXPERIENCE_BLUEPRINTS[0])
    bp.update(default_title='Software Engineer', source_bullets=['Built backend REST APIs.'])
    profile = {'projects': [{'name': 'Native app', 'bullets': ['Built a Swift iOS application.']}]}
    common = dict(api_key='test', analysis_payload=ANALYSIS)
    skill = {'updated_skills': [{'category': 'Programming Languages', 'items': ['Swift', 'Java']}]}
    exp = {'experience': {bp['key']: {'title': 'Software Engineer', 'bullets': ['Built backend REST APIs.']}}}
    with pytest.raises(Captured):
        if stage == 'skills':
            resume_app.generate_skills_from_analysis(**common, candidate_profile=profile)
        elif stage == 'recent':
            resume_app.generate_experience_subset_from_analysis(**common, job_description=JD, blueprints=[bp], model=resume_app.RESUME_MODEL, timeout_seconds=30, preliminary_skills_payload=skill)
        elif stage == 'synthesis':
            resume_app.generate_final_synthesis_from_analysis(**common, job_description=JD, preliminary_skills_payload=skill, combined_experience_payload=exp, active_blueprints=[bp], candidate_profile=profile)
        else:
            resume_app.generate_resume_quality_audit(**common, job_description=JD, current_resume={**exp, **skill}, active_blueprints=[bp], candidate_profile=profile)
    prompt = requests[0]['user_prompt']
    for text in [WORK['system_type'], WORK['primary_workflow'], WORK['specialist_requirements'][0]['jd_quote']]:
        assert text in prompt


def test_analysis_schema_requires_system_description_beyond_route_and_technologies():
    schema = resume_app.ai_analysis_schema()
    assert 'target_work' in schema['required']
    assert set(WORK) == set(schema['properties']['target_work']['required'])


def test_app_reanalysis_refreshes_legacy_analysis_and_dependent_stage_caches(monkeypatch):
    session = {'analysis': {'role_family': 'backend application engineering'},
               'skills': {'old': True}, 'experience_recent': {'old': True},
               'resume_content': 'User-edited draft', 'turns': [], 'enabled_experience_keys': []}
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setattr(resume_app, 'get_ai_session', lambda *args: ('test', session))
    monkeypatch.setattr(resume_app, 'infer_company_name_for_preflight', lambda *args: '')
    monkeypatch.setattr(resume_app, 'current_job_preflight', lambda *args, **kwargs: {'blocked': False})
    monkeypatch.setattr(resume_app, 'analyze_job_description', lambda **kwargs: copy.deepcopy(ANALYSIS))
    monkeypatch.setattr(resume_app, 'classify_resume_job', lambda *args: {'category': 'software_engineering', 'suitable': True})
    response = resume_app.app.test_client().post('/api/ai/analyze', json={'job_description': JD})
    assert response.status_code == 200
    assert response.get_json()['analysis']['target_work'] == WORK
    assert session['skills'] is None and session['experience_recent'] is None
    assert session['resume_content'] == 'User-edited draft'

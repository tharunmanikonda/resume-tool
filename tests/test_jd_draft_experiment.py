import copy
import json
from pathlib import Path

import pytest
import app as app
import jd_draft_experiment as experiment

JD = 'Build web applications. Demonstrated experience using AI-powered development tools. Experience designing multi-step agents is a strong plus.'
ROLE = {'key': 'mckinsey', 'company': 'Example', 'location': 'US', 'dates': '2024-Present',
        'default_title': 'Software Engineer', 'bullet_min': 1, 'bullet_max': 1,
        'source_bullets': ['PRIVATE_SAVED_BULLET'], 'anchor': 'PRIVATE_ANCHOR',
        'achievements': ['PRIVATE_ACHIEVEMENT'], 'metric_evidence': 'PRIVATE_METRIC'}
PLAN = {'role_positioning': 'Software Engineer', 'target_system': 'Web applications', 'target_workflow': 'Build and test web features',
        'required': [{'capability': 'AI-powered development tools', 'jd_quote': 'Demonstrated experience using AI-powered development tools.'}],
        'optional': [{'capability': 'multi-step agents', 'jd_quote': 'Experience designing multi-step agents is a strong plus.'}],
        'unknowns': ['Actual product'], 'experience': {'mckinsey': {'system': 'Proposed account portal',
            'workflow': 'Build and test features', 'scope': 'Implement application modules', 'assumptions': ['A web portal is proposed'],
            'contributions': ['Implement a reliable request API']}}}
DRAFT = {'headline': 'Software Engineer', 'summary': 'Proposed software engineering experience.',
         'skills': [{'category': 'Backend Engineering', 'items': ['REST APIs', 'Request validation']}],
         'experience': {'mckinsey': {'bullets': [{'text': 'Implemented request validation for 500 requests using typed API contracts and explicit error responses, preventing malformed payloads from reaching service handlers during integration testing and release validation.',
            'contribution_number': 1, 'measurement': {'kind': 'scale', 'value': '500', 'unit': 'requests',
                                                   'context': 'proposed workload', 'status': 'illustrative_unverified'}}]}}}


def aligned_targeting(inputs):
    clauses = inputs.get('job_description_clauses') or experiment.jd_clause_map(inputs.get('job_description', JD))
    return {'decision': 'aligned', 'corrections': [], 'assessment': {
        'level_scope': 'Feature-level individual contributor', 'team_path': 'Application engineering',
        'choice_basis': 'conservative_assumption',
        'primary_focus': [{'source_clause_id': next(iter(clauses)), 'focus': 'Implement application features'}],
        'secondary_focus': [], 'excluded_paths': [], 'rationale': 'Implementation scope fits the selected role'}}


def test_targeting_corrections_are_exact_atomic_and_do_not_rewrite_other_roles():
    result = aligned_targeting({'job_description': JD})
    result.update(decision='corrected', corrections=[{
        'target': 'contribution', 'role_key': 'mckinsey', 'contribution_number': 1,
        'old_text': PLAN['experience']['mckinsey']['contributions'][0],
        'replacement': 'Implement native API integration | typed service responses | reliable feature data | request latency (ms)'}])
    original = copy.deepcopy(PLAN)
    corrected, assessment = experiment.apply_targeting_check(original, result, JD)
    assert original == PLAN
    assert corrected['required'] == PLAN['required']
    assert corrected['experience']['mckinsey']['scope'] == PLAN['experience']['mckinsey']['scope']
    assert corrected['experience']['mckinsey']['contributions'] == [result['corrections'][0]['replacement']]
    assert assessment['primary_focus'][0]['jd_quote'] in JD
    result['corrections'][0]['old_text'] = 'Stale plan'
    with pytest.raises(ValueError, match='stale'):
        experiment.apply_targeting_check(original, result, JD)
    assert original == PLAN


def test_writing_receives_corrected_project_direction_before_any_resume_call(setup, monkeypatch):
    jd = 'Build .NET services using SQL and LINQ. RAG experience is preferred.'
    bad = copy.deepcopy(PLAN)
    bad.update(role_positioning='Applied AI engineer', target_system='RAG assistant')
    bad['required'] = [{'capability': '.NET services', 'jd_quote': 'Build .NET services using SQL and LINQ.'}]
    bad['optional'] = [{'capability': 'RAG', 'jd_quote': 'RAG experience is preferred.'}]
    bad['experience']['mckinsey'].update(system='RAG assistant', contributions=['Implement RAG retrieval'])
    stages = []
    def generate(stage, schema, prompt, inputs):
        stages.append(stage)
        if stage == 'plan':
            return copy.deepcopy(bad)
        if stage == 'targeting':
            result = aligned_targeting(inputs)
            result['decision'] = 'corrected'
            result['assessment']['primary_focus'][0]['focus'] = '.NET application delivery'
            result['assessment']['secondary_focus'] = [{'source_clause_id': 'jd_2', 'focus': 'Optional RAG knowledge'}]
            result['corrections'] = [
                {'target': 'role_positioning', 'old_text': 'Applied AI engineer', 'replacement': '.NET application engineer'},
                {'target': 'target_system', 'old_text': 'RAG assistant', 'replacement': 'Enterprise .NET application'},
                {'target': 'system', 'role_key': 'mckinsey', 'old_text': 'RAG assistant', 'replacement': '.NET feature services'},
                {'target': 'contribution', 'role_key': 'mckinsey', 'contribution_number': 1,
                 'old_text': 'Implement RAG retrieval', 'replacement': 'Implement feature APIs | .NET, SQL, LINQ | reliable data access | response time (ms)'}]
            return result
        assert inputs['targeting_assessment']['primary_focus'][0]['focus'] == '.NET application delivery'
        assert inputs['checked_plan']['target_system'] == 'Enterprise .NET application'
        assert inputs['checked_plan']['optional'][0]['capability'] == 'RAG'
        if stage == 'review':
            return {'summary': 'Reviewed', 'findings': [], 'changes': []}
        return copy.deepcopy(DRAFT)
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(jd, [ROLE], 'professional')
    assert stages == ['plan', 'targeting', 'core', 'experience', 'review']
    assert result['plan']['role_positioning'] == '.NET application engineer'
    assert result['targeting_assessment']['secondary_focus'][0]['focus'] == 'Optional RAG knowledge'


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(app, 'settings', {**copy.deepcopy(app.settings), 'experimental_jd_drafting': True})
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setattr(app, 'current_experience_blueprints', lambda **kwargs: [copy.deepcopy(ROLE)])
    monkeypatch.setattr(app, 'current_job_preflight', lambda *args, **kwargs: {'blocked': False})
    monkeypatch.setattr(app, 'jd_experiment_sessions', {})
    monkeypatch.setattr(app, 'ai_sessions', {})
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        if kwargs['schema_name'].endswith('targeting'):
            return aligned_targeting(json.loads(kwargs['user_prompt']))
        if kwargs['schema_name'].endswith('review'):
            return {'summary': 'Ready to review assumptions', 'ready_for_assumption_review': True, 'findings': []}
        return copy.deepcopy(PLAN if kwargs['schema_name'].endswith('plan') else DRAFT)
    monkeypatch.setattr(app, 'call_openai_structured_output', generate)
    return app.app.test_client(), calls


def test_source_free_plan_and_draft_work_without_factual_provenance(setup):
    client, calls = setup
    response = client.post('/api/ai/jd-draft/plan', json={'job_description': JD, 'profile': {'summary': 'PRIVATE_SUMMARY'}})
    assert response.status_code == 200, response.json
    generated = client.post('/api/ai/jd-draft/generate', json={'plan_id': response.json['plan_id'], 'source_bullets': ['PRIVATE_EXTRA']})
    assert generated.status_code == 200, generated.json
    assert generated.json['assumptions_unverified'] is True
    assert 'unverified' in generated.json['markdown']
    assert generated.json['numerical_notes'] == []
    prompts = json.dumps(calls)
    for private in ['PRIVATE_SAVED_BULLET', 'PRIVATE_ANCHOR', 'PRIVATE_ACHIEVEMENT', 'PRIVATE_METRIC', 'PRIVATE_SUMMARY', 'PRIVATE_EXTRA']:
        assert private not in prompts
    assert set(experiment.headings_only([ROLE])[0]) == set(experiment.HEADINGS)


def test_experiment_is_disabled_by_default_and_has_no_api_side_effect(setup, monkeypatch):
    client, calls = setup
    monkeypatch.setitem(app.settings, 'experimental_jd_drafting', False)
    assert client.post('/api/ai/jd-draft/plan', json={'job_description': JD}).status_code == 403
    assert client.post('/api/ai/jd-draft/generate', json={'plan_id': 'x'}).status_code == 403
    assert not calls


def test_optional_label_does_not_block_a_grounded_project_plan():
    plan = copy.deepcopy(PLAN)
    plan['required'].append({'capability': 'multi-step agents', 'jd_quote': 'Experience designing multi-step agents'})
    assert experiment.plan_issues(plan, [ROLE], JD) == []  # Classification labels do not block generation.
    assert experiment.plan_issues(PLAN, [ROLE], JD) == []


def test_mixed_dynamics_requirement_preserves_each_qualification_priority():
    text = '3-5 Years development experience in Dynamics 365 Finance & Operations required, experience developing in Microsoft Power Platform is a plus.'
    jd = 'Required Qualifications: ' + text
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': 'Dynamics 365 Finance & Operations', 'jd_quote': text}]
    plan['optional'] = [{'capability': 'Microsoft Power Platform', 'jd_quote': text}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []
    clauses = experiment.jd_clauses(text)
    assert clauses == ['3-5 Years development experience in Dynamics 365 Finance & Operations required',
                       'experience developing in Microsoft Power Platform is a plus.']
    wrong = copy.deepcopy(plan)
    wrong['required'] += wrong['optional']
    assert experiment.plan_issues(wrong, [ROLE], jd) == []  # Classification labels do not block generation.
    wrong = copy.deepcopy(plan)
    wrong['optional'] += wrong['required']
    assert experiment.plan_issues(wrong, [ROLE], jd) == []  # Classification labels do not block generation.


def test_priority_splitting_preserves_lists_and_saved_quote_identity():
    assert experiment.jd_clauses('Experience in Java, Python, SQL preferred.') == ['Experience in Java, Python, SQL preferred.']
    jd = 'Dynamics 365 required, experience in Power Platform is a plus. Build APIs.'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': 'APIs', 'jd_quote': 'Build APIs.', 'source_clause_id': 'jd_2'}]
    assert experiment.normalize_plan(plan, jd)['required'][0]['jd_quote'] == 'Build APIs.'


@pytest.mark.parametrize('case', json.loads(Path('tests/fixtures/jd_priority_failures.json').read_text()),
                         ids=lambda case: case['name'])
def test_saved_flattened_priority_failures_replay_without_api(case):
    plan = copy.deepcopy(PLAN)
    for level in ('required', 'optional'):
        plan[level] = copy.deepcopy(case[level])
        for requirement in plan[level]:
            requirement['jd_quote'] = case['old_clauses'][requirement.pop('source_clause_id')]
    normalized = experiment.normalize_plan(plan, case['jd'])
    assert [r['capability'] for r in normalized['required']] == [r['capability'] for r in plan['required']]
    assert all(r['jd_quote'] in case['jd'] for level in ('required', 'optional') for r in normalized[level])
    issues = experiment.plan_issues(normalized, [ROLE], case['jd'])
    assert not any('Optional/bonus' in issue or 'combining required' in issue for issue in issues)
    assert issues == []
    assert experiment.plan_issues(normalized, [ROLE], case['jd']) == []


@pytest.mark.parametrize('required_heading,optional_heading', [
    ('Minimum Qualifications', 'Preferred Qualifications'),
    ('REQUIRED QUALIFICATIONS', 'PREFERRED QUALIFICATIONS'),
    ('Required Skills', 'Nice to Have'),
    ('Technical Skills Required', 'Preferred'),
])
def test_section_priority_is_local_with_or_without_colons(required_heading, optional_heading):
    jd = f'{required_heading} Build Java servicesExperience with SQL {optional_heading} Experience with Kubernetes'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': 'Java APIs', 'jd_quote': jd}]
    plan['optional'] = [{'capability': 'Kubernetes', 'jd_quote': jd}]
    normalized = experiment.normalize_plan(plan, jd)
    assert normalized['required'][0]['capability'] == 'Java APIs'
    assert 'Preferred' not in normalized['required'][0]['jd_quote']
    assert experiment.plan_issues(normalized, [ROLE], jd) == []
    wrong = copy.deepcopy(normalized)
    wrong['required'].append(wrong['optional'].pop())
    assert experiment.plan_issues(wrong, [ROLE], jd) == []  # Classification labels do not block generation.
    wrong = copy.deepcopy(normalized)
    wrong['optional'].append(copy.deepcopy(wrong['required'][0]))
    assert experiment.plan_issues(wrong, [ROLE], jd) == []  # Classification labels do not block generation.


def test_priority_continuation_stops_at_next_flattened_requirement():
    jd = 'Required Qualifications Strong Python skillsCloud migration is a plus.'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': 'Python', 'jd_quote': 'Strong Python skills'}]
    plan['optional'] = [{'capability': 'Cloud migration', 'jd_quote': 'Cloud migration'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []


def test_broad_saved_quote_is_not_a_classification_blocker():
    jd = 'Required Qualifications Build APIs Preferred Qualifications Build Kubernetes tools'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': jd, 'jd_quote': jd}]
    plan['optional'] = []
    normalized = experiment.normalize_plan(plan, jd)
    assert normalized['required'][0]['capability'] == jd
    assert experiment.plan_issues(normalized, [ROLE], jd) == []  # Classification labels do not block generation.


def test_heading_detection_does_not_split_customer_requirements_or_brd_skills():
    jd = ('Job Overview This role meets customer requirements and business goals. '
          'Responsibilities: Maintain business requirements documentation. '
          'Knowledge, Skills and Abilities: Business Requirements Documentation (BRD) (Required)'
          'Source Code Management (Required)')
    assert [m.group() for m in experiment._jd_section_matches(jd)] == [
        'Job Overview', 'Responsibilities', 'Knowledge, Skills and Abilities']
    clauses = experiment.jd_clauses(jd)
    assert any('customer requirements and business goals.' in text for text in clauses)
    assert any('Business Requirements Documentation (BRD) (Required)' in text for text in clauses)


@pytest.mark.parametrize('required,preferred', [('Required','Preferred'), ('REQUIRED','PREFERRED'), ('required','preferred')])
@pytest.mark.parametrize('separator', [' ', '\n'])
def test_postfix_annotations_stay_with_their_own_items(required, preferred, separator):
    jd = (f'Education and Work Experience: Degree ({required}) '
          f'Less than 2 years experience.{separator}({preferred}) '
          f'Knowledge, Skills and Abilities: Analytical Thinking ({required})'
          f'Analytics ({required})Business Requirements Documentation (BRD) ({required})')
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability':'Analytics', 'jd_quote':f'Analytics ({required})'}]
    plan['optional'] = [{'capability':'Experience duration', 'jd_quote':f'Less than 2 years experience.{separator}({preferred})'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []
    records = experiment._jd_clause_records(jd)
    assert (f'Less than 2 years experience.{separator}({preferred})', 'optional') in records
    assert (f'Analytics ({required})', 'required') in records
    assert not any(f'({preferred}) Knowledge' in text for text, _ in records)
    wrong = copy.deepcopy(plan)
    wrong['required'].append(wrong['optional'].pop())
    assert experiment.plan_issues(wrong, [ROLE], jd) == []  # Classification labels do not block generation.
    wrong = copy.deepcopy(plan)
    wrong['optional'].append(copy.deepcopy(wrong['required'][0]))
    assert experiment.plan_issues(wrong, [ROLE], jd) == []  # Classification labels do not block generation.


def test_explicit_item_annotations_override_section_defaults():
    jd = 'Preferred Qualifications Python (Required)Required Qualifications Kotlin (Preferred)'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability':'Python', 'jd_quote':'Preferred Qualifications Python (Required)'}]
    plan['optional'] = [{'capability':'Kotlin', 'jd_quote':'Required Qualifications Kotlin (Preferred)'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []


@pytest.mark.parametrize('separator', ['; ', ', ', '; and ', ', but ', ';\n'])
def test_independently_qualified_skills_split_without_changing_source(separator):
    jd = f'Java required{separator}AWS preferred.'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability':'Java', 'jd_quote':jd}]
    plan['optional'] = [{'capability':'AWS', 'jd_quote':jd}]
    result = experiment.normalize_plan(plan, jd)
    assert experiment.plan_issues(result, [ROLE], jd) == []
    assert all(r['jd_quote'] in jd for level in ('required','optional') for r in result[level])
    assert result['required'][0]['jd_quote'].rstrip(';') == 'Java required'
    assert result['optional'][0]['jd_quote'] == 'AWS preferred.'
    wrong = copy.deepcopy(result)
    wrong['required'].append(wrong['optional'].pop())
    assert experiment.plan_issues(wrong, [ROLE], jd) == []  # Classification labels do not block generation.
    wrong = copy.deepcopy(result)
    wrong['optional'].append(copy.deepcopy(wrong['required'][0]))
    assert experiment.plan_issues(wrong, [ROLE], jd) == []  # Classification labels do not block generation.


@pytest.mark.parametrize('modifier', ['is optional', 'is not required', '(preferred but not required)',
                                     '(preferred for this role)', '(strongly preferred)', '(experience preferred)'])
def test_explanatory_preferences_are_not_discarded_as_technology_variants(modifier):
    jd = f'Required Qualifications Java required. Python experience {modifier}.'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability':'Java', 'jd_quote':'Java required.'}]
    plan['optional'] = [{'capability':'Python', 'jd_quote':f'Python experience {modifier}.'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []
    plan['required'].append(plan['optional'].pop())
    assert experiment.plan_issues(plan, [ROLE], jd) == []  # Classification labels do not block generation.


def test_preferably_a_named_variant_does_not_downgrade_the_base_skill():
    jd = 'Required Qualifications Working knowledge of cloud platforms, preferably AWS.'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability':'cloud platforms', 'jd_quote':jd}]
    plan['optional'] = [{'capability':'AWS', 'jd_quote':jd}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []
    plan['required'].append(plan['optional'].pop())
    assert experiment.plan_issues(plan, [ROLE], jd) == []  # Classification labels do not block generation.


def test_required_travel_context_is_not_a_required_engineering_skill():
    jd = 'Required Qualifications Java required. Travel: Travel Required: Yes'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability':'Java', 'jd_quote':'Java required.'}]
    plan['optional'] = [{'capability':'Travel', 'jd_quote':'Travel: Travel Required: Yes'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []


@pytest.mark.parametrize('heading', ['BONUS SKILLS', 'Optional Skills', 'Desirable Qualifications',
                                    'Nice-to-Have', 'Nice‑to‑Have', 'Preferred   Qualifications',
                                    'Preferred\nQualifications', 'Preferred\u00a0Qualifications'])
def test_additional_optional_headings_apply_to_every_item_in_section(heading):
    jd = f'Required Qualifications Java required.\n{heading}\nKubernetes\nRedis'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability':'Java', 'jd_quote':'Java required.'}]
    plan['optional'] = [{'capability':'Redis','jd_quote':'Redis'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []
    plan['required'].append(plan['optional'].pop())
    assert experiment.plan_issues(plan, [ROLE], jd) == []  # Classification labels do not block generation.


def test_markdown_heading_does_not_override_an_explicit_required_item():
    jd = '**Preferred Qualifications**\nPython (Required)'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability':'Python','jd_quote':jd}]
    plan['optional'] = []
    assert experiment.plan_issues(plan, [ROLE], jd) == []


@pytest.mark.parametrize('text', [
    'Experience with frameworks (e.g. Java, C#, ASP.NET Core and .NET 8).',
    'Experience with [e.g. Java, C++ and Python 3.11].',
    'Python (required), AWS (preferred).',
    'Java, Python and SQL preferred.',
])
def test_nested_examples_and_shared_lists_keep_their_original_text(text):
    clauses = experiment.jd_clauses(text)
    assert all(c in text for c in clauses)
    assert all(any(ch.isalnum() for ch in c) for c in clauses)
    if text.startswith('Experience') or text.startswith('Java,'):
        assert clauses == [text]
    else:
        assert clauses == ['Python (required)', 'AWS (preferred)']


@pytest.mark.parametrize('quote,required,preferred', [
    ('Direct MCP experience is required (approximately 1+ year preferred).', 'MCP', '1+ year'),
    ('Working knowledge of SQL (Postgres preferred), CI/CD pipelines, and Git-based development workflows.', 'SQL', 'Postgres'),
])
def test_parenthetical_preference_does_not_downgrade_base_requirement(quote, required, preferred):
    for label in (required, quote):
        plan = copy.deepcopy(PLAN)
        plan['required'] = [{'capability': label, 'jd_quote': quote}]
        plan['optional'] = [{'capability': preferred, 'jd_quote': quote}]
        assert experiment.plan_issues(plan, [ROLE], quote) == []
    plan['required'].append({'capability': preferred, 'jd_quote': quote})
    assert experiment.plan_issues(plan, [ROLE], quote) == []  # Classification labels do not block generation.


@pytest.mark.parametrize('modifier', ['preferred', 'strongly preferred', 'is highly preferred'])
def test_bare_parenthetical_preferred_still_qualifies_surrounding_skill(modifier):
    plan = copy.deepcopy(PLAN)
    quote = f'Experience with Python ({modifier}).'
    plan['required'] = [{'capability': 'Python', 'jd_quote': quote}]
    plan['optional'] = []
    assert experiment.plan_issues(plan, [ROLE], quote) == []  # Classification labels do not block generation.


def test_invalid_plan_is_not_used_for_bullet_generation(setup, monkeypatch):
    client, _ = setup
    bad = copy.deepcopy(PLAN)
    bad['required'][0]['jd_quote'] = 'Not in posting'
    monkeypatch.setattr(app, 'call_openai_structured_output', lambda **kwargs: copy.deepcopy(bad))
    response = client.post('/api/ai/jd-draft/plan', json={'job_description': JD})
    assert response.status_code == 422
    assert not app.jd_experiment_sessions


def test_expired_plan_cannot_generate(setup):
    client, calls = setup
    app.jd_experiment_sessions['expired'] = {'created_at': 0}
    assert client.post('/api/ai/jd-draft/generate', json={'plan_id': 'expired'}).status_code == 409
    assert not calls


@pytest.mark.parametrize('mode', ['professional', 'internship', 'coop', 'new_grad'])
def test_selected_mode_reaches_planning_repairs_drafting_and_review(setup, monkeypatch, mode):
    client, _ = setup
    calls, selected_modes = [], []
    def blueprints(**kwargs):
        selected_modes.append(kwargs['resume_mode'])
        return [copy.deepcopy(ROLE)]
    monkeypatch.setattr(app, 'current_experience_blueprints', blueprints)
    def generate(stage, schema, prompt, inputs):
        calls.append((stage, prompt, copy.deepcopy(inputs)))
        if stage == 'review':
            return {'summary': 'Check scope', 'ready_for_assumption_review': False, 'findings': []}
        if stage == 'targeting':
            return aligned_targeting(inputs)
        result = copy.deepcopy(PLAN if stage == 'plan' else DRAFT)
        if sum(s == stage for s, _, _ in calls) == 1:
            if stage == 'plan':
                result['required'][0]['jd_quote'] = 'Invalid quote triggers repair'
            else:
                result['experience']['mckinsey']['bullets'][0]['measurement']['value'] = '600'
        return result
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    planned = client.post('/api/ai/jd-draft/plan', json={'job_description': JD, 'resume_mode': mode})
    assert planned.status_code == 200, planned.json
    generated = client.post('/api/ai/jd-draft/generate', json={'plan_id': planned.json['plan_id'], 'resume_mode': mode})
    assert generated.status_code == 200, generated.json
    assert selected_modes == [mode]
    assert [stage for stage, _, _ in calls] == ['plan', 'plan', 'draft', 'draft', 'review']
    for _, prompt, inputs in calls:
        assert inputs['resume_mode_context'] == experiment.mode_context(mode)
        assert 'PRIVATE_' not in json.dumps(inputs)
    assert generated.json['resume_mode'] == mode
    assert '**Profile mode:** ' + experiment.mode_context(mode)['label'] in generated.json['markdown']


def test_student_modes_keep_mid_level_scope_and_new_grad_is_not_internship():
    for mode in ['internship', 'coop', 'new_grad']:
        rules = ' '.join(experiment.mode_context(mode)['writing_rules'])
        assert 'mid-level individual-contributor' in rules
        assert 'do not portray the candidate as a beginner' in rules
        assert 'Avoid senior, staff, principal' in rules
        assert 'Independent feature ownership' in rules
    assert 'Do not add Intern or Co-op unless the JD itself does' in ' '.join(experiment.mode_context('new_grad')['writing_rules'])


def test_changed_mode_or_legacy_plan_requires_replanning(setup):
    client, calls = setup
    planned = client.post('/api/ai/jd-draft/plan', json={'job_description': JD, 'resume_mode': 'professional'})
    plan_id = planned.json['plan_id']
    calls.clear()
    response = client.post('/api/ai/jd-draft/generate', json={'plan_id': plan_id, 'resume_mode': 'new_grad'})
    assert response.status_code == 409
    assert not calls
    del app.jd_experiment_sessions[plan_id]['resume_mode_context']
    assert client.post('/api/ai/jd-draft/generate', json={'plan_id': plan_id}).status_code == 409
    assert not calls


def test_versions_are_not_measurements_and_shortfall_is_advisory():
    draft = copy.deepcopy(DRAFT)
    b = draft['experience']['mckinsey']['bullets'][0]
    b.update(text='Implemented v1 and v2 API contracts with backward compatibility.')
    b['measurement'].update(kind='qualitative', status='qualitative', value='', unit='')
    issues, notes = experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)
    assert not issues and notes


def test_quantified_bullet_cannot_be_labelled_qualitative():
    draft = copy.deepcopy(DRAFT)
    draft['experience']['mckinsey']['bullets'][0]['measurement']['status'] = 'qualitative'
    issues, _ = experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)
    assert any('labelled illustrative' in issue for issue in issues)


def test_number_without_visible_support_is_rejected():
    draft = copy.deepcopy(DRAFT)
    draft['experience']['mckinsey']['bullets'][0]['measurement']['value'] = '600'
    assert experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)[0]


def test_illustrative_magnitude_matches_approximate_prose_without_changing_prose():
    draft = copy.deepcopy(DRAFT)
    b = draft['experience']['mckinsey']['bullets'][0]
    b['text'] = 'Reduced request processing time by approximately 30% through batching.'
    b['measurement'].update(kind='improvement', value='30', unit='percent')
    assert experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)[0] == []
    assert 'approximately' in b['text']


def test_illustrative_delta_requires_matching_arithmetic():
    draft = copy.deepcopy(DRAFT)
    b = draft['experience']['mckinsey']['bullets'][0]
    b['text'] = 'Reduced latency from approximately 2.4 seconds to approximately 0.8 seconds using query batching.'
    b['measurement'].update(kind='improvement', value='1.6', unit='seconds')
    assert experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)[0] == []
    b['measurement']['value'] = '1.7'
    assert experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)[0]


def test_operating_scope_counts_are_distinct_from_version_identifiers():
    for text in ['Implemented six testable stories.', 'Supported three API versions.', 'Enabled 4 incremental releases.', 'Migrated two major API families.']:
        assert app._numeric_tokens(text)
    assert not app._numeric_tokens('Implemented v1 and v2 with Java 17.')


def test_single_artifact_padding_is_demoted_without_inventing_a_measurement():
    draft = copy.deepcopy(DRAFT)
    b = draft['experience']['mckinsey']['bullets'][0]
    b['text'] = 'Delivered 1 responsive account component with version-aware error handling.'
    b['measurement'].update(kind='scale', value='1', unit='component delivered')
    result = experiment.normalize_draft(draft, app._numeric_tokens)
    normalized = result['experience']['mckinsey']['bullets'][0]
    assert normalized['text'].startswith('Delivered a responsive account component')
    assert normalized['measurement']['kind'] == 'qualitative'
    assert b['measurement']['kind'] == 'scale'
    assert experiment.draft_issues(result, PLAN, [ROLE], app._numeric_tokens)[0] == []


def test_typed_measurement_unit_does_not_depend_on_prose_noun_whitelist():
    draft = copy.deepcopy(DRAFT)
    b = draft['experience']['mckinsey']['bullets'][0]
    b['text'] = 'Built approximately 40 automated integration tests to check compatibility.'
    b['measurement'].update(kind='scale', value='40', unit='integration tests added')
    assert experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)[0] == []
    b['text'] = 'Implemented 4 responsive, accessible signup form components.'
    b['measurement'].update(value='4', unit='responsive form components')
    assert experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)[0] == []


def test_experimental_setting_persists_and_is_exposed_to_both_clients(setup, monkeypatch, tmp_path):
    client, _ = setup
    saved = []
    monkeypatch.setattr(app, 'save_settings', lambda data: saved.append(copy.deepcopy(data)))
    monkeypatch.setattr(app, 'get_pdf_conversion_status', lambda: (True, 'Ready'))
    monkeypatch.setattr(app, 'is_ai_generation_ready', lambda: (True, 'Ready'))
    response = client.post('/api/settings', json={'output_directory': str(tmp_path), 'experimental_jd_drafting': True})
    assert response.status_code == 200
    assert saved[-1]['experimental_jd_drafting'] is True
    assert client.get('/api/settings').json['experimental_jd_drafting'] is True
    assert client.get('/api/extension/status').json['experimental_jd_drafting'] is True


@pytest.mark.parametrize('mode', ['professional', 'internship', 'coop', 'new_grad'])
def test_normal_generation_uses_jd_only_and_normal_editor_versions(setup, monkeypatch, mode):
    client, calls = setup
    monkeypatch.setitem(app.settings, 'experimental_jd_drafting', False)
    monkeypatch.setattr(app, 'ai_session_active_blueprints', lambda session: [copy.deepcopy(ROLE)])
    app.ai_sessions['normal'] = {'job_description': JD, 'resume_mode': mode,
        'enabled_experience_keys': ['mckinsey'], 'analysis': {'target_role': 'Software Engineer'},
        'profile_snapshot': {'summary': 'PRIVATE_PROFILE', 'skills': ['PRIVATE_SKILL']},
        'revision_context': {'revision_request': 'Emphasize request handling', 'current_resume_content': 'PRIVATE_OLD_RESUME'}}
    response = client.post('/api/ai/generate-jd-resume', json={'session_id': 'normal', 'resume_mode': mode})
    assert response.status_code == 200, response.json
    data = response.json
    assert data['generation_method'] == 'jd_only'
    assert data['resume_mode'] == mode
    assert data['content'].startswith('Updated Title')
    assert 'Professional Experience' in data['content']
    assert set(data['resume_versions']) == {'original', 'luna_reviewed'}
    assert data['active_resume_version'] == 'luna_reviewed'
    assert data['audit_status'] == 'approved'
    assert data['audit_result']['assumptions_unverified'] is True
    serialized = json.dumps(calls)
    assert 'PRIVATE_' not in serialized
    for call in calls:
        inputs = json.loads(call['user_prompt'])
        assert inputs['resume_mode_context']['resume_mode'] == mode


def test_jd_only_retry_review_never_reintroduces_saved_evidence(setup):
    _, calls = setup
    resume = {'updated_title': 'Software Engineer', 'updated_summary': 'Application engineering',
              'updated_skills': DRAFT['skills'], 'experience': {'mckinsey': {'title': 'Software Engineer',
              'bullets': [DRAFT['experience']['mckinsey']['bullets'][0]['text']]}}}
    result = app.generate_resume_quality_audit(api_key='test', job_description=JD,
        analysis_payload={'_generation_method': 'jd_only', '_resume_mode': 'new_grad', '_jd_only_plan': PLAN},
        current_resume=resume, active_blueprints=[ROLE], candidate_profile={'summary': 'PRIVATE_PROFILE'})
    assert result['decision'] == 'approved'
    assert 'PRIVATE_' not in json.dumps(calls)
    assert json.loads(calls[0]['user_prompt'])['resume_mode_context']['resume_mode'] == 'new_grad'


def test_normal_versions_keep_original_and_reviewed_content_separate(setup, monkeypatch):
    client, _ = setup
    monkeypatch.setattr(app, 'ai_session_active_blueprints', lambda session: [copy.deepcopy(ROLE)])
    app.ai_sessions['normal'] = {'job_description': JD, 'resume_mode': 'professional',
        'analysis': {'_generation_method': 'jd_only'}, 'enabled_experience_keys': ['mckinsey'],
        'revision_context': {'revision_request': 'Clean status labels', 'current_resume_content': 'OLD_DRAFT_WITH_illustrative_unverified'}}
    seen = []
    def generate(stage, schema, prompt, inputs):
        seen.append(stage)
        if stage == 'review':
            assert 'current_proposed_resume' not in inputs
            assert 'requested_revision' not in inputs
            assert 'OLD_DRAFT_WITH_' not in json.dumps(inputs)
            assert 'illustrative_unverified' not in json.dumps(inputs['assembled_draft'])
        if stage == 'targeting':
            return aligned_targeting(inputs)
        if stage == 'plan':
            return copy.deepcopy(PLAN)
        if stage == 'review':
            bullet = copy.deepcopy(DRAFT['experience']['mckinsey']['bullets'][0])
            bullet['text'] = 'Validated 500 API requests using typed contracts and explicit error responses, checking malformed payloads at service boundaries to catch integration failures before deployment to shared environments.'
            return {'summary': 'Implementation wording corrected',
                    'findings': [{'target_id': 'bullet:mckinsey:1', 'severity': 'repair', 'issue': 'Clarify implementation', 'change_indices': [1]}],
                    'changes': [{'target': 'bullet', 'role_key': 'mckinsey', 'bullet_number': 1,
                                 'old_text': DRAFT['experience']['mckinsey']['bullets'][0]['text'], 'replacement': bullet}]}
        return copy.deepcopy(DRAFT)
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    response = client.post('/api/ai/generate-jd-resume', json={'session_id': 'normal'})
    assert response.status_code == 200, response.json
    versions = response.json['resume_versions']
    assert 'Implemented request validation' in versions['original']['resume_content']
    assert 'Validated 500 API requests' in versions['luna_reviewed']['resume_content']
    assert response.json['audit_status'] == 'approved'
    assert seen == ['plan', 'targeting', 'core', 'experience', 'review']


def test_review_outage_keeps_generated_resume_available(setup, monkeypatch):
    client, _ = setup
    monkeypatch.setattr(app, 'ai_session_active_blueprints', lambda session: [copy.deepcopy(ROLE)])
    app.ai_sessions['normal'] = {'job_description': JD, 'resume_mode': 'professional',
        'analysis': {}, 'enabled_experience_keys': ['mckinsey']}
    def generate(stage, schema, prompt, inputs):
        if stage == 'review':
            raise RuntimeError('Review unavailable')
        if stage == 'targeting':
            return aligned_targeting(inputs)
        return copy.deepcopy(PLAN if stage == 'plan' else DRAFT)
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    response = client.post('/api/ai/generate-jd-resume', json={'session_id': 'normal'})
    assert response.status_code == 200, response.json
    assert response.json['content'].startswith('Updated Title')
    assert response.json['audit_status'] == 'technical_failed'
    assert response.json['active_resume_version'] == 'original'
    assert set(response.json['resume_versions']) == {'original'}
    assert response.json['audit_result']['assumptions_unverified'] is True
    assert 'Review unavailable' in response.json['audit_result']['error']


def test_output_limit_is_retried_once_with_a_larger_budget(setup, monkeypatch):
    _, calls = setup
    def limited(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("OpenAI API returned no final output (status=incomplete, details={'reason': 'max_output_tokens'})")
        return copy.deepcopy(PLAN)
    monkeypatch.setattr(app, 'call_openai_structured_output', limited)
    assert app._jd_experiment_call('plan', experiment.plan_schema([ROLE]), experiment.PLAN_PROMPT,
                                    {'employment_headings_only': experiment.headings_only([ROLE])}) == PLAN
    assert len(calls) == 2
    assert calls[1]['max_output_tokens'] > calls[0]['max_output_tokens']
    assert calls[1]['user_prompt'] == calls[0]['user_prompt']


def test_persistent_output_limit_reports_the_real_stage_and_stops(setup, monkeypatch):
    _, calls = setup
    def limited(**kwargs):
        calls.append(kwargs)
        raise RuntimeError('max_output_tokens')
    monkeypatch.setattr(app, 'call_openai_structured_output', limited)
    with pytest.raises(app.AIStageError) as error:
        app._jd_experiment_call('draft', {}, experiment.DRAFT_PROMPT, {})
    assert error.value.stage == 'jd_draft'
    assert len(calls) == 2


def test_failed_writing_resumes_from_checked_plan_and_changed_mode_replans(setup, monkeypatch):
    _, _calls = setup
    events, seen = [], []
    fail_draft = True
    def generate(stage, schema, prompt, inputs):
        seen.append(stage)
        if stage == 'experience' and fail_draft:
            raise app.AIStageError('jd_draft', 'max_output_tokens')
        if stage == 'review':
            return {'summary': 'Reviewed', 'findings': [], 'ready_for_assumption_review': True}
        if stage == 'targeting':
            return aligned_targeting(inputs)
        return copy.deepcopy(PLAN if stage == 'plan' else DRAFT)
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    with pytest.raises(app.AIStageError):
        app.generate_jd_only_resume(JD, [ROLE], 'professional', checkpoint=lambda stage, state: events.append((stage, state)))
    assert [stage for stage, _ in events] == ['jd_plan', 'jd_targeting', 'jd_targeting', 'jd_core', 'jd_core', 'jd_experience']
    assert events[-1][1]['core_sections']['headline'] == DRAFT['headline']
    saved = events[-1][1]
    assert saved['plan'] == experiment.ensure_plan_titles(PLAN, [ROLE])
    fail_draft = False
    seen.clear()
    app.generate_jd_only_resume(JD, [ROLE], 'professional', saved_state=saved)
    assert seen == ['experience', 'review']
    seen.clear()
    app.generate_jd_only_resume(JD, [ROLE], 'new_grad', saved_state=saved)
    assert seen == ['plan', 'targeting', 'core', 'experience', 'review']


@pytest.mark.parametrize('field', ['headline', 'summary', 'skill', 'bullet'])
def test_internal_measurement_status_cannot_leak_into_resume_fields(field):
    draft = copy.deepcopy(DRAFT)
    if field == 'bullet':
        draft['experience']['mckinsey']['bullets'][0]['text'] = 'Handled an illustrative_unverified 500 requests using typed API contracts.'
    elif field == 'skill':
        draft['skills'][0]['items'][0] += ' illustrative_unverified'
    else:
        draft[field] += ' illustrative_unverified'
    issues, _ = experiment.draft_issues(draft, PLAN, [ROLE], app._numeric_tokens)
    assert any('metadata only' in issue for issue in issues)
    assert experiment.draft_issues(DRAFT, PLAN, [ROLE], app._numeric_tokens)[0] == []


def test_skills_use_conventional_names_rather_than_project_descriptions():
    draft = copy.deepcopy(DRAFT)
    draft['skills'][0]['items'] = ['Python integration adapters', 'Serverless / microservice adapters', 'Document embeddings for KB search']
    assert len(experiment.skill_style_notes(draft)) == 3
    assert experiment.resume_text_issues(draft) == []
    draft['skills'] = [{'category': 'Programming Languages', 'items': ['Python', 'Java']},
                       {'category': 'Tools & Platforms', 'items': ['Jira', 'Jira Service Management', 'Confluence']},
                       {'category': 'Backend Engineering', 'items': ['REST APIs', 'SCIM']},
                       {'category': 'DevOps & CI/CD', 'items': ['Git', 'CI/CD']}]
    assert experiment.resume_text_issues(draft) == []


def test_qualifications_under_experience_required_are_not_optional():
    jd = 'Experience Required: Strong Python development skills. Comfortable with Git environments. Cloud migration highly advantageous.'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': 'Python', 'jd_quote': 'Strong Python development skills.'}]
    plan['optional'] = [{'capability': 'Git', 'jd_quote': 'Comfortable with Git environments.'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []  # Classification labels do not block generation.
    plan['optional'] = [{'capability': 'Cloud migration', 'jd_quote': 'Cloud migration highly advantageous.'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []


def test_concatenated_jd_keeps_explicit_preferences_optional():
    jd = 'Experience Required: Strong Python development skillsCloud migration highly advantageousKnowledgeable in workflow design'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': 'Python', 'jd_quote': 'Strong Python development skills'}]
    plan['optional'] = [{'capability': 'Cloud migration', 'jd_quote': 'Cloud migration highly advantageous'}]
    assert experiment.plan_issues(plan, [ROLE], jd) == []
    assert experiment.plan_schema([ROLE])['properties']['engineering_focus']['minItems'] == 1


def test_normal_resume_formatter_also_rejects_leaked_status_labels():
    resume = {'updated_title': 'Software Engineer', 'updated_summary': 'Application engineering',
              'updated_skills': DRAFT['skills'], 'experience': {'mckinsey': {'title': 'Software Engineer',
              'bullets': ['Reduced workflow exceptions by an illustrative_unverified 37%.']}}}
    with pytest.raises(ValueError, match='internal measurement/review status'):
        app.format_generated_resume_text(resume, [ROLE])


def test_quote_schema_selects_actual_clauses_from_joined_job_site_text():
    jd = 'Required Technical SkillsStrong experience with C#, Python and API’s. Mobile application development is a plus.Use of Hangfire is nice to have.Required QualificationsHands-on production software experience.'
    clauses = experiment.jd_clauses(jd)
    assert 'required' not in experiment.plan_schema([ROLE], jd)['properties']
    assert list(experiment.jd_clause_map(jd).values()) == clauses
    assert all(clause in jd for clause in clauses)
    assert 'Mobile application development is a plus.' in clauses
    assert 'Use of Hangfire is nice to have.' in clauses
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': 'Python and APIs', 'jd_quote': clauses[0]}]
    plan['optional'] = [{'capability': 'Mobile application development', 'jd_quote': clauses[1]}]
    normalized = experiment.normalize_plan(plan, jd)
    assert experiment.plan_issues(normalized, [ROLE], jd) == []
    assert normalized['required'][0]['jd_quote'] == clauses[0]
    plan['required'] = [plan['optional'][0]]
    assert experiment.plan_issues(plan, [ROLE], jd) == []  # Classification labels do not block generation.


def test_typography_normalization_preserves_csharp_and_the_actual_source_quote():
    jd = 'Use C# and API’s for hands‑on development.'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': 'C# APIs', 'jd_quote': "Use C# and API's for hands-on development."}]
    plan['optional'] = []
    result = experiment.normalize_plan(plan, jd)
    assert result['required'][0]['jd_quote'] == jd
    assert 'C#' in result['required'][0]['capability']
    assert experiment.plan_issues(result, [ROLE], jd) == []


def test_source_reference_resolves_quote_without_model_copying_jd_punctuation():
    jd = 'Build software with C#, dot-net and API’s. Use of Hangfire is nice to have.'
    plan = copy.deepcopy(PLAN)
    plan['required'] = [{'capability': '.NET APIs', 'source_clause_id': 'jd_1'}]
    plan['optional'] = [{'capability': 'Hangfire', 'source_clause_id': 'jd_2'}]
    result = experiment.normalize_plan(plan, jd)
    assert result['required'][0]['jd_quote'] == experiment.jd_clauses(jd)[0]
    assert experiment.plan_issues(result, [ROLE], jd) == []


def test_valid_slash_separated_skills_are_formatted_without_failure():
    draft = copy.deepcopy(DRAFT)
    draft['skills'] = [{'category': 'Backend Engineering', 'items': ['OAuth2 / JWT', 'ETL / batch ingestion', 'CI/CD', 'TCP/IP']}]
    normalized = experiment.normalize_draft(draft, app._numeric_tokens)
    assert normalized['skills'][0]['items'] == ['OAuth2', 'JWT', 'ETL', 'batch ingestion', 'CI/CD', 'TCP/IP']
    assert experiment.draft_issues(normalized, PLAN, [ROLE], app._numeric_tokens)[0] == []


def test_numerical_goal_shortfall_does_not_trigger_another_full_draft_call(setup, monkeypatch):
    stages = []
    def generate(stage, schema, prompt, inputs):
        stages.append(stage)
        if stage == 'targeting':
            return aligned_targeting(inputs)
        if stage == 'plan':
            return copy.deepcopy(PLAN)
        if stage == 'review':
            return {'summary': 'Writing review complete', 'findings': [], 'ready_for_assumption_review': True}
        draft = copy.deepcopy(DRAFT)
        b = draft['experience']['mckinsey']['bullets'][0]
        b['text'] = 'Implemented request validation using typed API contracts and explicit error responses, preventing malformed payloads from reaching service handlers and making integration failures easier to diagnose during testing.'
        b['measurement'].update(kind='qualitative', status='qualitative', value='', unit='')
        return draft
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], 'professional')
    assert stages == ['plan', 'targeting', 'core', 'experience', 'review']
    assert result['audit']['non_blocking_gaps']


def test_single_schema_count_is_not_measurement_padding():
    draft = copy.deepcopy(DRAFT)
    bullet = draft['experience']['mckinsey']['bullets'][0]
    bullet['text'] = 'Modelled asset relationships and automated inventory imports for one CMDB schema.'
    bullet['measurement'].update(kind='scale', value='1', unit='schema')
    result = experiment.normalize_draft(draft, app._numeric_tokens)
    assert 'for a CMDB schema' in result['experience']['mckinsey']['bullets'][0]['text']
    assert result['experience']['mckinsey']['bullets'][0]['measurement']['kind'] == 'qualitative'


@pytest.mark.parametrize('value,unit', [('1', 'ingestion pipeline'), ('1', 'runbook collection'), ('multiple', 'REST endpoints'), ('N/A', '')])
def test_invisible_measurements_are_demoted_without_changing_sentence(value, unit):
    draft = copy.deepcopy(DRAFT)
    bullet = draft['experience']['mckinsey']['bullets'][0]
    bullet['text'] = 'Built a batch ingestion pipeline with schema validation and monitoring alerts.'
    bullet['measurement'].update(kind='scale', value=value, unit=unit)
    result = experiment.normalize_draft(draft, app._numeric_tokens)
    normalized = result['experience']['mckinsey']['bullets'][0]
    assert normalized['text'] == bullet['text']
    assert normalized['measurement']['kind'] == 'qualitative'
    assert normalized['measurement']['value'] == normalized['measurement']['unit'] == ''
    assert experiment.draft_issues(result, PLAN, [ROLE], app._numeric_tokens)[0] == []
    assert bullet['measurement']['value'] == value


def test_normalization_preserves_real_measurement_conflicts_for_repair():
    draft = copy.deepcopy(DRAFT)
    draft['experience']['mckinsey']['bullets'][0]['measurement']['value'] = '600'
    result = experiment.normalize_draft(draft, app._numeric_tokens)
    assert experiment.draft_issues(result, PLAN, [ROLE], app._numeric_tokens)[0]


def test_partial_repairs_change_only_addressed_content():
    draft = copy.deepcopy(DRAFT)
    draft['summary'] = 'Builds APIs. Writes tests. Ships features.'
    bullet = copy.deepcopy(draft['experience']['mckinsey']['bullets'][0])
    bullet['text'] = 'Validated 500 requests with typed contracts and explicit error responses.'
    result = experiment.apply_repairs(draft, {'changes': [
        {'target': 'headline', 'old_text': draft['headline'], 'replacement': 'Backend Engineer'},
        {'target': 'summary', 'old_text': 'Writes tests.', 'replacement': 'Automates integration tests.'},
        {'target': 'bullet', 'role_key': 'mckinsey', 'bullet_number': 1,
         'old_text': draft['experience']['mckinsey']['bullets'][0]['text'], 'replacement': bullet},
    ]})
    assert result['headline'] == 'Backend Engineer'
    assert result['summary'] == 'Builds APIs. Automates integration tests. Ships features.'
    assert result['skills'] == draft['skills']
    assert result['experience']['mckinsey']['bullets'] == [bullet]
    assert draft['headline'] == DRAFT['headline']
    assert draft['experience'] == DRAFT['experience']
    assert experiment.apply_repairs(draft, {'changes': []}) == draft


def test_partial_skill_repair_preserves_other_groups():
    draft = copy.deepcopy(DRAFT)
    draft['skills'].append({'category': 'Programming Languages', 'items': ['Python', 'Java']})
    result = experiment.apply_repairs(draft, {'changes': [{
        'target': 'skills', 'group_number': 1, 'expected_category': 'Backend Engineering',
        'category': 'Backend Engineering', 'items': ['REST APIs', 'API versioning']}]})
    assert result['skills'][1] == draft['skills'][1]
    assert result['experience'] == draft['experience']
    assert result['summary'] == draft['summary']


@pytest.mark.parametrize('changes', [
    [{'target': 'headline', 'old_text': 'Stale title', 'replacement': 'Engineer'}],
    [{'target': 'summary', 'old_text': 'Absent sentence', 'replacement': 'New sentence'}],
    [{'target': 'summary', 'old_text': 'software engineering', 'replacement': 'engineering'},
     {'target': 'summary', 'old_text': 'engineering experience', 'replacement': 'delivery'}],
    [{'target': 'headline', 'old_text': DRAFT['headline'], 'replacement': 'Engineer'}] * 2,
    [{'target': 'bullet', 'role_key': 'missing', 'bullet_number': 1,
      'old_text': 'Old', 'replacement': {}}],
    [{'target': 'skills', 'group_number': 8, 'expected_category': 'Backend Engineering',
      'category': 'Backend Engineering', 'items': ['REST APIs', 'API versioning']}],
])
def test_invalid_partial_repairs_are_atomic(changes):
    draft = copy.deepcopy(DRAFT)
    before = copy.deepcopy(draft)
    with pytest.raises(ValueError):
        experiment.apply_repairs(draft, {'changes': changes})
    assert draft == before


def test_generation_validation_repair_returns_one_bullet_not_a_resume(setup, monkeypatch):
    stages = []
    def generate(stage, schema, prompt, inputs):
        stages.append(stage)
        if stage == 'targeting':
            return aligned_targeting(inputs)
        if stage == 'plan':
            return copy.deepcopy(PLAN)
        if stage == 'core':
            return copy.deepcopy(DRAFT)
        if stage == 'experience':
            bad = copy.deepcopy(DRAFT)
            bad['experience']['mckinsey']['bullets'][0]['measurement']['value'] = '600'
            return bad
        if stage == 'repair':
            assert 'previous_draft' not in inputs
            assert inputs['repair_issues']
            assert 'resume_mode_context' in inputs
            assert list(schema['properties']) == ['changes']
            b = inputs['current_draft']['experience']['mckinsey']['bullets'][0]
            return {'changes': [{'target': 'bullet', 'role_key': 'mckinsey', 'bullet_number': 1,
                                 'old_text': b['text'], 'replacement': copy.deepcopy(DRAFT['experience']['mckinsey']['bullets'][0])}]}
        return {'findings': [], 'summary': 'Reviewed', 'ready_for_assumption_review': True}
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], 'professional')
    assert stages == ['plan', 'targeting', 'core', 'experience', 'repair', 'review']
    assert result['resume']['updated_summary'] == DRAFT['summary']
    assert result['resume']['experience']['mckinsey']['bullets'] == [DRAFT['experience']['mckinsey']['bullets'][0]['text']]


def test_invalid_review_patch_preserves_original_resume(setup, monkeypatch):
    stages = []
    def generate(stage, schema, prompt, inputs):
        stages.append(stage)
        if stage == 'targeting':
            return aligned_targeting(inputs)
        if stage == 'plan':
            return copy.deepcopy(PLAN)
        if stage in {'core', 'experience'}:
            return copy.deepcopy(DRAFT)
        if stage == 'review':
            return {'summary': 'Change title',
                    'findings': [{'target_id': 'headline', 'severity': 'repair', 'issue': 'Change title', 'change_indices': [1]}],
                    'changes': [{'target': 'headline', 'old_text': 'Wrong original', 'replacement': 'New title'}]}
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], 'professional')
    assert stages == ['plan', 'targeting', 'core', 'experience', 'review']
    assert result['resume'] == result['original_resume']
    assert result['resume']['updated_title'] == DRAFT['headline']


@pytest.mark.parametrize('mode', ['professional', 'new_grad', 'internship', 'coop'])
def test_grouped_writing_uses_shared_plan_and_core_handoff(setup, monkeypatch, mode):
    calls = []
    def generate(stage, schema, prompt, inputs):
        calls.append((stage, copy.deepcopy(inputs)))
        if stage == 'targeting':
            return aligned_targeting(inputs)
        if stage == 'plan':
            return copy.deepcopy(PLAN)
        if stage in {'core', 'experience'}:
            assert inputs['checked_plan'] == experiment.ensure_plan_titles(PLAN, [ROLE])
            assert inputs['resume_mode_context'] == experiment.mode_context(mode)
            assert 'PRIVATE_' not in json.dumps(inputs)
            assert '80%' in prompt
            if stage == 'core':
                assert set(schema['properties']) == {'headline', 'summary', 'skills'}
                return {k: copy.deepcopy(DRAFT[k]) for k in ('headline', 'summary', 'skills')}
            assert set(schema['properties']) == {'experience'}
            assert 'work | outcome | measurement' in prompt
            assert inputs['core_sections'] == {k: DRAFT[k] for k in ('headline', 'summary', 'skills')}
            assert 'checked plan controls' in prompt
            # Even an unexpected extra field from a test double cannot replace core.
            return {'experience': copy.deepcopy(DRAFT['experience']), 'headline': 'Unwanted overwrite'}
        return {'summary': 'Reviewed', 'findings': [], 'ready_for_assumption_review': True}
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], mode)
    assert [stage for stage, _ in calls] == ['plan', 'targeting', 'core', 'experience', 'review']
    assert result['resume']['updated_title'] == DRAFT['headline']
    assert result['resume']['experience']['mckinsey']['bullets'] == [DRAFT['experience']['mckinsey']['bullets'][0]['text']]


def test_restored_skills_use_role_categories_and_compact_items(setup, monkeypatch):
    ordered = app.skill_category_order_for_key('backend_application')
    def generate(stage, schema, prompt, inputs):
        if stage == 'targeting':
            return aligned_targeting(inputs)
        if stage == 'plan':
            return copy.deepcopy(PLAN)
        if stage == 'core':
            assert inputs['ordered_skill_categories'] == ordered
            group = schema['properties']['skills']['items']['properties']
            assert group['category']['enum'] == sorted(ordered)
            assert group['items']['maxItems'] == 5
            assert 'Do not fill every allowed category' in prompt
            assert 'Build a substantial' not in prompt
            result = copy.deepcopy(DRAFT)
            result['skills'] = [
                {'category': 'Backend Engineering', 'items': ['Spring Boot', 'REST APIs']},
                {'category': 'Process & Requirements', 'items': ['Agile', 'Scrum']},
                {'category': 'Programming Languages', 'items': ['Java', 'SQL']},
            ]
            return result
        if stage == 'experience':
            assert [g['category'] for g in inputs['core_sections']['skills']] == ['Programming Languages', 'Backend Engineering']
            return copy.deepcopy(DRAFT)
        return {'summary': 'Reviewed', 'findings': [], 'ready_for_assumption_review': True}
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], 'professional', skill_order_key='backend_application')
    assert [g['category'] for g in result['resume']['updated_skills']] == ['Programming Languages', 'Backend Engineering']
    patches = experiment.repair_schema([ROLE], ordered)['properties']['changes']['items']['anyOf']
    skill_patch = next(p for p in patches if p['properties']['target']['enum'] == ['skills'])
    assert skill_patch['properties']['items']['maxItems'] == 5


def test_review_target_ids_are_explicit_and_resolve_to_correct_bullet():
    draft = copy.deepcopy(DRAFT)
    second = copy.deepcopy(draft['experience']['mckinsey']['bullets'][0])
    second.update(text='Integrated Azure Service Bus with bounded retries.', contribution_number=2)
    draft['experience']['mckinsey']['bullets'].append(second)
    targets = experiment.review_targets(draft)
    assert targets['bullet:mckinsey:2'] == second['text']
    schema = experiment.review_schema(draft)
    assert 'bullet:mckinsey:2' in schema['properties']['findings']['items']['properties']['target_id']['enum']
    result = experiment.identify_findings({'findings': [{'target_id': 'bullet:mckinsey:2', 'severity': 'repair', 'issue': 'Clarify delivery'}]}, draft)
    assert result['findings'][0]['bullet_number'] == 2
    assert result['findings'][0]['current_text'] == second['text']


def test_every_finding_requires_a_linked_disposition():
    findings = experiment.identify_findings({'findings': [
        {'target_id': 'headline', 'severity': 'repair', 'issue': 'Simplify title'},
        {'target_id': 'summary', 'severity': 'repair', 'issue': 'Remove irrelevant AI claim'},
    ]}, DRAFT)['findings']
    patch = {'changes': [{'target': 'headline', 'old_text': DRAFT['headline'], 'replacement': 'Backend Engineer'}],
             'dispositions': [{'finding_id': findings[0]['finding_id'], 'status': 'patched', 'change_indices': [1], 'reason': 'Simplified'}]}
    with pytest.raises(ValueError, match='omitted'):
        experiment.validate_dispositions(patch, findings)
    patch['dispositions'].append({'finding_id': findings[1]['finding_id'], 'status': 'unchanged', 'change_indices': [], 'reason': 'Current wording already describes backend work'})
    experiment.validate_dispositions(patch, findings)
    patch['dispositions'][1].update(status='patched', change_indices=[1])
    with pytest.raises(ValueError, match='target'):
        experiment.validate_dispositions(patch, findings)


@pytest.mark.parametrize('severity, decision', [('repair', 'approved'), ('advisory', 'approved'), ('factual_blocker', 'manual_attention')])
def test_reviewer_supplies_exact_changes_and_code_applies_without_more_calls(setup, monkeypatch, severity, decision):
    stages, checkpoints = [], []
    def generate(stage, schema, prompt, inputs):
        stages.append(stage)
        if stage == 'targeting':
            return aligned_targeting(inputs)
        if stage == 'plan':
            return copy.deepcopy(PLAN)
        if stage in {'core', 'experience'}:
            return copy.deepcopy(DRAFT)
        assert stage == 'review'
        assert 'change_indices' not in json.dumps(schema)
        assert inputs['review_items']['titles'][0] == {'tid': 1, 'text': DRAFT['headline'], 'scope': 'main'}
        return {'snapshot_id': inputs['snapshot_id'], 'review_summary': 'Review complete',
                'titles': [{'tid': 1, 'replacement': 'Backend Engineer', 'reason': 'Standard positioning'}] if severity == 'repair' else [],
                'summaries': [], 'skills': [], 'bullets': [],
                'notes': [] if severity == 'repair' else [{'tid': 1, 'severity': severity, 'issue': 'Standard positioning'}]}
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], 'professional', checkpoint=lambda stage,state: checkpoints.append(copy.deepcopy(state)))
    assert stages == ['plan', 'targeting', 'core', 'experience', 'review']
    assert result['audit']['decision'] == decision
    assert result['resume']['updated_title'] == ('Backend Engineer' if severity == 'repair' else DRAFT['headline'])
    assert result['resume']['updated_summary'] == DRAFT['summary']
    assert result['resume']['experience']['mckinsey']['bullets'] == [DRAFT['experience']['mckinsey']['bullets'][0]['text']]
    assert checkpoints[-1]['review_rounds'][0]['application'] == 'locally_validated'


def test_prose_only_review_request_is_not_mistaken_for_an_applied_fix(setup, monkeypatch):
    def generate(stage, schema, prompt, inputs):
        if stage == 'targeting':
            return aligned_targeting(inputs)
        if stage == 'plan': return copy.deepcopy(PLAN)
        if stage in {'core', 'experience'}: return copy.deepcopy(DRAFT)
        return {'summary': 'Fix title', 'findings': [{'target_id': 'headline', 'severity': 'repair', 'issue': 'Change title', 'change_indices': []}], 'changes': []}
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], 'professional')
    assert result['audit']['decision'] == 'technical_failed'
    assert result['resume'] == result['original_resume']


@pytest.mark.parametrize('mode', ['professional', 'new_grad', 'internship', 'coop'])
def test_compact_structured_plan_reaches_all_downstream_stages(setup, monkeypatch, mode):
    raw = {'role_positioning': 'Software Engineer', 'engineering_focus': ['Application APIs'],
           'experience': copy.deepcopy(PLAN['experience'])}
    note = {'work': 'Implement typed request validation', 'outcome': 'Reject malformed payloads',
            'measurement': 'Malformed requests rejected (%)'}
    raw['experience']['mckinsey']['contributions'] = [note]
    expected = experiment.ensure_plan_titles(experiment.normalize_plan(raw, JD), [ROLE])
    assert experiment.plan_issues(expected, [ROLE], JD) == []
    assert raw['experience']['mckinsey']['contributions'] == [note]
    stages = []

    def generate(stage, schema, prompt, inputs):
        stages.append(stage)
        if stage == 'plan':
            assert 'required' not in schema['properties']
            assert 'optional' not in schema['properties']
            assert 'contributions' not in schema['properties']['experience']['properties']['mckinsey']['properties']
            return copy.deepcopy(raw)
        if stage == 'targeting':
            assert inputs['proposed_plan'] == expected
            assert 'PROJECT CONTEXT' in prompt
            return aligned_targeting(inputs)
        assert inputs['checked_plan'] == expected
        assert expected['experience']['mckinsey']['contributions'] == [
            'Implement typed request validation | Reject malformed payloads | Malformed requests rejected (%)']
        assert 'PROJECT CONTEXT' in prompt
        if stage == 'core':
            return {key: copy.deepcopy(DRAFT[key]) for key in ('headline', 'summary', 'skills')}
        if stage == 'experience':
            return {'experience': copy.deepcopy(DRAFT['experience'])}
        return {'summary': 'Reviewed', 'findings': [], 'ready_for_assumption_review': True}

    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], mode)
    assert stages == ['plan', 'targeting', 'core', 'experience', 'review']
    assert result['resume']['experience']['mckinsey']['bullets'] == [DRAFT['experience']['mckinsey']['bullets'][0]['text']]


def test_planning_preserves_full_jd_while_targeting_receives_clauses(setup, monkeypatch):
    captured = []
    def capture(**kwargs):
        captured.append(json.loads(kwargs['user_prompt']))
        return copy.deepcopy(PLAN)
    monkeypatch.setattr(app, 'call_openai_structured_output', capture)
    inputs = {'job_description': JD, 'employment_headings_only': experiment.headings_only([ROLE])}
    app._jd_experiment_call('plan', experiment.plan_schema([ROLE]), experiment.PLAN_PROMPT, inputs)
    assert captured[-1] == inputs
    app._jd_experiment_call('targeting', {}, experiment.TARGETING_PROMPT, inputs)
    assert 'job_description' not in captured[-1]
    assert captured[-1]['job_description_clauses'] == experiment.jd_clause_map(JD)
    assert inputs['job_description'] == JD


@pytest.mark.parametrize('mode', ['professional', 'new_grad', 'internship', 'coop'])
def test_project_only_plan_lets_writer_choose_contributions_without_extra_calls(setup, monkeypatch, mode):
    plan = {'role_positioning': 'Software Engineer', 'engineering_focus': ['Application APIs'],
            'experience': copy.deepcopy(PLAN['experience'])}
    plan['experience']['mckinsey'].pop('contributions')
    expected = experiment.ensure_plan_titles(plan, [ROLE])
    assert experiment.normalize_plan(plan, JD) == plan
    assert experiment.plan_issues(plan, [ROLE], JD) == []
    stages = []
    def generate(stage, schema, prompt, inputs):
        stages.append(stage)
        assert experiment.CAREER_SCOPE_POLICY in prompt
        if stage == 'plan':
            assert 'contributions' not in schema['properties']['experience']['properties']['mckinsey']['properties']
            return copy.deepcopy(plan)
        if stage == 'targeting':
            assert inputs['proposed_plan'] == expected
            variants = schema['properties']['corrections']['items']['anyOf']
            assert not any(v['properties']['target']['enum'] == ['contribution'] for v in variants)
            assert variants[0]['properties']['target']['enum'] == ['role_positioning']
            return aligned_targeting(inputs)
        assert inputs['checked_plan'] == expected
        assert 'contributions' not in inputs['checked_plan']['experience']['mckinsey']
        if stage == 'core':
            return {key: copy.deepcopy(DRAFT[key]) for key in ('headline', 'summary', 'skills')}
        if stage == 'experience':
            assert 'choose distinct important engineering contributions' in prompt
            assert 'measurement.value' in prompt
            return {'experience': copy.deepcopy(DRAFT['experience'])}
        return {'summary': 'Reviewed', 'findings': [], 'ready_for_assumption_review': True}
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(JD, [ROLE], mode)
    assert stages == ['plan', 'targeting', 'core', 'experience', 'review']
    assert result['resume']['experience']['mckinsey']['bullets'] == [DRAFT['experience']['mckinsey']['bullets'][0]['text']]

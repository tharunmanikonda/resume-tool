"""Replay production failures without API requests or changes to saved resumes."""
import copy
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import app
import jd_draft_experiment as experiment

FIXTURES = Path(__file__).parent / 'fixtures'
PRIORITY_CASES = json.loads((FIXTURES / 'generation_priority_failures_2026_10_28.json').read_text())
ROLE = {'key': 'recent', 'company': 'Example', 'default_title': 'Engineer',
        'dates': '2024 - Present', 'location': 'Remote', 'bullet_min': 1, 'bullet_max': 1}
VALID_TEXT = ('Implemented request validation for 500 requests using typed API contracts and explicit error responses, '
              'preventing malformed payloads from reaching service handlers during integration testing and release validation.')
BULLET = {'text': VALID_TEXT, 'contribution_number': 1, 'measurement': {
    'kind': 'scale', 'value': '500', 'unit': 'requests', 'context': 'Proposed test workload', 'status': 'illustrative_unverified'}}


def base_plan():
    return {'role_positioning': 'Engineer', 'target_system': 'API service', 'target_workflow': 'Validate requests',
            'required': [], 'optional': [], 'unknowns': ['Product'], 'experience': {'recent': {
                'system': 'API service', 'workflow': 'Validate requests', 'scope': 'Module implementation',
                'assumptions': ['Proposed service'], 'contributions': ['Validate requests | typed contracts | clear errors | workload']}}}


@pytest.mark.parametrize('case', PRIORITY_CASES, ids=lambda case: case['name'])
def test_latest_failed_plans_no_longer_block_on_classification(case):
    plan = base_plan()
    plan.update(required=copy.deepcopy(case['required']), optional=copy.deepcopy(case['optional']))
    normalized = experiment.normalize_plan(plan, case['jd'])
    assert experiment.plan_issues(normalized, [ROLE], case['jd']) == []
    assert normalized['experience'] == plan['experience']
    for level in ('required', 'optional'):
        assert [r['capability'] for r in normalized[level]] == [r['capability'] for r in plan[level]]


def test_unanchored_quote_still_rejected_without_priority_checker():
    jd = 'Required Qualifications Build APIs. Preferred Qualifications Build Kubernetes tools.'
    plan = base_plan()
    plan['required'] = [{'capability': 'APIs', 'jd_quote': 'Not in this JD'}]
    assert experiment.plan_issues(experiment.normalize_plan(plan, jd), [ROLE], jd)


@pytest.mark.parametrize('case', json.loads((FIXTURES / 'stale_bullet_repair_2026_10_28.json').read_text()))
def test_real_paraphrased_old_text_cannot_satisfy_new_patch_schema(case):
    change = case['change'];role = {**ROLE, 'key': change['role_key']}
    bullets = [copy.deepcopy(case['actual']) for _ in range(change['bullet_number'])]
    draft = {'headline': 'Engineer', 'summary': 'Builds APIs.', 'skills': [],
             'experience': {role['key']: {'bullets': bullets}}}
    schema = experiment.repair_schema([role], current_draft=draft)
    Draft202012Validator.check_schema(schema)
    candidate = copy.deepcopy(change)
    candidate['replacement'] = copy.deepcopy(BULLET)
    candidate['replacement']['contribution_number'] = change['bullet_number']
    assert not Draft202012Validator(schema).is_valid({'changes': [candidate]})
    fixed = copy.deepcopy(candidate)
    fixed['old_text'] = case['actual']['text']
    fixed['replacement'] = copy.deepcopy(BULLET)
    fixed['replacement']['contribution_number'] = change['bullet_number']
    assert Draft202012Validator(schema).is_valid({'changes': [fixed]})
    patched = experiment.apply_repairs(draft, {'changes': [fixed]})
    assert patched['experience'][role['key']]['bullets'][change['bullet_number'] - 1] == fixed['replacement']
    assert draft['experience'][role['key']]['bullets'] == bullets
    with pytest.raises(ValueError, match='stale'):
        experiment.apply_repairs(draft, {'changes': [change]})


@pytest.mark.parametrize('length', [24, 25, 30, 31])
def test_writer_and_review_replacement_schema_enforce_same_word_rule(length):
    draft = {'headline': 'Engineer', 'summary': 'Builds APIs.', 'skills': [],
             'experience': {'recent': {'bullets': [BULLET]}}}
    text = ' '.join(['word'] * length)
    schemas = [experiment.experience_schema([ROLE]), experiment.repair_schema([ROLE], current_draft=draft),
               experiment.review_apply_schema([ROLE], draft)]
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
        patterns = re.findall(r'"pattern": "(.*?)"', json.dumps(schema))
        assert patterns
        for encoded in patterns:
            pattern = json.loads('"'+encoded+'"')
            assert bool(re.fullmatch(pattern, text)) == (25 <= length <= 30)


def test_migrated_failed_plan_skips_another_planning_call(monkeypatch):
    case = next(case for case in PRIORITY_CASES if case['name'] == 'Atlassian')
    jd = case['jd']
    plan = base_plan()
    plan.update(required=case['required'], optional=case['optional'])
    inputs = {'job_description': jd, 'employment_headings_only': experiment.headings_only([ROLE]),
              'resume_mode_context': experiment.mode_context('professional')}
    legacy_fingerprint = app.canonical_json_hash({'workflow_version': 5, 'jd_source_version': 4,
        'writing_policy_version': experiment.WRITING_POLICY_VERSION, 'inputs': inputs, 'skill_order_key': None})
    saved = {'fingerprint': legacy_fingerprint, 'pending_plan': plan}
    stages, checkpoints = [], []

    def generate(stage, schema, prompt, supplied):
        stages.append(stage)
        assert stage != 'plan', 'A completed planning call must not run again for a priority correction.'
        if stage == 'targeting':
            return {'decision': 'aligned', 'corrections': [], 'assessment': {
                'level_scope': 'Feature implementation', 'team_path': 'Application engineering',
                'choice_basis': 'conservative_assumption',
                'primary_focus': [{'source_clause_id': next(iter(experiment.jd_clause_map(jd))), 'focus': 'Build product features'}],
                'secondary_focus': [], 'excluded_paths': [], 'rationale': 'Target the required engineering work'}}
        if stage == 'core':
            return {'headline': 'Software Engineer', 'summary': 'Builds application features.',
                    'skills': [{'category': 'Backend Engineering', 'items': ['REST APIs', 'Request validation']}]}
        if stage == 'experience':
            return {'experience': {'recent': {'bullets': [copy.deepcopy(BULLET)]}}}
        if stage == 'review':
            return {'summary': 'Reviewed', 'findings': [], 'changes': []}
        pytest.fail('Unexpected call: '+stage)

    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(jd, [ROLE], 'professional', saved_state=saved,
        checkpoint=lambda stage, state: checkpoints.append(copy.deepcopy(state)))
    assert stages == ['targeting', 'core', 'experience', 'review']
    assert result['resume']['experience']['recent']['bullets'] == [VALID_TEXT]
    assert 'priority_corrections' not in checkpoints[-1]
    assert saved == {'fingerprint': legacy_fingerprint, 'pending_plan': plan}


def test_pdf_keeps_numerical_goal_advisory_instead_of_new_export_block(monkeypatch):
    # The writing/review pipeline already reports numerical_goal_notes. PDF
    # export must not turn that goal into an unrelated hard failure afterward.
    qualitative = VALID_TEXT.replace('500 requests', 'incoming requests')
    resume = {'experience': [{'company': 'Example', 'bullets': [VALID_TEXT, VALID_TEXT, qualitative]}]}
    assert experiment.bullet_writing_issues(resume) == []
    assert experiment.bullet_writing_issues(resume, app._numeric_tokens)
    monkeypatch.setattr(app, 'draft_resume_snapshot', lambda draft: resume)
    monkeypatch.setattr(app, 'validate_updated_content', lambda text: (['stop before filesystem writes'], []))
    draft = {'audit_status': 'approved', 'status': 'ready', 'resume_content': 'Generated content',
             'analysis': {'_generation_method': 'jd_only'}}
    with pytest.raises(ValueError, match='Validation failed: stop before filesystem writes'):
        app.generate_extension_pdf(draft)


@pytest.mark.parametrize('fits_story', [True, False])
def test_preferred_use_is_applied_when_fitting_and_omitted_without_extra_calls(monkeypatch, fits_story):
    jd = 'Build Python APIs. Snowflake experience is a plus.'
    plan = base_plan()
    plan['required'] = [{'capability': 'Python APIs', 'jd_quote': 'Build Python APIs.'}]
    plan['optional'] = [{'capability': 'Snowflake', 'jd_quote': 'Snowflake experience is a plus.'}]
    if fits_story:
        plan['target_workflow'] = plan['experience']['recent']['workflow'] = 'Deliver reporting data'
    original = plan['experience']['recent']['contributions'][0]
    replacement = 'Build Python reporting endpoint | query Snowflake reporting data | serve report results | response latency (ms)'
    stages = []

    def generate(stage, schema, prompt, supplied):
        stages.append(stage)
        if stage == 'plan':
            return copy.deepcopy(plan)
        if stage == 'targeting':
            return {'decision': 'corrected' if fits_story else 'aligned',
                    'corrections': [{'target': 'contribution', 'role_key': 'recent', 'contribution_number': 1,
                        'old_text': original, 'replacement': replacement}] if fits_story else [],
                    'assessment': {'level_scope': 'Implementation', 'team_path': 'Python APIs',
                        'choice_basis': 'explicit_jd_scope',
                        'primary_focus': [{'source_clause_id': 'jd_1', 'focus': 'Build Python APIs'}],
                        'secondary_focus': [], 'excluded_paths': [] if fits_story else ['Unrelated data warehouse work'],
                        'rationale': 'Preserve the existing workflow'}}
        if stage in {'core', 'experience'}:
            note = supplied['checked_plan']['experience']['recent']['contributions'][0]
            assert ('Snowflake' in note) == fits_story
            if stage == 'core':
                return {'headline': 'Software Engineer', 'summary': 'Builds Python APIs.',
                        'skills': [{'category': 'Backend Engineering', 'items': ['REST APIs', 'Request validation']}]}
            bullet = copy.deepcopy(BULLET)
            if fits_story:
                bullet['text'] = ('Built Python reporting APIs that query Snowflake datasets, validating request parameters and '
                                  'response schemas across 500 test requests to deliver consistent reporting results to application consumers.')
            return {'experience': {'recent': {'bullets': [bullet]}}}
        if stage == 'review':
            return {'summary': 'Reviewed', 'findings': [], 'changes': []}
        pytest.fail('Unexpected additional call: '+stage)

    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    result = app.generate_jd_only_resume(jd, [ROLE], 'professional')
    assert stages == ['plan', 'targeting', 'core', 'experience', 'review']
    assert ('Snowflake' in result['resume']['experience']['recent']['bullets'][0]) == fits_story
    assert result['plan']['optional'] == plan['optional']


def test_exact_unlinked_advisory_patch_is_linked_without_another_call():
    draft = {'headline': 'Engineer', 'summary': 'Builds APIs.', 'skills': [
        {'category': 'Backend Engineering', 'items': ['REST APIs', 'Request validation']}], 'experience': {}}
    review = experiment.identify_findings({'findings': [
        {'target_id': 'skills:1', 'severity': 'advisory', 'issue': 'Include the planned framework', 'change_indices': []}],
        'changes': [{'target': 'skills', 'group_number': 1, 'expected_category': 'Backend Engineering',
                     'category': 'Backend Engineering', 'items': ['Spring Boot', 'REST APIs']}]}, draft)
    linked = experiment.reconcile_review_links(review)
    assert linked['findings'][0]['severity'] == 'repair'
    assert linked['findings'][0]['change_indices'] == [1]
    patch = {'changes': linked['changes'], 'dispositions': [{
        'finding_id': linked['findings'][0]['finding_id'], 'status': 'patched', 'change_indices': [1], 'reason': 'Include planned framework'}]}
    experiment.validate_dispositions(patch, linked['findings'])
    assert experiment.apply_repairs(draft, patch)['skills'][0]['items'] == ['Spring Boot', 'REST APIs']
    assert review['findings'][0]['change_indices'] == []


@pytest.mark.parametrize('severity,targets', [('factual_blocker', ['skills:1']), ('advisory', ['skills:1', 'skills'])])
def test_review_link_recovery_does_not_guess_or_override_blocker(severity, targets):
    review = {'findings': [{'target_id': target, 'severity': severity, 'change_indices': []} for target in targets],
              'changes': [{'target': 'skills', 'group_number': 1}]}
    assert experiment.reconcile_review_links(review) == review


def test_swapped_model_indices_rebuilt_from_exact_targets_without_changing_patches():
    changes = [
        {'target': 'skills', 'group_number': 4},
        {'target': 'skills', 'group_number': 5},
        {'target': 'skills', 'group_number': 8},
        {'target': 'bullet', 'role_key': 'mckinsey', 'bullet_number': 5},
        {'target': 'bullet', 'role_key': 'uber', 'bullet_number': 2},
        {'target': 'bullet', 'role_key': 'uber', 'bullet_number': 3},
    ]
    targets = ['skills:4', 'skills:5', 'skills:8', 'bullet:mckinsey:5', 'bullet:uber:2', 'bullet:uber:3']
    review = {'findings': [{'finding_id': f'finding-{i}', 'target_id': target, 'severity': 'repair',
                           'issue': 'Clarify planned work', 'change_indices': [index]}
                          for i, (target, index) in enumerate(zip(targets, [4, 5, 6, 1, 2, 3]))],
              'changes': changes}
    corrected = experiment.reconcile_review_links(review)
    assert [f['change_indices'] for f in corrected['findings']] == [[1], [2], [3], [4], [5], [6]]
    assert corrected['changes'] == changes
    assert review['findings'][0]['change_indices'] == [4]
    patch = {'changes': changes, 'dispositions': [
        {'finding_id': f['finding_id'], 'status': 'patched', 'change_indices': f['change_indices'], 'reason': f['issue']}
        for f in corrected['findings']]}
    experiment.validate_dispositions(patch, corrected['findings'])


@pytest.mark.parametrize('value,unit,accepted', [('99.9', 'authentication success rate', True),
    ('80', 'authentication success rate', False), ('0.999', 'authentication success rate', False),
    ('99.9', 'requests', False)])
def test_rate_unit_accepts_only_the_exact_visible_percentage(value, unit, accepted):
    bullet = copy.deepcopy(BULLET)
    bullet['text'] = ('Integrated OAuth2 authentication and session management with secure token handling, achieving a 99.9% '
                      'authentication success rate and strengthening access control across monitored business workflows during releases.')
    bullet['measurement'].update(value=value, unit=unit)
    draft = {'headline': 'Engineer', 'summary': 'Builds APIs.', 'skills': [], 'experience': {'recent': {'bullets': [bullet]}}}
    errors, _ = experiment.draft_issues(draft, {}, [ROLE], app._numeric_tokens)
    mismatch = [e for e in errors if 'measurement value/unit' in e]
    assert bool(mismatch) != accepted

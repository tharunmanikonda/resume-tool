import copy

import pytest

import app
import jd_draft_experiment as experiment
import resume_review_ids as ids
from manual_resume_parser import parse_updated_content_to_resume

TEXT = ('Implemented request validation for 500 requests using typed API contracts and explicit error responses, '
        'preventing malformed payloads from reaching service handlers during integration testing and release validation.')
METRIC = {'kind': 'scale', 'value': '500', 'unit': 'requests', 'context': 'Proposed workload', 'status': 'illustrative_unverified'}
TITLES = {'mckinsey': 'Salesforce Developer', 'uber': 'Software Engineer', 'kpmg': 'Java Developer', 'trigent': 'Frontend Developer'}
ROLES = [{'key': key, 'company': key.title(), 'default_title': 'Full Stack Developer', 'location': 'CA, USA',
          'dates': dates, 'bullet_min': 1, 'bullet_max': 1} for key, dates in zip(TITLES,
          ['May 2025 - Present', 'February 2024 - May 2025', 'September 2021 - July 2022', 'March 2020 - August 2021'])]
JD = 'Build Salesforce applications using Apex and Lightning Web Components.'


def model_plan():
    stories = ['Salesforce account portal', 'Customer API application', 'Java reporting APIs', 'React forms portal']
    return {'role_positioning': 'Salesforce Developer', 'target_system': 'Salesforce account portal',
            'target_workflow': 'Manage account workflows',
            'required': [{'capability': 'Salesforce development', 'jd_quote': JD}], 'optional': [], 'unknowns': ['Product'],
            'experience': {key: {'title': title, 'system': story, 'workflow': 'Implement features',
                'scope': 'Feature implementation', 'assumptions': ['Proposed project'],
                'contributions': ['Implement request validation | typed contracts | clear failures | workload requests']}
                for (key, title), story in zip(TITLES.items(), stories)}}


@pytest.mark.parametrize('mode', ['professional', 'new_grad', 'internship', 'coop'])
def test_story_titles_survive_generation_display_and_export_parse(monkeypatch, mode):
    calls = []
    def generate(stage, schema, prompt, supplied):
        calls.append(stage)
        if stage == 'plan':
            assert all('title' in schema['properties']['experience']['properties'][r['key']]['required'] for r in ROLES)
            return model_plan()
        if stage == 'targeting':
            return {'decision': 'aligned', 'corrections': [], 'assessment': {'level_scope': 'Feature implementation',
                'team_path': 'Salesforce application development', 'choice_basis': 'explicit_jd_scope',
                'primary_focus': [{'source_clause_id': 'jd_1', 'focus': 'Build Salesforce applications'}],
                'secondary_focus': [], 'excluded_paths': [], 'rationale': 'Match application workflow'}}
        if stage == 'core':
            return {'headline': 'Salesforce Developer', 'summary': 'Builds business applications.',
                    'skills': [{'category': 'Programming Languages', 'items': ['Apex', 'JavaScript']}]}
        if stage == 'experience':
            assert {key: entry['title'] for key, entry in supplied['checked_plan']['experience'].items()} == TITLES
            return {'experience': {key: {'bullets': [{'text': TEXT, 'measurement': copy.deepcopy(METRIC),
                                                    'contribution_number': 1}]} for key in TITLES}}
        assert stage == 'review'
        assert {item['role_key']: item['text'] for item in supplied['review_items']['titles'][1:]} == TITLES
        return {'snapshot_id': supplied['snapshot_id'], 'review_summary': 'Reviewed', 'titles': [], 'summaries': [],
                'skills': [], 'bullets': [], 'notes': []}
    monkeypatch.setattr(app, '_jd_experiment_call', generate)
    original_roles = copy.deepcopy(ROLES)
    result = app.generate_jd_only_resume(JD, ROLES, mode)
    assert calls == ['plan', 'targeting', 'core', 'experience', 'review']
    assert result['audit']['decision'] == 'approved'
    for key, title in TITLES.items():
        assert result['resume']['experience'][key]['title'] == title
        assert title in result['content']
    base = {'experience': [{'company': r['company'], 'title': r['default_title'], 'bullets': []} for r in ROLES]}
    parsed = parse_updated_content_to_resume(result['content'], base, enabled_experience_keys=list(TITLES), experience_blueprints=ROLES)
    assert [entry['title'] for entry in parsed['experience']] == list(TITLES.values())
    assert ROLES == original_roles


def test_review_can_correct_work_title_by_tid_without_touching_headline_or_bullets(monkeypatch):
    resume = {'updated_title': 'Software Engineer', 'updated_summary': 'Builds applications.',
              'updated_skills': [{'category': 'Programming Languages', 'items': ['Apex', 'JavaScript']}],
              'experience': {'mckinsey': {'title': 'Full Stack Developer', 'bullets': [TEXT]}}}
    def review(stage, schema, prompt, supplied):
        assert stage == 'review'
        assert supplied['review_items']['titles'][1] == {'tid': 2, 'role_key': 'mckinsey',
            'text': 'Full Stack Developer', 'scope': 'experience'}
        return {'snapshot_id': supplied['snapshot_id'], 'review_summary': 'Align functional title',
            'titles': [{'tid': 2, 'replacement': 'Salesforce Developer', 'reason': 'Matches the planned Apex/LWC project'}],
            'summaries': [], 'skills': [], 'bullets': [], 'notes': []}
    monkeypatch.setattr(app, '_jd_experiment_call', review)
    result = app.review_jd_only_resume(JD, {'_resume_mode': 'professional', '_jd_only_plan': model_plan()}, resume, ROLES[:1], repair=True)
    assert result['decision'] == 'approved'
    updated = result['_repaired_resume']
    assert updated['experience']['mckinsey']['title'] == 'Salesforce Developer'
    assert updated['updated_title'] == resume['updated_title']
    assert updated['experience']['mckinsey']['bullets'] == [TEXT]
    assert resume['experience']['mckinsey']['title'] == 'Full Stack Developer'


def test_one_selected_late_role_uses_its_story_title_not_an_automatic_junior_label():
    role = ROLES[0]
    result = experiment.apply_plan_titles({'experience': {'mckinsey': {'bullets': []}}}, model_plan(), [role])
    assert result['experience']['mckinsey']['title'] == 'Salesforce Developer'
    legacy = model_plan();del legacy['experience']['mckinsey']['title']
    result = experiment.ensure_plan_titles(legacy, [role])
    assert result['experience']['mckinsey']['title'] == role['default_title']


def test_targeting_can_correct_title_when_story_direction_changes():
    original = model_plan()
    original['experience']['mckinsey']['title'] = 'Full Stack Developer'
    checked, _ = experiment.apply_targeting_check(original, {'decision': 'corrected', 'corrections': [{
        'target': 'title', 'role_key': 'mckinsey', 'old_text': 'Full Stack Developer', 'replacement': 'Salesforce Developer'}],
        'assessment': {'primary_focus': [], 'secondary_focus': []}}, JD)
    assert checked['experience']['mckinsey']['title'] == 'Salesforce Developer'
    assert original['experience']['mckinsey']['title'] == 'Full Stack Developer'

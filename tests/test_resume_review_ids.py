"""Typed IDs identify one item in one review snapshot, independent of ordering."""
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import app
import jd_draft_experiment as experiment
import resume_review_ids as ids

TEXT = ('Implemented request validation for 500 requests using typed API contracts and explicit error responses, '
        'preventing malformed payloads from reaching service handlers during integration testing and release validation.')
METRIC = {'kind': 'scale', 'value': '500', 'unit': 'requests', 'context': 'Proposed workload', 'status': 'illustrative_unverified'}


def draft():
    return {'headline': 'Software Engineer', 'summary': 'Builds service APIs.',
            'skills': [{'category': 'Programming Languages', 'items': ['Python', 'Go']},
                       {'category': 'Backend Engineering', 'items': ['REST APIs', 'gRPC']}],
            'experience': {role: {'bullets': [{'text': TEXT + (' ' if index % 2 else ''), 'contribution_number': index+1,
                                             'measurement': copy.deepcopy(METRIC)} for index in range(count)]}
                           for role, count in [('recent', 7), ('second', 6), ('third', 5)]}}


def response(saved, **updates):
    return {'snapshot_id': saved['snapshot_id'], 'review_summary': 'Reviewed', 'titles': [], 'summaries': [],
            'skills': [], 'bullets': [], 'notes': [], **updates}


def change(bid, text=TEXT):
    return {'bid': bid, 'replacement': text, 'measurement': copy.deepcopy(METRIC), 'reason': 'Clarify the contribution'}


def test_bids_12_15_18_returned_out_of_order_replace_exact_original_locations():
    original = draft(); saved = ids.snapshot(original)
    wire = response(saved, bullets=[change(18, TEXT.replace('Implemented', 'Built')),
                                   change(12, TEXT.replace('Implemented', 'Created')),
                                   change(15, TEXT.replace('Implemented', 'Added'))])
    patch, review = ids.decode(wire, saved, original)
    edited = experiment.apply_repairs(original, patch)
    expected = {18: 'Built', 12: 'Created', 15: 'Added'}
    for bid, (role, index) in saved['locations'].items():
        actual = edited['experience'][role]['bullets'][index]
        if bid in expected:
            assert actual['text'].startswith(expected[bid])
            assert actual['contribution_number'] == index+1
        else:
            assert actual == original['experience'][role]['bullets'][index]
    assert not review['findings']
    assert len(review['applied_findings']) == 3
    assert original == draft()


def test_separate_id_namespaces_cannot_cross_replace():
    original = draft(); saved = ids.snapshot(original)
    wire = response(saved, titles=[{'tid': 1, 'replacement': 'Backend Engineer', 'reason': 'Use standard role'}],
        summaries=[{'psid': 1, 'replacement': 'Develops backend services.', 'reason': 'Align positioning'}],
        skills=[{'sid': 1, 'replacement': {'category': 'Programming Languages', 'items': ['Go', 'SQL']}, 'reason': 'Align tools'}],
        bullets=[change(1, TEXT.replace('Implemented', 'Built'))])
    patch, _ = ids.decode(wire, saved, original)
    edited = experiment.apply_repairs(original, patch)
    assert edited['headline'] == 'Backend Engineer'
    assert edited['summary'] == 'Develops backend services.'
    assert edited['skills'][0]['items'] == ['Go', 'SQL']
    assert edited['skills'][1] == original['skills'][1]
    assert edited['experience']['recent']['bullets'][0]['text'].startswith('Built')
    assert edited['experience']['recent']['bullets'][1:] == original['experience']['recent']['bullets'][1:]
    with pytest.raises(ValueError, match='ID type'):
        ids.decode(response(saved, titles=[{'bid': 1, 'replacement': 'Engineer'}]), saved, original)


@pytest.mark.parametrize('bid', [0, -1, 19, '12', True])
def test_unknown_or_non_integer_id_cannot_apply(bid):
    original = draft(); saved = ids.snapshot(original)
    with pytest.raises(ValueError):
        ids.decode(response(saved, bullets=[change(bid)]), saved, original)
    assert original == draft()


def test_duplicate_id_rejected_before_any_changes_apply():
    original = draft(); saved = ids.snapshot(original)
    with pytest.raises(ValueError, match='Duplicate'):
        ids.decode(response(saved, bullets=[change(12), change(12)]), saved, original)
    assert original == draft()


@pytest.mark.parametrize('mutation', ['insert', 'remove', 'reorder', 'text'])
def test_ids_never_reapplied_to_changed_snapshot(mutation):
    original = draft(); saved = ids.snapshot(original); changed = copy.deepcopy(original)
    bullets = changed['experience']['recent']['bullets']
    if mutation == 'insert': bullets.insert(0, copy.deepcopy(bullets[0]))
    elif mutation == 'remove': bullets.pop()
    elif mutation == 'reorder': bullets.reverse()
    else: bullets[0]['text'] = TEXT.replace('Implemented', 'Built')
    with pytest.raises(ValueError, match='snapshot changed'):
        ids.decode(response(saved, bullets=[change(12)]), saved, changed)


def test_empty_changes_preserve_everything_and_new_schema_has_no_link_indices():
    original = draft(); saved = ids.snapshot(original)
    roles = [{'key': k, 'bullet_min': len(v['bullets'])} for k, v in original['experience'].items()]
    schema = experiment.review_apply_schema(roles, original)
    Draft202012Validator.check_schema(schema)
    assert Draft202012Validator(schema).is_valid(response(saved))
    assert 'change_indices' not in json.dumps(schema)
    assert 'old_text' not in json.dumps(schema)
    assert 'target_id' not in json.dumps(schema)
    patch, _ = ids.decode(response(saved), saved, original)
    assert experiment.apply_repairs(original, patch) == original


def test_real_transit_response_ignores_broken_legacy_numbers():
    # Minimal saved failure: three replacements referenced nonexistent 4/5.
    original = draft(); saved = ids.snapshot(original)
    targets = [('recent', 4), ('second', 3), ('third', 3)]
    legacy = {'summary': 'Three fixes', 'findings': [
        {'target_id': f'bullet:{role}:{number}', 'severity': 'repair', 'issue': 'Clarify contribution', 'change_indices': [link]}
        for (role, number), link in zip(targets, [3, 4, 5])], 'changes': [
        {'target': 'bullet', 'role_key': role, 'bullet_number': number,
         'old_text': original['experience'][role]['bullets'][number-1]['text'],
         'replacement': {'text': TEXT.replace('Implemented', 'Built'), 'measurement': copy.deepcopy(METRIC), 'contribution_number': number}}
        for role, number in targets]}
    patch, review = experiment.decode_review_response(legacy, saved, original)
    revised = experiment.apply_repairs(original, patch)
    assert len(review['applied_findings']) == 3
    for role, number in targets:
        assert revised['experience'][role]['bullets'][number-1]['text'].startswith('Built')
    assert 'dispositions' not in patch


def test_complete_review_uses_typed_ids_for_all_sections_without_extra_calls(monkeypatch):
    original = draft()
    canonical = {'updated_title': original['headline'], 'updated_summary': original['summary'],
        'updated_skills': original['skills'], 'experience': {
            role: {'title': 'Software Engineer', 'bullets': [b['text'] for b in entry['bullets']]}
            for role, entry in original['experience'].items()}}
    roles = [{'key': role, 'company': role, 'location': 'Remote', 'dates': '2020 - Present',
              'default_title': 'Software Engineer', 'bullet_min': len(entry['bullets'])}
             for role, entry in original['experience'].items()]
    stages = []
    def model(stage, schema, prompt, supplied):
        stages.append(stage)
        assert stage == 'review'
        assert [item['bid'] for item in supplied['review_items']['bullets']] == list(range(1, 19))
        assert 'findings' not in schema['properties']
        return {'snapshot_id': supplied['snapshot_id'], 'review_summary': 'Exact replacements',
                'titles': [{'tid': 1, 'replacement': 'Backend Engineer', 'reason': 'Natural title'}],
                'summaries': [{'psid': 1, 'replacement': 'Builds backend service APIs.', 'reason': 'Align positioning'}],
                'skills': [{'sid': 2, 'replacement': {'category': 'Backend Engineering', 'items': ['Spring Boot', 'REST APIs']},
                            'reason': 'Use planned tools'}],
                'bullets': [change(bid, TEXT.replace('Implemented', 'Built')) for bid in [18, 12, 15]], 'notes': []}
    monkeypatch.setattr(app, '_jd_experiment_call', model)
    result = app.review_jd_only_resume('Build backend APIs.', {'_resume_mode': 'professional'}, canonical, roles, repair=True)
    assert stages == ['review']
    assert result['decision'] == 'approved'
    revised = result['_repaired_resume']
    assert revised['updated_title'] == 'Backend Engineer'
    assert revised['updated_summary'] == 'Builds backend service APIs.'
    assert revised['updated_skills'][1]['items'] == ['Spring Boot', 'REST APIs']
    for bid in [12, 15, 18]:
        role, index = ids.snapshot(original)['locations'][bid]
        assert revised['experience'][role]['bullets'][index].startswith('Built')
    assert canonical['updated_title'] == original['headline']


def test_skills_removals_use_original_ids_and_apply_atomically():
    original = draft()
    original['skills'].append({'category': 'Testing & Quality', 'items': ['Unit testing', 'Integration testing']})
    saved = ids.snapshot(original)
    wire = response(saved, skills=[
        {'sid': 1, 'replacement': {'category': 'Programming Languages', 'items': []}, 'reason': 'Consolidate'},
        {'sid': 3, 'replacement': {'category': 'Testing & Quality', 'items': ['pytest', 'Integration testing']}, 'reason': 'Clarify'}])
    Draft202012Validator(experiment.review_apply_schema([{'key': 'recent', 'bullet_min': 7}], original)).validate(wire)
    patch, _ = ids.decode(wire, saved, original)
    revised = experiment.apply_repairs(original, patch)
    assert revised['skills'] == [original['skills'][1], {'category': 'Testing & Quality', 'items': ['pytest', 'Integration testing']}]
    assert len(original['skills']) == 3
    assert revised['experience'] == original['experience']


def test_review_cannot_remove_every_skills_group():
    original = draft(); saved = ids.snapshot(original)
    wire = response(saved, skills=[{'sid': i+1, 'replacement': {'category': g['category'], 'items': []}, 'reason': 'Remove'} for i, g in enumerate(original['skills'])])
    patch, _ = ids.decode(wire, saved, original)
    with pytest.raises(ValueError, match='every skills group'):
        experiment.apply_repairs(original, patch)
    assert original == draft()


def test_review_snapshot_exposes_independent_measurement_copy():
    original = draft()
    saved = ids.snapshot(original)
    item = saved['items']['bullets'][0]
    assert item['measurement'] == METRIC
    item['measurement']['value'] = '999'
    assert original['experience']['recent']['bullets'][0]['measurement'] == METRIC


def test_nine_relevant_skills_groups_can_survive_review_unchanged():
    original = draft()
    original['skills'] = [
        {'category': 'Programming Languages', 'items': ['Java', 'TypeScript']},
        {'category': 'Frontend Engineering', 'items': ['React', 'Web accessibility']},
        {'category': 'Backend Engineering', 'items': ['Spring Boot', 'REST APIs']},
        {'category': 'Data & Storage', 'items': ['PostgreSQL', 'SQL Server']},
        {'category': 'Cloud & Infrastructure', 'items': ['Docker', 'AWS']},
        {'category': 'DevOps & CI/CD', 'items': ['Git', 'GitHub Actions']},
        {'category': 'Testing & Quality', 'items': ['JUnit', 'Jest']},
        {'category': 'AI & LLM Systems', 'items': ['GitHub Copilot', 'Prompt engineering']},
        {'category': 'Observability & Reliability', 'items': ['Prometheus', 'Grafana']},
    ]
    saved = ids.snapshot(original)
    wire = response(saved)
    Draft202012Validator(experiment.review_apply_schema([{'key': 'recent', 'bullet_min': 7}], original)).validate(wire)
    patch, _ = ids.decode(wire, saved, original)
    revised = experiment.apply_repairs(original, patch)
    assert revised['skills'] == original['skills']
    assert len(revised['skills']) == 9

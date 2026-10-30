import copy

import pytest

import app
import jd_draft_experiment as experiment
from resume_measurements import visible_ratio_matches_measurement

TEXT = ('Execute checklist-driven deployments and post-release smoke tests, limiting incidents to one per three '
        'releases and supporting coordinated cross-team cutovers with rollback-ready validation across sprint delivery cycles.')
METADATA = {'kind': 'improvement', 'value': '0.33', 'unit': 'incidents per release',
            'context': 'one incident per three coordinated releases', 'status': 'illustrative_unverified'}


@pytest.mark.parametrize('text,value,unit,expected', [
    (TEXT, '0.33', 'incidents per release', True),
    (TEXT, '0.333', 'incidents per release', True),
    (TEXT, '0.3', 'incidents per release', True),
    (TEXT, '0.5', 'incidents per release', False),
    (TEXT, '0', 'incidents per release', False),
    (TEXT, '1', 'incidents per release', False),
    (TEXT, '0.33', 'incidents per day', False),
    (TEXT, '0.33', 'requests per release', False),
    ('Recorded 2 failures per 5 deployments during release testing.', '0.4', 'failures per deployment', True),
    ('Recorded 2 failures per 5 deployments during release testing.', '0.4', 'failures per request', False),
    ('Recorded 2 failures per 0 deployments during release testing.', '0.4', 'failures per deployment', False),
    ('Recorded -1 failure per 3 deployments during release testing.', '0.33', 'failures per deployment', False),
    ('Recorded two failures per five deployments during release testing.', '0.4', 'failures per deployment', True),
    ('Reduced incidents during releases.', '0.33', 'incidents per release', False),
    ('Processed 1 request per 3 releases, with incidents monitored separately.', '0.33', 'incidents per release', False),
])
def test_only_explicit_matching_ratio_and_units_are_accepted(text, value, unit, expected):
    assert visible_ratio_matches_measurement(text, {**METADATA, 'value': value, 'unit': unit}) == expected


def test_real_reviewer_bullet_passes_without_changing_visible_number_or_metadata():
    bullet = {'text': TEXT, 'measurement': copy.deepcopy(METADATA), 'contribution_number': 1}
    original = copy.deepcopy(bullet)
    draft = {'headline': 'Software Engineer', 'summary': 'Builds services.', 'skills': [],
             'experience': {'uber': {'bullets': [bullet]}}}
    errors, _ = experiment.draft_issues(draft, {}, [{'key': 'uber', 'company': 'Uber', 'bullet_min': 1}],
                                       app._numeric_tokens, check_writing=True)
    assert errors == []
    assert bullet == original
    bullet['measurement']['value'] = '0.5'
    errors, _ = experiment.draft_issues(draft, {}, [{'key': 'uber', 'company': 'Uber', 'bullet_min': 1}], app._numeric_tokens)
    assert any('measurement value/unit' in e for e in errors)

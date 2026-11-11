import copy

import pytest

import app
import jd_draft_experiment as jd
from resume_measurements import format_percentage_symbols


@pytest.mark.parametrize('before,after', [
    ('Reduced errors by 30 percent.', 'Reduced errors by 30%.'),
    ('Coverage reached approximately 92.5 per cent.', 'Coverage reached approximately 92.5%.'),
    ('Improved by 30 % and 10 PERCENT.', 'Improved by 30% and 10%.'),
    ('Improved by 3 percentage points at the 95th percentile.', 'Improved by 3 percentage points at the 95th percentile.'),
])
def test_percentage_format_preserves_meaning(before, after):
    assert format_percentage_symbols(before) == after


def test_draft_normalization_formats_prose_without_mutating_measurement_or_input():
    bullet = {'text': 'Reduced API validation errors by approximately 30 percent using typed contracts.', 'contribution_number': 1,
              'measurement': {'kind': 'improvement', 'value': '30', 'unit': 'percent', 'context': 'validation errors', 'status': 'illustrative_unverified'}}
    original = {'experience': {'recent': {'bullets': [bullet]}}}
    before = copy.deepcopy(original)
    result = jd.normalize_draft(original, app._numeric_tokens)
    assert result['experience']['recent']['bullets'][0]['text'] == 'Reduced API validation errors by approximately 30% using typed contracts.'
    assert result['experience']['recent']['bullets'][0]['measurement'] == bullet['measurement']
    assert original == before

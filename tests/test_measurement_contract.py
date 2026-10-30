import copy

import pytest
import app as resume_app
from resume_bullet_quality import claim_evidence_issues, project_writing_rules
from resume_measurements import measurement_rules, normalize_number_words


BP = {'key': 'example', 'company': 'Example', 'default_title': 'Software Engineer',
      'bullet_min': 1, 'bullet_max': 1}


def evidence_issues(source, bullet, measurement=None):
    evidence = {'bullet_number': 1, 'source_refs': ['source_bullets.1'], 'confirmation_questions': []}
    if measurement is not None:
        evidence['measurement'] = measurement
    payload = {'experience': {'example': {'title': 'Software Engineer', 'bullets': [bullet], 'bullet_evidence': [evidence]}}}
    return claim_evidence_issues(payload, [{**BP, 'source_bullets': [source]}], resume_app._numeric_tokens)


@pytest.mark.parametrize('source,bullet', [
    ('Analyzed over 50,000 telemetry metrics.', 'Analyzed 50,000+ telemetry metrics.'),
    ('Validated more than fifteen UI regressions.', 'Validated over 15 UI regressions.'),
    ('Integrated ten enterprise audit applications.', 'Integrated 10 enterprise audit applications.'),
    ('Supported 1M+ monthly transactions.', 'Supported 1,000,000+ monthly transactions.'),
    ('Served approximately 500 requests.', 'Served about 500 requests.'),
    ('Maintained response times under 500 ms.', 'Maintained response times below 500 milliseconds.'),
    ('Handled at least 200 transactions.', 'Handled >=200 transactions.'),
    ('Maintained sub-second responses.', 'Maintained response times under 1 second.'),
])
def test_equivalent_source_quantities_do_not_trigger_repair(source, bullet):
    assert resume_app._numeric_tokens(source) == resume_app._numeric_tokens(bullet)
    assert evidence_issues(source, bullet) == []


@pytest.mark.parametrize('source,bullet', [
    ('Analyzed 50,000 telemetry metrics.', 'Analyzed 60,000 telemetry metrics.'),
    ('Handled approximately 500 requests.', 'Handled 500 requests.'),
    ('Handled over 500 requests.', 'Handled under 500 requests.'),
    ('Handled at least 500 requests.', 'Handled at most 500 requests.'),
    ('Reduced latency by 32%.', 'Reduced latency by 42%.'),
    ('Handled 50,000 transactions.', 'Handled 50,000+ transactions.'),
])
def test_changed_measurements_and_qualifiers_remain_unsupported(source, bullet):
    assert any('unsupported metrics' in issue for issue in evidence_issues(source, bullet))


def test_time_unit_change_is_rejected_even_when_numeric_value_matches():
    assert any('units differ' in issue for issue in evidence_issues('Maintained latency at 500 milliseconds.', 'Maintained latency at 500 seconds.'))


def test_numbers_with_modifiers_and_written_quantities_are_counted():
    for text in ['50,000 monthly audit transactions', 'over 50,000 telemetry metrics',
                 'ten enterprise audit applications', 'more than fifteen UI regressions', 'five device types']:
        assert resume_app._numeric_tokens(text)
    assert normalize_number_words('twenty-five pages and one hundred and ten tests') == '25 pages and 110 tests'


def test_software_versions_are_not_measurements():
    assert not resume_app._numeric_tokens('Used OAuth 2.0, TLS 1.3, HTTP/2, Microsoft 365, .NET 8, Java 17 and Python 3.11.')


def test_measurement_records_distinguish_scale_improvement_and_qualitative():
    scale = {'kind': 'scale', 'measure': 'requests processed', 'value': '500', 'unit': 'requests',
             'context': '', 'connection': 'Implemented request validation'}
    assert not evidence_issues('Validated 500 requests.', 'Validated 500 requests.', scale)
    bad = copy.deepcopy(scale)
    bad.update(kind='qualitative')
    assert any('qualitative' in issue for issue in evidence_issues('Validated 500 requests.', 'Validated 500 requests.', bad))
    bad = copy.deepcopy(scale)
    bad.update(value='600')
    assert any('metadata must match' in issue for issue in evidence_issues('Validated 500 requests.', 'Validated 500 requests.', bad))
    bad = copy.deepcopy(scale)
    bad.update(kind='improvement', connection='')
    assert any('action/result connection' in issue for issue in evidence_issues('Validated 500 requests.', 'Validated 500 requests.', bad))


def test_measurement_contract_reaches_drafting_synthesis_review_and_repairs():
    for prompt in [project_writing_rules(), resume_app.build_ai_final_synthesis_prompt(), resume_app.build_ai_resume_quality_audit_prompt()]:
        assert measurement_rules() in prompt
    issues = evidence_issues('Validated 500 requests.', 'Validated 600 requests.')
    assert all('use [Confirm metric:' not in issue for issue in issues)

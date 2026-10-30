import copy
import pytest
import app as resume_app
from test_resume_quality_audit import audit_result, current_resume, active_blueprints, title_change, ANALYSIS


def numeric_blueprints():
    result = active_blueprints()
    result[0]['_generation_context_version'] = 2
    return result


def validate(result, current=None):
    return resume_app.validate_resume_quality_audit_result(
        result, current_resume=current or current_resume(), analysis_payload=ANALYSIS,
        active_blueprints=numeric_blueprints(),
    )


def legacy_numeric_result():
    result = audit_result('manual_attention')
    result['manual_findings'] = [{
        'id': 'confirmation.required', 'severity': 'error', 'path': 'experience',
        'problem': 'Supply measurements for 1 more distinct accomplishments to reach the 80% target. Keep these questions outside resume content. Supply measurements for 3 more distinct accomplishments to reach the 80% target. Keep these questions outside resume content.',
        'recommendation': 'Supply measurements.', 'evidence_refs': [],
    }]
    return result


def test_measurement_target_does_not_discard_valid_title_patch():
    checked = validate(audit_result('changes_suggested', title_change()))
    assert checked['decision'] == 'changes_suggested'
    assert checked['manual_findings'] == []
    assert [g['change_id'] for g in checked['review_groups']] == ['title.market-standard']
    assert any(g['kind'] == 'numerical_target' for g in checked['non_blocking_gaps'])
    assert resume_app._quality_audit_preflight(current_resume(), numeric_blueprints())['pending_confirmations'] == []


def test_approved_resume_with_measurement_note_is_export_eligible():
    checked = validate(audit_result())
    assert checked['decision'] == 'approved'
    assert checked['decision'] in resume_app.AI_PDF_ALLOWED_AUDIT_STATUSES
    assert any(g['kind'] == 'numerical_target' for g in checked['non_blocking_gaps'])


def test_cached_numeric_only_block_is_reclassified_without_rewriting_resume():
    raw = legacy_numeric_result()
    checked = validate(raw)
    assert checked['decision'] == 'approved'
    assert checked['manual_findings'] == []
    assert checked['changes'] == resume_app._empty_resume_quality_audit_changes()
    assert raw['decision'] == 'manual_attention'


def test_real_confirmation_block_is_not_reclassified_as_measurement_advice():
    raw = legacy_numeric_result()
    raw['manual_findings'][0]['problem'] = 'One or more drafted accomplishments contain unconfirmed details or missing measurements.'
    assert validate(raw)['decision'] == 'manual_attention'
    raw = legacy_numeric_result()
    raw['manual_findings'].append({'id': 'facts.unverified', 'severity': 'error', 'path': 'experience', 'problem': 'Unconfirmed hardware work.', 'recommendation': 'Clarify.', 'evidence_refs': []})
    checked = validate(raw)
    assert checked['decision'] == 'manual_attention'
    assert checked['manual_findings'][0]['id'] == 'facts.unverified'


def test_inline_unverified_claim_remains_blocking_despite_legacy_numeric_finding():
    current = current_resume()
    current['experience']['mckinsey']['bullets'][0] = '[Confirm: proposed work] Installed vehicle controllers.'
    assert validate(legacy_numeric_result(), current)['decision'] == 'manual_attention'

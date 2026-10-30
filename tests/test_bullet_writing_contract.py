"""The final writing contract survives review patches and document exports."""
import pytest

from jd_draft_experiment import WRITING_POLICY_VERSION, bullet_writing_issues
from pdf_builder import build_resume_docx


VALID = ('Implemented request validation for 500 requests using typed API contracts and explicit error responses, '
         'preventing malformed payloads from reaching service handlers during integration testing and release validation.')


@pytest.mark.parametrize('length,invalid', [(24, True), (25, False), (30, False), (31, True)])
def test_final_word_count_boundaries(length, invalid):
    words = VALID.split()
    text = ' '.join((words + ['integration', 'checks', 'before', 'deployment'])[:length])
    assert len(text.split()) == length
    result = bullet_writing_issues({'experience': {'role': {'bullets': [{'text': text}]}}})
    assert bool(result) == invalid


def test_hyphenated_words_and_renderer_strings_use_same_count():
    text = VALID.replace('request validation', 'request-validation')
    structured = {'experience': {'role': {'bullets': [{'text': text}]}}}
    rendered = {'experience': [{'company': 'Example', 'bullets': [text]}]}
    assert len(text.split()) == 26
    assert bullet_writing_issues(structured) == bullet_writing_issues(rendered) == []


def test_numerical_coverage_checked_per_role_not_whole_resume():
    from app import _numeric_tokens
    qualitative = VALID.replace('500 requests', 'incoming requests')
    result = bullet_writing_issues({'experience': {
        'recent': {'bullets': [VALID] * 5},
        'early': {'bullets': [qualitative]},
    }}, _numeric_tokens)
    assert len(result) == 1
    assert 'early: numerical evidence in 0/1' in result[0]


def test_manual_shortening_blocks_document_before_overwriting_existing_file(tmp_path):
    output = tmp_path / 'existing.docx'
    output.write_bytes(b'existing document')
    with pytest.raises(ValueError, match='writing rules failed'):
        build_resume_docx({'_writing_policy_version': WRITING_POLICY_VERSION,
                           'experience': [{'company': 'Example', 'bullets': ['Built APIs.']}]}, str(output))
    assert output.read_bytes() == b'existing document'


def test_validated_export_keeps_aws_certification(tmp_path):
    from docx import Document
    output = tmp_path / 'resume.docx'
    cert = 'AWS Certified Solutions Architect – Associate'
    build_resume_docx({'_writing_policy_version': WRITING_POLICY_VERSION,
                      'name': 'Candidate', 'experience': [{'company': 'Example', 'bullets': [VALID]}],
                      'certifications': [cert]}, str(output))
    text = '\n'.join(p.text for p in Document(output).paragraphs)
    assert 'CERTIFICATIONS' in text.upper()
    assert cert in text

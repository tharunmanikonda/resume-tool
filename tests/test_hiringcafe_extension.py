import json
from pathlib import Path

from extension_drafts import normalize_context


def test_hiringcafe_reader_registered_without_duplicate_panel():
    manifest = json.loads(Path('extension/public/manifest.json').read_text())
    reader = next(e for e in manifest['content_scripts'] if 'hiringcafe-content-script.js' in e['js'])
    panel = next(e for e in manifest['content_scripts'] if 'panel-host.js' in e['js'])
    for host in ['hiring.cafe', 'www.hiring.cafe', 'hiringcafe.com', 'www.hiringcafe.com']:
        assert f'https://{host}/*' in reader['matches']
        assert f'https://{host}/*' in panel['exclude_matches']


def test_hiringcafe_draft_keeps_identity_and_permalink():
    context = normalize_context({
        'source': 'hiringcafe',
        'url': 'https://hiringcafe.com/job/software-engineer-acme-97snnjd2c8bn394y?ref=search',
        'company_name': 'Acme', 'role_title': 'Software Engineer',
        'job_description': 'Develop Python services. ' * 10,
    })
    assert context['external_job_id'] == '97snnjd2c8bn394y'
    assert context['canonical_url'] == 'https://hiringcafe.com/job/software-engineer-acme-97snnjd2c8bn394y'
    assert context['source'] == 'hiringcafe'


def test_hiringcafe_legacy_selected_job_query_is_preserved():
    context = normalize_context({
        'source': 'hiringcafe', 'url': 'https://hiring.cafe/?v=job123&searchState=filters',
        'company_name': 'Acme', 'role_title': 'Engineer', 'job_description': 'Build services. ' * 10,
    })
    assert context['external_job_id'] == 'job123'
    assert context['canonical_url'] == 'https://hiring.cafe/?v=job123'

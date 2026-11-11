import jd_draft_experiment as jd


def test_presets_selected_by_company_and_key_without_source_content():
    roles = [{'key': 'uber', 'company': 'Uber', 'source_bullets': ['private'], 'default_title': 'Saved title'},
             {'key': 'trigent', 'company': 'Trigent Software'},
             {'key': 'mckinsey', 'company': 'Different employer'}]
    contexts = jd.employer_project_contexts(roles)
    assert set(contexts) == {'uber', 'trigent'}
    assert contexts['uber']['domain'] == 'Ride-sharing and related trip operations'
    assert 'source_bullets' not in str(contexts)
    assert 'Saved title' not in str(contexts)
    assert 'client industry unspecified' in contexts['trigent']['domain']


def test_selected_profile_contexts_do_not_include_unselected_employers():
    contexts = jd.employer_project_contexts([{'key': 'mckinsey', 'company': 'McKinsey & Company'}])
    assert set(contexts) == {'mckinsey'}
    contexts['mckinsey']['fallback_project']['purpose'] = 'Changed'
    assert jd.employer_project_contexts([{'key': 'mckinsey', 'company': 'McKinsey & Company'}])['mckinsey']['fallback_project']['purpose'] != 'Changed'


def test_changing_preset_changes_generation_fingerprint(monkeypatch):
    import app
    calls = []
    def stop(stage, schema, prompt, inputs):
        calls.append(inputs['employer_project_contexts'])
        raise RuntimeError('Stop before paid generation')
    monkeypatch.setattr(app, '_jd_experiment_call', stop)
    import pytest
    role = {'key': 'uber', 'company': 'Uber', 'dates': '2024-2025', 'location': 'USA', 'bullet_min': 1, 'bullet_max': 1}
    states = []
    with pytest.raises(RuntimeError, match='Stop before'):
        app.generate_jd_only_resume('Build payment APIs', [role], 'professional', checkpoint=lambda stage, state: states.append(state))
    assert calls[0]['uber']['fallback_project']['purpose']
    original = jd.employer_project_contexts
    def changed(roles):
        contexts = original(roles)
        contexts['uber']['fallback_project']['purpose'] = 'Updated project purpose'
        return contexts
    monkeypatch.setattr(jd, 'employer_project_contexts', changed)
    with pytest.raises(RuntimeError, match='Stop before'):
        app.generate_jd_only_resume('Build payment APIs', [role], 'professional', saved_state=states[0], checkpoint=lambda stage, state: states.append(state))
    assert states[0]['fingerprint'] != states[-1]['fingerprint']

"""Preserve candidate context between profile, snapshots, and AI stages."""
from copy import deepcopy
import re

from resume_bullet_quality import ROLE_EVIDENCE_FIELDS

PROFILE_CONTEXT_FIELDS = ('summary', 'technical_skills', 'education')


def _identity(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('–', '-').replace('—', '-')).strip().casefold()


def role_matches(first, second):
    return all(_identity(first.get(field)) and _identity(first.get(field)) == _identity(second.get(field))
               for field in ('company', 'title', 'dates'))


def profile_with_resume_context(profile, base_resume):
    """Backfill only matching roles from the configured resume, never by position.

    Explicit evidence fields (including an empty list) override the base resume.
    An unrelated named resume cannot supply another candidate's work history.
    """
    result = deepcopy(profile if isinstance(profile, dict) else {})
    if result.get('resume_category') == 'data_center_infrastructure':
        return result
    if base_resume.get('name') and result.get('name') and _identity(base_resume['name']) != _identity(result['name']):
        return result
    history = result.get('experience_history') or []
    base_roles = [r for r in base_resume.get('experience', []) if isinstance(r, dict)]
    matching = []
    for role in history:
        if not isinstance(role, dict):
            continue
        matches = [source for source in base_roles if role_matches(role, source)]
        if len(matches) != 1:
            continue
        matching.append(role)
        if not any(field in role for field in ROLE_EVIDENCE_FIELDS):
            bullets = matches[0].get('bullets') or []
            if bullets:
                role['source_bullets'] = deepcopy(bullets)
    active = [r for r in history if isinstance(r, dict) and r.get('enabled', True) and r.get('company')]
    if active and all(any(r is item for item in matching) for r in active):
        for field in PROFILE_CONTEXT_FIELDS:
            if field not in result and base_resume.get(field):
                result[field] = deepcopy(base_resume[field])
    return result


def candidate_generation_context(profile, blueprints=None):
    """One explicit candidate-evidence payload shared by the generation stages."""
    fields = ('experience_history', 'projects', 'certifications', *PROFILE_CONTEXT_FIELDS)
    context = {field: deepcopy(profile.get(field, [] if field != 'summary' else '')) for field in fields}
    if blueprints is not None:
        context['experience_history'] = [{
            'key': bp['key'], 'company': bp.get('company', ''),
            'title': bp.get('default_title', ''), 'dates': bp.get('dates', ''),
            **{field: deepcopy(bp[field]) for field in ROLE_EVIDENCE_FIELDS if field in bp},
        } for bp in blueprints]
    return context


def refresh_profile_evidence(snapshot, current):
    """Refresh sources for matching roles on explicit regeneration, keeping edits."""
    result = deepcopy(snapshot)
    if result.get('name') and current.get('name') and _identity(result['name']) != _identity(current['name']):
        return result
    for role in result.get('experience_history', []):
        matches = [r for r in current.get('experience_history', []) if r.get('key') == role.get('key') and role_matches(role, r)]
        if len(matches) == 1:
            for field in ROLE_EVIDENCE_FIELDS:
                role.pop(field, None)
                if field in matches[0]:
                    role[field] = deepcopy(matches[0][field])
    for field in PROFILE_CONTEXT_FIELDS:
        if field in current:
            result[field] = deepcopy(current[field])
    return result

"""Snapshot-scoped, typed integer IDs for partial resume review replacements."""
from copy import deepcopy
import hashlib
import json


def obj(properties):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


def snapshot(draft):
    saved = deepcopy(draft)
    locations, bullets = {}, []
    for role, entry in saved.get('experience', {}).items():
        for index, bullet in enumerate(entry.get('bullets', [])):
            bid = len(locations) + 1
            locations[bid] = (role, index)
            bullets.append({'bid': bid, 'role_key': role, 'text': bullet['text'],
                            'measurement': deepcopy(bullet.get('measurement', {}))})
    titles = [{'tid': 1, 'text': saved.get('headline', ''), 'scope': 'main'}]
    for role, entry in saved.get('experience', {}).items():
        if entry.get('title'):
            titles.append({'tid': len(titles)+1, 'role_key': role, 'text': entry['title'], 'scope': 'experience'})
    digest = hashlib.sha256(json.dumps({'draft': saved, 'locations': list(locations.items())},
        sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return {'snapshot_id': digest, 'draft': saved, 'locations': locations, 'items': {
        'titles': titles,
        'summaries': [{'psid': 1, 'text': saved.get('summary', '')}],
        'skills': [{'sid': i, 'category': group['category'], 'items': deepcopy(group['items'])}
                   for i, group in enumerate(saved.get('skills', []), 1)],
        'bullets': bullets}}


def response_schema(saved, bullet_schema, categories=None):
    string = {'type': 'string'}
    def id_field(kind):
        ids = [item[kind] for item in saved['items'][{'tid': 'titles', 'psid': 'summaries', 'sid': 'skills', 'bid': 'bullets'}[kind]]]
        return {'type': 'integer', 'enum': ids} if ids else {'type': 'integer', 'minimum': 1}
    skill = obj({'category': {'type': 'string', 'enum': sorted(categories)} if categories else string,
                 'items': {'type': 'array', 'items': string, 'minItems': 0, 'maxItems': 5}})
    def array(kind, replacement, measurement=False):
        props = {kind: id_field(kind), 'replacement': replacement, 'reason': string}
        if measurement:
            props['measurement'] = deepcopy(bullet_schema['properties']['measurement'])
        result = {'type': 'array', 'items': obj(props)}
        if not saved['items'][{'tid': 'titles', 'psid': 'summaries', 'sid': 'skills', 'bid': 'bullets'}[kind]]:
            result['maxItems'] = 0
        return result
    notes = [obj({kind: id_field(kind), 'severity': {'type': 'string', 'enum': ['advisory', 'factual_blocker']},
                  'issue': string}) for kind in ('tid', 'psid', 'sid', 'bid')
             if saved['items'][{'tid': 'titles', 'psid': 'summaries', 'sid': 'skills', 'bid': 'bullets'}[kind]]]
    return obj({'snapshot_id': {'type': 'string', 'enum': [saved['snapshot_id']]}, 'review_summary': string,
        'titles': array('tid', string), 'summaries': array('psid', string), 'skills': array('sid', skill),
        'bullets': array('bid', deepcopy(bullet_schema['properties']['text']), True),
        'notes': {'type': 'array', 'items': {'anyOf': notes}}})


def decode(response, saved, current_draft):
    if snapshot(current_draft)['snapshot_id'] != saved['snapshot_id'] or response.get('snapshot_id') != saved['snapshot_id']:
        raise ValueError('Review snapshot changed; do not apply IDs to another resume version.')
    changes, findings, applied, seen = [], [], [], set()
    def resolve(kind, value):
        if type(value) is not int or value < 1:
            raise ValueError('Review IDs must be positive integers.')
        if kind == 'tid':
            titles = saved['items']['titles']
            if value > len(titles):
                raise ValueError('Unknown title review ID.')
            item = titles[value-1]
            if value == 1:
                return 'headline', {'target': 'headline', 'old_text': item['text']}
            return f"title:{item['role_key']}", {'target': 'experience_title', 'role_key': item['role_key'], 'old_text': item['text']}
        if kind == 'psid':
            if value != 1:
                raise ValueError('Unknown summary review ID.')
            return 'summary', {'target': 'summary', 'old_text': saved['draft'].get('summary', '')}
        if kind == 'sid':
            groups = saved['draft'].get('skills', [])
            if value > len(groups):
                raise ValueError('Unknown skills review ID.')
            return f'skills:{value}', {'target': 'skills', 'group_number': value, 'expected_category': groups[value-1]['category']}
        if value not in saved['locations']:
            raise ValueError('Unknown bullet review ID.')
        role, index = saved['locations'][value]
        original = saved['draft']['experience'][role]['bullets'][index]
        return f'bullet:{role}:{index+1}', {'target': 'bullet', 'role_key': role, 'bullet_number': index+1, 'old_text': original['text']}
    def finding(kind, value, target, severity, issue):
        role, number = (target.split(':')[1], int(target.split(':')[2])) if kind == 'bid' else (target.split(':')[1] if target.startswith('title:') else target.split(':')[0], 0)
        return {'finding_id': f'{kind}-{value}', kind: value, 'target_id': target,
                'severity': severity, 'issue': issue, 'role_key': role, 'bullet_number': number}
    for section, kind in [('titles', 'tid'), ('summaries', 'psid'), ('skills', 'sid'), ('bullets', 'bid')]:
        for item in response.get(section, []):
            if {k for k in ('tid', 'psid', 'sid', 'bid') if k in item} != {kind}:
                raise ValueError('Review ID type does not match its section.')
            value = item[kind]
            target, change = resolve(kind, value)
            if (kind, value) in seen:
                raise ValueError('Duplicate review replacement ID.')
            seen.add((kind, value))
            replacement = item['replacement']
            if kind == 'sid':
                if not isinstance(replacement, dict) or not replacement.get('category') or not isinstance(replacement.get('items'), list):
                    raise ValueError('A skills replacement needs its category and items.')
                if len(replacement['items']) == 1:
                    raise ValueError('A retained skills group needs at least two items.')
                if not replacement['items'] and replacement['category'] != change['expected_category']:
                    raise ValueError('A removed skills group must preserve its snapshot category.')
                change.update(category=replacement['category'], items=deepcopy(replacement['items']))
            elif kind == 'bid':
                if not isinstance(replacement, str) or not replacement.strip():
                    raise ValueError('A bullet replacement must be nonempty text.')
                change['replacement'] = {'text': replacement, 'measurement': deepcopy(item['measurement']),
                                         'contribution_number': change['bullet_number']}
            else:
                if not isinstance(replacement, str) or not replacement.strip():
                    raise ValueError('A title/summary replacement must be nonempty text.')
                change['replacement'] = replacement
            changes.append(change)
            applied.append(finding(kind, value, target, 'repair', item.get('reason', 'Review correction')))
    for note in response.get('notes', []):
        kinds = [kind for kind in ('tid', 'psid', 'sid', 'bid') if kind in note]
        if len(kinds) != 1 or note.get('severity') not in {'advisory', 'factual_blocker'}:
            raise ValueError('Review notes need one typed ID and a note severity.')
        kind = kinds[0];target, _ = resolve(kind, note[kind])
        if note['severity'] == 'factual_blocker' and (kind, note[kind]) in seen:
            raise ValueError('A factual blocker cannot also be silently replaced.')
        findings.append(finding(kind, note[kind], target, note['severity'], note['issue']))
    return {'changes': changes, 'contract': 'typed_ids_v1'}, {
        'summary': response.get('review_summary', ''), 'findings': findings, 'applied_findings': applied}

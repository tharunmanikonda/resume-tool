"""Source-free, explicitly proposed JD drafting; independent of factual resumes."""
from copy import deepcopy
import resume_review_ids
import math
import re
import unicodedata
from difflib import SequenceMatcher
from decimal import Decimal
from resume_measurements import normalize_number_words, canonical_quantity, visible_ratio_matches_measurement

HEADINGS = ('key', 'company', 'location', 'dates', 'bullet_min', 'bullet_max')
MODE_POLICY_VERSION = 1
JD_SOURCE_VERSION = 5
WRITING_POLICY_VERSION = 2
PLANNING_POLICY_VERSION = 10
INTERNAL_LABEL_RE = re.compile(r'\b(?:illustrative(?:[_\s-]+unverified)?|unverified|needs[_-]user[_-]confirmation)\b', re.I)


def mode_context(mode):
    """Writing policy only: never hydrate source accomplishments into this mode."""
    mode = mode if mode in {'professional', 'internship', 'coop', 'new_grad'} else 'professional'
    label = {'professional': 'Professional', 'internship': 'Internship', 'coop': 'Co-op', 'new_grad': 'New Grad'}[mode]
    rules = [
        'Keep supplied employers and dates exactly. Saved employment titles are intentionally omitted from model input. Choose a proposed conventional functional title from each role story, responsibility and timeline; use the JD for relevant specialization, not unsupported seniority. Do not present a proposed functional title as a verified official title.',
        'Match the target headline to the advertised role. A senior JD does not authorize inventing senior responsibilities.',
        'Prioritize hands-on implementation, debugging, testing, delivery and collaboration; technical depth does not require leadership claims.',
        'Use the same JD-first project planning, concise XYZ writing and 80% numerical-evidence goal in every mode.',
        'Do not invent education, graduation dates, enrollment or eligibility. This draft does not include an education section.',
    ]
    if mode == 'professional':
        rules += ['Use experienced professional positioning; calibrate ownership to each historical title and its planned scope.']
    else:
        rules += [
            'Retain prior engineering experience and a mid-level individual-contributor tone; do not portray the candidate as a beginner.',
            'Avoid senior, staff, principal, tech-lead, people-management, organization-wide architecture or team-leadership positioning. Independent feature ownership, technical problem solving and collaboration are appropriate.',
            'If years of experience are mentioned in the summary, use 3+ years; do not invent a different total.',
            'Use past tense for completed roles and follow supplied dates; do not turn ended roles into current employment.',
        ]
        rules += {
            'internship': ['Target the advertised internship while retaining the substance of prior professional work.'],
            'coop': ['Target the advertised co-op while retaining the substance of prior professional work.'],
            'new_grad': ['Target the advertised new-graduate position with mid-level engineering substance. Do not add Intern or Co-op unless the JD itself does.'],
        }[mode]
    return {'resume_mode': mode, 'label': label, 'policy_version': MODE_POLICY_VERSION, 'writing_rules': rules}


def headings_only(roles):
    return [{key: deepcopy(role.get(key, '')) for key in HEADINGS} for role in roles]


def obj(properties):
    return {'type': 'object', 'additionalProperties': False, 'properties': properties, 'required': list(properties)}


STRING = {'type': 'string'}
STRINGS = {'type': 'array', 'items': STRING}
REQUIREMENTS = {'type': 'array', 'items': obj({'capability': STRING, 'jd_quote': STRING})}


_PREFERENCE = (r'\b(?:preferred|preferably|optional|not\s+(?:required|mandatory)|'
               r'advantageous|desirable|strong plus|is a plus|bonus|nice.to.have)\b')
_QUALIFICATION_MARKER = (r'\b(?:required|mandatory|preferred|preferably|optional|'
                         r'desirable|advantageous|is a plus|bonus|nice.to.have)\b')


def _top_level_positions(text):
    """Offsets outside parentheses/brackets, without changing source text."""
    depth, positions = 0, set()
    for offset, char in enumerate(text):
        if depth == 0:
            positions.add(offset)
        if char in '([':
            depth += 1
        elif char in ')]':
            depth = max(0, depth - 1)
    if depth == 0:
        positions.add(len(text))
    return positions


def qualification_parts(text):
    """Separate independently qualified requirements, preserving tool lists."""
    boundary = r'[,;]\s*(?:(?:but|and)\s+)?'
    top_level = _top_level_positions(text)
    result, start = [], 0
    for match in re.finditer(boundary, text, re.I):
        if (match.start() in top_level
                and not re.match(r'(?:including|using|such as|e\.g\.)\b', text[match.end():], re.I)
                and re.search(_QUALIFICATION_MARKER, text[start:match.start()], re.I)
                and re.search(_QUALIFICATION_MARKER, text[match.end():], re.I)):
            result.append(text[start:match.start()].strip())
            start = match.end()
    result.append(text[start:].strip())
    return result


_JD_SECTION = re.compile(
    r'(?<![a-z])(?:Preferred Qualifications|Preferred Skills|Bonus Skills|Bonus Qualifications|'
    r'Desirable Skills|Desirable Qualifications|Optional Skills|Nice[- ]to[- ]Have(?:s)?|'
    r'Basic Qualifications|Minimum Qualifications|Required Qualifications|Required Technical Skills|Must[- ]Have(?: Skills)?|'
    r'Technical Skills Required|Required Experience|Required Skills(?: & Experience)?|Experience Required|'
    r'Requirements(?: Qualifications)?|Qualifications|Responsibilities|'
    r'What You[’\']ll Do|Essential Functions|Your experience and qualifications|Development Stack|Benefits(?: \+ Perks)?|'
    r'Education and Work Experience|Knowledge,? Skills and Abilities|Job Overview|'
    r'Compensation Information|Salary Range|Travel(?=:)|(?-i:Preferred))(?=\s|:|[*_#]|(?-i:[A-Z])|$)'
    .replace('[- ]', r'(?:[-\u2010-\u2015]|\s+)').replace(' ', r'\s+'), re.I)
_JD_ITEM_START = (
    r'Design|Develop|Implement|Create|Maintain|Build|Integrate|Work|Write|Own|'
    r'Simplify|Promote|Upgrade|Review|Document|Train|Contribute|Mentor|Lead|'
    r'Experience|Knowledge|Understanding|Proficiency|Familiarity|Ability|'
    r'Strong experience|Excellent communication|Evidence|Comfort|A collaborative|'
    r'Cloud migration|Knowledgeable|Hands-on|Working knowledge|Solid understanding|'
    r'Proven experience|Demonstrated experience')


def _jd_section_matches(jd):
    """Generic words in prose (e.g. customer requirements) are not headings."""
    for match in _JD_SECTION.finditer(jd):
        label = match.group()
        if label.casefold() in {'requirements', 'qualifications', 'responsibilities', 'benefits', 'preferred'}:
            tail = jd[match.end():]
            line_start = not jd[:match.start()].rsplit('\n', 1)[-1].strip(' \t#*_+-0123456789.)')
            delimiter = bool(re.match(r'[*_]*[ \t]*[:\r\n]', tail))
            # Recover flattened headings only with heading casing and a list
            # starter, not inside Business Requirements Documentation (BRD).
            starter = re.match(r'\s*(?:' + _JD_ITEM_START + r'|[0-9]|EDI\b)', tail)
            if label.casefold() == 'requirements':
                starter = re.match(r'\s*(?:Experience|Knowledge|Understanding|Proficiency|Familiarity|'
                                   r'Ability|Strong|Excellent|Working|Hands-on|Build|Develop|Design|[0-9])\b', tail)
            if not (line_start or delimiter or (label[0].isupper() and starter)):
                continue
        yield match


def _jd_clause_records(jd):
    """Keep original text while recovering section and glued list boundaries."""
    headings = list(_jd_section_matches(jd))
    starts = sorted(set([0] + [m.start() for m in headings] + [len(jd)]))
    records = []
    for start, end in zip(starts, starts[1:]):
        section = jd[start:end]
        heading = next((m.group() for m in headings if m.start() == start), '')
        semantic_heading = re.sub(r'\s+', ' ', heading)
        if re.match(r'Preferred|Nice|Bonus|Desirable|Optional', semantic_heading, re.I):
            priority = 'optional'
        elif re.match(r'Benefits|Compensation|Salary|Travel|Job Overview|Education and Work Experience', semantic_heading, re.I):
            priority = 'context'
        elif heading.casefold() == 'development stack':
            priority = 'required'
        else:
            priority = 'required' if heading else None
        boundary = (
            r'(?<=[.!?])\s+(?!\s*(?i:\((?:required|preferred)\)))|'
            r'(?<=[.!?])(?=[A-Z][a-z])|[\r\n]+(?!\s*(?i:\((?:required|preferred)\)))|'
            r'(?i:(?<=\(required\))[,;]?\s*|(?<=\(preferred\))[,;]?\s*)|'
            r'(?<=[a-z0-9)])(?=(?:' + _JD_ITEM_START + r')\b)|'
            r'(?<=[A-Z])(?=(?:Experience|Knowledge|Understanding|Proficiency)\b)')
        # Do not split example sentences or technology lists inside parentheses.
        # Split only the body, so a heading wrapped over lines stays intact.
        body = section[len(heading):]
        top_level = _top_level_positions(body)
        cuts = [(m.start(), m.end()) for m in re.finditer(boundary, body) if m.start() in top_level]
        spans, begin = [], 0
        for split_start, split_end in cuts:
            spans.append((begin, split_start))
            begin = split_end
        spans.append((begin, len(body)))
        sentences = []
        for begin, finish in spans:
            sentence = body[begin:finish]
            if not re.search(r'\w', sentence):
                continue
            if heading and not sentences:
                sentence = section[:len(heading) + finish]
            sentences.append(sentence)
        for sentence in sentences:
            for part in qualification_parts(sentence):
                if part.strip():
                    annotation = re.search(r'\((required|preferred)\)\s*$', part, re.I)
                    local_priority = ('required' if annotation[1].casefold() == 'required' else 'optional') if annotation else priority
                    records.append((part.strip(), local_priority))
    return records


def jd_clauses(jd):
    return list(dict.fromkeys(text for text, _ in _jd_clause_records(jd)))


def jd_clause_priorities(jd):
    """Section context is separate from the exact evidence text."""
    records = _jd_clause_records(jd)
    return {key: next(priority for text, priority in records if text == quote)
            for key, quote in jd_clause_map(jd).items()}


def _label_terms(text):
    stop = {'and', 'or', 'the', 'with', 'for', 'to', 'in', 'of', 'a', 'an', 'be',
            'experience', 'using', 'work', 'knowledge', 'strong', 'implement', 'develop'}
    return {word.rstrip('s') for word in re.findall(r'[\w#+]+', text.casefold())
            if word not in stop and len(word) > 1}


def _narrow_quote(quote, capability, clauses):
    """Recover a local citation from a saved broad quote; never expand its label."""
    norm = lambda text: re.sub(r'\s+', ' ', text).strip()
    candidates = [text for text in clauses if norm(text) in norm(quote)]
    if len(candidates) < 2:
        return quote
    if norm(capability) == norm(quote):
        return quote
    terms = _label_terms(capability)
    scores = [(len(terms & _label_terms(text)), text) for text in candidates]
    best = max(score for score, _ in scores)
    winners = [text for score, text in scores if score == best]
    return winners[0] if best and len(winners) == 1 else quote


def jd_clause_map(jd):
    return {f'jd_{i + 1}': text for i, text in enumerate(jd_clauses(jd))}


def normalize_plan(plan, jd):
    """Ground display labels in their selected source clause, without paraphrase gates."""
    result = deepcopy(plan)
    # Keep existing writer/targeting exact-string replacement contracts. Older
    # cached plans already use strings; normalize structured notes once locally.
    for entry in result.get('experience', {}).values():
        if 'contributions' not in entry:
            continue
        entry['contributions'] = [
            ' | '.join(str(note.get(k, '')).strip() for k in ('work', 'outcome', 'measurement'))
            if isinstance(note, dict) else note
            for note in entry.get('contributions', [])]
    norm = lambda text: re.sub(r'\s+', ' ', str(text)).strip()
    def typography(text):
        text = unicodedata.normalize('NFKC', norm(text)).casefold()
        text = text.translate(str.maketrans({'’': "'", '‘': "'", '–': '-', '—': '-', '‑': '-', '‐': '-'}))
        return text.strip(' .!?:;')
    clauses = jd_clauses(jd)
    clause_map = jd_clause_map(jd)
    for level in ('required', 'optional'):
        for req in result.get(level, []):
            if (req.get('source_clause_id') in clause_map
                    and (not req.get('jd_quote') or norm(req['jd_quote']) not in norm(jd))):
                req['jd_quote'] = clause_map[req['source_clause_id']]
            quote = norm(req.get('jd_quote', ''))
            if quote and quote not in norm(jd):
                matches = [c for c in clauses if typography(c) == typography(quote)]
                if len(matches) == 1:
                    req['jd_quote'] = matches[0]
                    quote = norm(matches[0])
            if quote and quote in norm(jd):
                req['jd_quote'] = _narrow_quote(req['jd_quote'], req.get('capability', ''), clauses)
                # Clause numbering may change when a flattened posting is split.
                matches = [key for key, text in clause_map.items() if norm(text) == norm(req['jd_quote'])]
                if len(matches) == 1 and req.get('source_clause_id'):
                    req['source_clause_id'] = matches[0]
    return result


def plan_schema(roles, jd=None):
    return obj({
        'role_positioning': STRING,
        'engineering_focus': {'type': 'array', 'items': STRING, 'minItems': 1, 'maxItems': 5},
        'career_alignment': obj({
            'specialization': STRING,
            'requires_sustained_specialization': {'type': 'boolean'},
            'support_status': {'type': 'string', 'enum': ['established', 'unestablished', 'not_required']},
            'gap': STRING,
        }),
        'experience': obj({role['key']: obj({
            'title': STRING, 'system': STRING, 'workflow': STRING, 'scope': STRING,
            'assumptions': {'type': 'array', 'items': STRING, 'maxItems': 3},
        }) for role in roles}),
    })


TARGETING_PROMPT = '''Independently check whether this proposed project plan targets the JOB, before resume writing. The proposed_plan is fallible; do not approve it merely because its stories are coherent. Read the original JD clauses and their separate section priorities first, then compare the proposed plan.
First distinguish the advertised levels, alternative teams/platforms, core requirements and preferred strengths. Choose a conservative writing scope from the JD and supplied employment dates and project scope. Dates establish chronology, not expertise, leadership or eligibility. If the exact level/team is not established, explicitly label the choice a conservative assumption; choose a usable common core instead of blocking generation. Do not combine requirements from mutually alternative teams or apply senior-only requirements to all levels.
Judge the primary project, headline positioning and recent contributions against the selected path's required work. Check whether preferred/bonus technologies used by the plan fit the actual proposed system, workflow, responsibility and timeline. Their omission is not a defect when they do not fit the story. If a capability naturally belongs to existing work but was excluded only because it was labelled optional, return an exact contribution replacement incorporating that use. Never manufacture a workflow or responsibility to cover a preferred keyword; remove forced uses instead. Do not remove a useful technology solely because the JD calls it preferred or a plus. Preserve the job's engineering needs, not its business narrative. Historical projects must keep their independently selected purpose, users and workflow. Do not transplant target-company business into a role to improve alignment. A JD mentioning AI tools, preferred RAG/MCP or an AI team does not automatically make the primary role AI engineering. Equally, preserve RAG/MCP as primary when the selected role explicitly requires that work; there is no blanket AI ban. Older roles retain period-appropriate responsibility and technology scope.
Return a compact assessment: level_scope, team_path, choice_basis, primary_focus, secondary_focus, excluded_paths and rationale. Use at most 5 primary and 3 secondary focuses; each focus cites a source_clause_id and uses at most 10 words. Keep other assessment strings under 25 words and excluded_paths at most 3 short items.
If the direction is wrong, return exact replacements for ONLY the affected fields present in the plan. New plans contain project context only: correct purpose, workflow, scope, stack assumptions or title; do not add numbered contribution notes. For older plans with existing notes, correct them only when necessary. Correct stale role assumptions when changing project direction; do not leave an obsolete stack steering the writer. Do not return a whole new plan, rewrite sound work, add unrelated tools, or invent observed achievements/measurements. JD-preferred technologies can be incorporated through a concrete planned use only when they naturally fit the story; no preferred-skill coverage quota. Each contribution remains a compact action | mechanism | intended result | measurement opportunity note, at most 25 words. Preserve role keys, employers/dates, contribution counts and career progression. Check each proposed experience title against its own corrected story; return an exact title correction when the generic supplied label no longer describes that work. Choose meaningful work, not generic delivery claims or a technology inventory. Keep a role-level system/workflow narrative coherent after changes. Decision corrected needs replacements; aligned needs none. This assessment is a proposed writing direction, not verified candidate fit or a hiring prediction.'''


def targeting_schema(roles, jd, plan=None):
    focus = obj({'source_clause_id': {'type': 'string', 'enum': list(jd_clause_map(jd))}, 'focus': STRING})
    schema = obj({'decision': {'type': 'string', 'enum': ['aligned', 'corrected']},
                'assessment': obj({
                    'level_scope': STRING, 'team_path': STRING,
                    'choice_basis': {'type': 'string', 'enum': ['explicit_jd_scope', 'conservative_assumption']},
                    'primary_focus': {'type': 'array', 'items': focus, 'minItems': 1, 'maxItems': 5},
                    'secondary_focus': {'type': 'array', 'items': focus, 'maxItems': 3},
                    'excluded_paths': {'type': 'array', 'items': STRING, 'maxItems': 3}, 'rationale': STRING}),
                'corrections': {'type': 'array', 'items': {'anyOf': [
                    obj({'target': {'type': 'string', 'enum': ['role_positioning', 'target_system', 'target_workflow']},
                         'old_text': STRING, 'replacement': STRING}),
                    obj({'target': {'type': 'string', 'enum': ['title', 'system', 'workflow', 'scope']},
                         'role_key': {'type': 'string', 'enum': [r['key'] for r in roles]},
                         'old_text': STRING, 'replacement': STRING}),
                    obj({'target': {'type': 'string', 'enum': ['contribution']},
                         'role_key': {'type': 'string', 'enum': [r['key'] for r in roles]},
                         'contribution_number': {'type': 'integer', 'minimum': 1}, 'old_text': STRING, 'replacement': STRING}),
                    obj({'target': {'type': 'string', 'enum': ['assumptions']},
                         'role_key': {'type': 'string', 'enum': [r['key'] for r in roles]},
                         'old_assumptions': STRINGS, 'replacement': {'type': 'array', 'items': STRING, 'minItems': 1, 'maxItems': 3}}),
                ]}}})

    if plan is not None:
        variants = schema['properties']['corrections']['items']['anyOf']
        variants[0]['properties']['target']['enum'] = [key for key in ('role_positioning', 'target_system', 'target_workflow') if key in plan]
        note_roles = [key for key, entry in plan.get('experience', {}).items() if entry.get('contributions')]
        if not note_roles:
            variants[:] = [v for v in variants if v['properties']['target']['enum'] != ['contribution']]
        else:
            variants[2]['properties']['role_key']['enum'] = note_roles
    return schema


def apply_targeting_check(plan, result, jd):
    corrected = deepcopy(plan)
    changes = result['corrections']
    if result['decision'] not in {'aligned', 'corrected'} or (result['decision'] == 'aligned') != (not changes):
        raise ValueError('Targeting decision must agree with its exact corrections.')
    seen = set()
    for change in changes:
        field = change['target']
        role = change.get('role_key')
        if field in {'role_positioning', 'target_system', 'target_workflow'}:
            container, key = corrected, field
            identity = (field,)
        else:
            if role not in corrected.get('experience', {}):
                raise ValueError('Targeting correction refers to a missing role.')
            entry = corrected['experience'][role]
            if field == 'contribution':
                number = change['contribution_number']
                if not isinstance(number, int) or not 1 <= number <= len(entry['contributions']):
                    raise ValueError('Targeting correction refers to a missing contribution.')
                container, key = entry['contributions'], number - 1
                identity = (field, role, number)
            elif field in {'title', 'system', 'workflow', 'scope', 'assumptions'}:
                container, key = entry, field
                identity = (field, role)
            else:
                raise ValueError('Unknown targeting correction field.')
        replacement = change['replacement']
        valid_replacement = (bool(replacement) and all(isinstance(v, str) and v.strip() for v in replacement)) if field == 'assumptions' else bool(replacement.strip())
        if identity in seen or container[key] != change.get('old_text', change.get('old_assumptions')) or not valid_replacement:
            raise ValueError('Targeting correction is duplicated, stale or empty.')
        seen.add(identity)
        container[key] = change['replacement']
    assessment = deepcopy(result['assessment'])
    clauses = jd_clause_map(jd)
    for level in ('primary_focus', 'secondary_focus'):
        for focus in assessment[level]:
            if focus['source_clause_id'] not in clauses:
                raise ValueError('Targeting focus must reference the actual JD.')
            focus['jd_quote'] = clauses[focus['source_clause_id']]
    return corrected, assessment


def draft_schema(roles, skill_categories=None):
    bullet = obj({'measurement': obj({'kind': {'type': 'string', 'enum': ['improvement', 'scale', 'qualitative']},
                                      'value': STRING, 'unit': STRING, 'context': STRING,
                                      'status': {'type': 'string', 'enum': ['illustrative_unverified', 'qualitative']}}),
                  'contribution_number': {'type': 'integer', 'minimum': 1},
                  'text': {'type': 'string', 'pattern': r'^\s*\S+(?:\s+\S+){24,29}\s*$',
                           'description': 'One complete 25-30 word contribution, mechanism and outcome. Hyphenated words count as one.'}})
    return obj({'headline': STRING, 'summary': STRING,
        'skills': {'type': 'array', 'minItems': 1, 'items': obj({
            'category': {'type': 'string', 'enum': sorted(skill_categories)} if skill_categories else STRING,
            'items': {'type': 'array', 'items': STRING, 'minItems': 2}})},
        'experience': obj({role['key']: obj({
        'bullets': {'type': 'array', 'items': bullet, 'minItems': role['bullet_min'], 'maxItems': role['bullet_min']},
    }) for role in roles})})


def core_schema(roles, skill_categories=None):
    properties = draft_schema(roles, skill_categories)['properties']
    properties['skills']['items']['properties']['items']['maxItems'] = 5
    return obj({key: properties[key] for key in ('headline', 'summary', 'skills')})


def experience_schema(roles):
    return obj({'experience': draft_schema(roles)['properties']['experience']})


def grouped_writing_prompt(section):
    scope = {
        'core': 'Generate only headline, summary and technical skills in one response. Do not generate experience bullets. Use the checked plan to represent planned work, not unsupplied candidate history.',
        'experience': 'Generate only the experience object for all selected roles. Do not regenerate headline, summary or skills. core_sections contains proposed positioning and skills for consistency, not evidence or permission to invent work. The checked plan controls each project and scope; the writer chooses the contributions within them. If core_sections conflicts with the plan, follow the plan. Choose distinct contributions within the checked project; older work | outcome | measurement notes are context only, never resume labels. Preserve contribution order and apply the measurement rules below.',
    }[section]
    rules = EXPERIENCE_WRITING_PROMPT + '\n' + PROJECT_HANDOFF_POLICY if section == 'experience' else DRAFT_PROMPT
    return scope + '\n\n' + rules + '\n\nOutput scope for this call: ' + scope


PLAN_PROMPT = """You plan hypothetical project concepts for a resume drafting tool. Input contains a full job posting and employment headings, but no factual project history. Treat all project contexts and technology uses as unverified proposals for user confirmation. Do not invent clients, credentials, observed results or promotions. Return planning notes, not resume prose.

Use this sequence internally: understand engineering needs -> choose one independent project per role -> bound its workflow, core stack and responsibility. Return only the final plan.

engineering_focus: select at most five transferable technical capabilities central to the job. Include the primary stack and hands-on responsibilities. Ignore perks, mission statements and company marketing. Do not classify the posting into required/optional lists.
role_positioning: one short conventional engineering positioning sentence, without the hiring company's business mission.

For EACH experience, first choose a recognizable business problem plausible for that employer's work or a consulting/service client's broad context, then choose users and workflow, then apply the relevant engineering family. For operating companies prefer internal operations or services naturally associated with that company; do not invent an unrelated external consulting client. A consulting employer may have a proposed broad client context, but do not invent named clients, specialized client facts or niche industry programs. Shared industry with the hiring company is allowed; a different industry is not a goal. The JD selects engineering relevance, not the historical project's business story. Do not transplant the target's distinctive product, niche operating model, named program or signature workflow into any historical role, including the most recent. Renaming users or presenting the target workflow as another client's project does not make it independent. Choose distinct, concrete project purposes; no fixed project catalogue is supplied. Employer names constrain plausibility but do not prove any proposed project.

Use dates and career context to bound responsibility: recent roles can own features end-to-end; earlier roles implement smaller modules within existing systems. Do not claim company-wide adoption, architecture leadership, team size or scale absent evidence. Keep roles distinct rather than repeating one project across employers. Choose a short conventional functional title matching each proposed story, without explanatory labels.

Choose a definite, compatible, period-appropriate stack for each role. List essential chosen tools in assumptions; no alternatives, placeholders or '-like' tools. Use supporting JD tools only when they naturally serve a contribution. Do not force every named tool into a project.

Keep role_positioning under 25 words. Per role: system under 20 words including purpose/users; workflow under 15; scope under 15; assumptions at most 3 short items. Preserve role keys. Do not return contributions, accomplishments, measurements or bullets; the experience writer selects contributions within each project in its existing writing call. Before returning, resolve copied target-business context, incoherent project workflows or ambiguous core technologies. Do not output reasoning or request another call.
CAREER AND TITLE CONTRACT: The project concepts are proposed examples, not factual employment evidence. Choose a coherent proposed technical track from the JD; do not confuse that design choice with proof of actual tenure. Preserve a coherent technical career family, not every current framework, service or AI capability across all roles. A stable specialist platform may continue through the proposed timeline with smaller responsibilities and period-appropriate capabilities. For a role using newer AI/agent techniques, recent work may use those techniques while earlier work demonstrates the relevant language, APIs, data processing, application integration and testing foundations. General SaaS experience requirements do not imply equal years of LLM/RAG/agent work. Choose tools and product capabilities plausible within each supplied employment period; omit a specific technology when its period suitability is uncertain rather than assume availability. Reduce responsibility backward: recent roles deliver features/integrations; earlier roles implement assigned components, validation, flows, tests and fixes in existing systems. Do not abandon an established platform family merely to signal less experience, and do not backdate modern specialist features merely to keep every role identical. Do not extend dates or claim the JD's required years. Return career_alignment.support_status as unestablished for required specialist tenure because only employment headings are supplied, and explain that gap briefly. This assessment must not silently substitute general development years for specialist years.
Keep each business purpose independently coherent and plausible for its employer/client context. Ordinary projects in a shared industry are acceptable; do not force industry differences or confuse relevant industry experience with copying the target's distinctive project. Recognize explicit industry qualifications without manufacturing evidence of them. Most-recent work is subject to the same independence rule. Distinct projects may use the same core platform while business purposes and responsibility boundaries differ.
Choose each proposed functional title after choosing that role's work and responsibility, using supplied dates and career context to calibrate level. Do not default every role to the same unlevelled title. For an established first-career period with assigned components, a conventional Associate or Junior title may fit; independent feature delivery fits an ordinary developer/engineer title, and broader implementation responsibility may fit Engineer II when that is a conventional title for the family. In a multi-role timeline, prefer an Associate or Junior title for the initial role when its planned work is assigned components and bug fixes and no prior experienced-career context is supplied. These are possible levels, not a mandatory ladder: repeated titles are valid where responsibility is comparable. Dates alone do not establish a promotion, seniority or specialist tenure. A single selected recent role is not automatically junior. Preserve the technical career family; do not change platforms to manufacture title growth. Use only short real-world titles; do not stack qualifiers, invent hybrid labels or import Senior, Lead, Architect or Manager from the target JD without supporting career context. These are proposed functional labels, not verified official titles or promotion history.
For the first career period shown by a multi-role progression, keep the proposed responsibility to assigned components and small workflow fixes in a team-maintained application. Do not infer architecture ownership, platform governance, broad service capacity or tool selection from the target JD. A single selected recent role is not automatically entry level. Prefer a small concrete system/workflow over an inventory of responsibilities. Return the existing schema only; no contributions, reasoning or bullets. Before returning, check platform continuity, business-context independence, ordinary titles and bounded earlier-career work together."""

DRAFT_PROMPT = '''Write an experimental proposed resume from the checked JD plan, not verified work history. There are no candidate source accomplishments or measurements. Do not invent source citations or claim these are confirmed facts.
Use targeting_assessment when supplied: primary_focus controls headline, summary and strongest recent contributions; secondary_focus stays supporting. Respect its selected level/team and excluded paths. Do not treat an optional technology as the role identity merely because a historical title mentions it.
Apply resume_mode_context.writing_rules to headline, summary and every bullet, including repairs. Student/new-graduate modes retain mid-level engineering substance without senior or leadership positioning.
Write a normal advertised-role headline and professional summary. Resume-facing headline, summary, skills and bullet text must never contain illustrative_unverified, illustrative, unverified, confirmation requests or internal status labels. Factual status belongs ONLY in measurement.status and the application's review notes, never in a sentence. Write 'reduced workflow exceptions by 37%', NEVER 'by an illustrative_unverified 37%'. A clean sentence does not mean the example has been factually verified.
SKILLS: Answer what languages and technologies this person would be hands-on with in the checked project plan. Include only the strongest relevant, believable day-to-day skills. Do not overfill with every plausible JD-adjacent tool. Use only ordered_skill_categories when supplied, keep their order, and omit categories without two strong relevant items. Do not fill every allowed category. Use 2-5 short items per included category. Each item names exactly one conventional language, framework, database, tool, platform, protocol or concise capability: no explanations, qualifiers, mini-sentences, packed lists or project descriptions. Keep established names such as CI/CD intact. Example: Programming Languages: Java, SQL, JavaScript; Backend Engineering: Spring Boot, REST APIs; Testing & Quality: Unit testing, Integration testing. Avoid repeating a skill or concept across categories. Prefer exact technology names over abstract phrases; show collaboration and routine process activities in experience, not extra skill categories. Select the primary JD-aligned stack from the planned mechanisms; do not add tools merely because they occur in the JD, and do not invent frameworks or infer source skills. These remain proposed skills, not verified history.
Within each checked project, choose distinct important contributions and write exactly bullet_min bullets, numbered from 1 within that role. No contribution notes are supplied by the new planner. Older saved plans may contain notes; preserve their order when present, narrowing overstated claims without changing their work. Keep every role within its planned project and scope. Do not turn every role into leadership or assign every platform to every role.
Use concise natural XYZ bullets: important implemented contribution, relevant technical mechanism, and impact or scale where useful. Do not require an entire architecture, baseline methodology or proof of every intermediate step inside a sentence. Flag misleading attribution, not brevity.
Aim for numerical evidence in at least 80% of bullets per role. Every generated measurement is a proposed example: set ONLY the separate measurement.status field to illustrative_unverified. Never copy that field's value or its explanation into text. Use useful scale or improvement quantities, never JD company membership/employee counts. Do not count 'one service/schema/sync/toolset' as evidence of scale merely to reach the goal. Counts of multiple integrations, services or tests can be meaningful scope when their purpose is clear; a count is not automatically padding. Software versions are not measurement evidence. Do not fabricate sources or call illustrative values observed outcomes. If meaningful quantification is unsuitable, retain qualitative work and accept an advisory shortfall.
Measurements must preserve meaning, units and qualifiers within this draft. A final-state latency is scale/performance evidence, not necessarily an improvement. A qualitative record has empty value/unit and status qualitative. A quantitative record names its value, unit, context and status illustrative_unverified. Its numbers must appear in the bullet. Never put confirmation questions or measurement placeholders in bullets.
Compose the finished sentence, then copy its primary visible value and matching unit into the measurement record; do not calculate a hidden percentage from endpoints; the whole draft is already labelled proposed/unverified. If you choose qualitative text instead, clear the measurement value/unit and use qualitative kind/status. Do not retain an invisible number in metadata. In a repair, either insert the already proposed illustrative quantity naturally or explicitly demote the record to qualitative; preserve the contribution and never add a second accomplishment just to fit a number.
Every experience bullet must contain 25-30 whitespace-separated words, inclusive. Hyphenated expressions count as one word. Count and revise each bullet before returning, including repairs. Use the space for the important work, technical mechanism and useful outcome; never add filler, another accomplishment or an invented tool to meet length. A test or pipeline pass rate alone is not evidence that a change prevented regressions or improved reliability. Earlier roles show transferable foundations rather than repeating the target product/domain everywhere. Do not add authority such as Led or Owned beyond the plan. AI-assisted development can be relevant without agentic AI becoming the main professional identity. Use preferred/bonus technologies only through concrete contributions that naturally fit the checked project; do not omit them merely because their JD priority is optional, and do not add unplanned preferred technologies or force a use to cover a keyword. Preserve the project scope and main workflow. Return only the schema.'''

REVIEW_PROMPT = '''Review the complete experimental proposed resume against its raw JD and project plan. These are hypothetical scenarios and illustrative measurements, not confirmed candidate history. Do not demand source citations or declare the work factual.
The application already displays one overall factual-status notice. Do not create repeated findings asking to confirm each proposed percentage, technology or project simply because no source history exists. Assess the usefulness and meaning of a measure, causal wording and technical consistency. A count of multiple services, integrations or tests is not automatically numerical padding. Internal status labels inside resume text are a writing error that must be repaired, not retained next to every number.
Check that technical skills use concrete conventional skill names rather than vague descriptions of projects, and that important required technologies are represented by the proposed work. Flag missing technical substance, but do not demand keyword stuffing or a full project explanation inside each bullet.
Check headline, summary, experience titles, project scope and bullets against resume_mode_context.writing_rules. Each experience title must be a conventional label for that role's actual proposed story and responsibility. Correct a generic Full Stack Developer title when its planned work is specifically Salesforce development. Do not force the target title onto unrelated older projects or invent seniority/promotion. Flag senior/leadership inflation in student/new-graduate modes, but preserve mid-level implementation depth, independent feature ownership and prior experience. Do not demand beginner wording merely because the target is New Grad, Internship or Co-op.
Judge whether the main job workflow is represented, preferred/bonus technologies selected for a natural fit appear through their uses in the checked plan, with no penalty for omitting those that do not fit, each role has a coherent project, contributions are distinct and scope fits the heading. Do not remove planned technical work solely because the JD described it as preferred or a plus. Check for excessive platforms/tools/leadership, repeated accomplishments, numerical padding and misleading action/result attribution. Every experience bullet must contain 25-30 whitespace-separated words, inclusive; apply the same limit to every replacement. Inspect per-role numerical_goal_notes and do not remove useful measurements without checking the remaining coverage and explaining a genuine shortfall. Do not repeat the specialist target project in every early-career role. Test pass rates alone do not establish regression prevention.
A concise resume bullet is not a case study: do not demand the whole architecture, every intermediate step, missing baselines or measurement methodology. A clear contribution, credible mechanism and relevant impact/scale can be sufficient. Missing intermediate detail alone is not a finding.
Return concise, actionable findings only. Preserve sound bullets. Do not invent additional project facts or measurements to repair the story. ready_for_assumption_review means suitable for reviewing proposed facts, never verified or ready to submit. No ATS score or hiring prediction.'''


HEADLINE_POLICY = """MAIN RESUME TITLE: Use one short, conventional job title naturally used for this role. Prefer the advertised JD title; if it contains a recruitment slogan, company/team/location text or a technology inventory, use its standard role equivalent. Examples: Software Engineer, Software Engineer II, Full Stack Developer, Backend Engineer, AI Engineer. Preserve a specialization or level that belongs to the actual title and follows the selected mode; do not invent extra seniority. Do not append a stack, pipe-separated keywords, selling points, project descriptions, multiple alternative titles or extra specialties. Keep technical detail in summary, skills and bullets. The plan's role_positioning describes direction and is not a sentence to copy into the headline. This headline rule is separate from experience titles: choose each proposed functional experience title from its own planned project and scope. Preserve explicit user title overrides."""
DRAFT_PROMPT += '\n' + HEADLINE_POLICY
REVIEW_PROMPT += '\n' + HEADLINE_POLICY + '\nIf the main title is expanded or unnatural, return an exact headline replacement with the conventional JD-aligned title. Do not expand an already suitable title.'


def review_targets(draft):
    targets = {key: str(draft.get(key, '')) for key in ('headline', 'summary')}
    targets['skills'] = '\n'.join(g['category'] + ': ' + ', '.join(g['items']) for g in draft.get('skills', []))
    for i, group in enumerate(draft.get('skills', []), 1):
        targets[f'skills:{i}'] = group['category'] + ': ' + ', '.join(group['items'])
    for key, entry in draft.get('experience', {}).items():
        if entry.get('title'):
            targets[f'title:{key}'] = entry['title']
        for i, bullet in enumerate(entry.get('bullets', []), 1):
            targets[f'bullet:{key}:{i}'] = bullet.get('text', '') if isinstance(bullet, dict) else str(bullet)
    return targets


def finding_schema(draft):
    return obj({'target_id': {'type': 'string', 'enum': list(review_targets(draft))},
                'severity': {'type': 'string', 'enum': ['repair', 'advisory', 'factual_blocker']}, 'issue': STRING})


def review_schema(draft=None):
    if draft is not None:
        return obj({'summary': STRING, 'ready_for_assumption_review': {'type': 'boolean'},
                    'findings': {'type': 'array', 'items': finding_schema(draft)}})
    return obj({'summary': STRING, 'ready_for_assumption_review': {'type': 'boolean'},
                'findings': {'type': 'array', 'items': obj({'role_key': STRING, 'bullet_number': {'type': 'integer', 'minimum': 0}, 'issue': STRING})}})


def review_apply_schema(roles, draft, skill_categories=None):
    bullet = draft_schema(roles, skill_categories)['properties']['experience']['properties'][roles[0]['key']]['properties']['bullets']['items']
    return resume_review_ids.response_schema(resume_review_ids.snapshot(draft), bullet, skill_categories)


REVIEW_APPLY_PROMPT = """Review and return only necessary replacements using the supplied review_items and snapshot_id. Copy the snapshot_id and the item's integer ID exactly. IDs have separate types: tid for a title (main headline or a role title as labelled in review_items), psid for the professional summary, sid for a skills group, bid for an experience bullet. bid values are unique across all selected roles. Never calculate a new ID, restart bullet IDs for each company, or use an item position as its ID.
Return titles, summaries, skills and bullets arrays; use empty arrays for unchanged sections. Each replacement carries its own reason. Do not return findings, change_indices, role_key, bullet_number, old_text, a whole resume, or a separate replacement-link table. Copy the ID from the item being corrected, even when returning only bids 12, 15 and 18 or returning them out of order.
For tid and psid, replacement is the complete corrected title or summary. tid 1 is the main headline; additional tids identify experience titles by the supplied role_key. Never derive a tid from bid numbering. For sid, replacement is the complete corrected category/items group. For bid, replacement is one complete corrected bullet, with consistent measurement metadata; the code supplies its contribution number. Preserve sound wording, useful quantities, project scope, selected mode, contribution count and career progression. Do not add/delete/reorder bullets or titles. To remove a redundant skills group, return its sid with its original category and an empty items array; merge useful existing skills into retained groups in the same response. Skill IDs always refer to the original snapshot, before removals. Retained groups need 2-5 items; keep at least one group. All replacement bullets follow the supplied writing rules, including 25-30 words. Measurement status stays in metadata, not visible prose.
Put optional advice and genuine unresolved factual blockers in notes using the same typed IDs; ordinary writing defects belong directly in replacements. Do not demand the whole project story or a full measurement methodology inside a bullet. Do not remove useful measurements merely to prefer qualitative wording. Conventional technical skills are valid even if they are not product names. Hypothetical project assumptions alone are not factual blockers. No extra repair writer or second review call is needed: the application validates and applies these replacements directly."""


def decode_review_response(response, saved, draft):
    if 'snapshot_id' in response:
        return resume_review_ids.decode(response, saved, draft)
    # Read-only compatibility for stored pre-migration responses. New API
    # schemas never request the legacy finding/index contract.
    legacy = identify_findings(response, draft)
    changes = legacy.get('changes', [])
    revised = apply_repairs(draft, {'changes': changes})
    targets = {patch_target(change) for change in changes}
    for finding in legacy.get('findings', []):
        if finding['severity'] == 'repair' and not any(target_matches(finding, target) for target in targets):
            raise ValueError('Review omitted a replacement for a repair finding.')
    wire = {'snapshot_id': saved['snapshot_id'], 'review_summary': legacy.get('summary', ''),
            'titles': [], 'summaries': [], 'skills': [], 'bullets': [], 'notes': []}
    bid_by_location = {location: bid for bid, location in saved['locations'].items()}
    def typed_target(target):
        if target == 'headline': return 'tid', 1
        if target == 'summary': return 'psid', 1
        if target.startswith('skills:'): return 'sid', int(target.split(':')[1])
        if target.startswith('bullet:'):
            _, role, number = target.split(':')
            return 'bid', bid_by_location[(role, int(number)-1)]
        return 'psid', 1  # Old whole-skills advice remains a non-editing note.
    summary_done = False
    for change in changes:
        target = patch_target(change)
        kind, value = typed_target(target)
        owners = [f for f in legacy.get('findings', []) if target_matches(f, target)]
        if any(f['severity'] == 'factual_blocker' for f in owners):
            raise ValueError('A factual blocker cannot be silently replaced.')
        reason = owners[0]['issue'] if owners else 'Review correction'
        item = {kind: value, 'reason': reason}
        if kind == 'bid':
            item.update(replacement=change['replacement']['text'], measurement=deepcopy(change['replacement']['measurement']))
            wire['bullets'].append(item)
        elif kind == 'sid':
            item['replacement'] = {key: deepcopy(change[key]) for key in ('category', 'items')}
            wire['skills'].append(item)
        elif kind == 'tid':
            item['replacement'] = change['replacement'];wire['titles'].append(item)
        elif not summary_done:
            item['replacement'] = revised['summary'];wire['summaries'].append(item);summary_done = True
    for finding in legacy.get('findings', []):
        if any(target_matches(finding, target) for target in targets): continue
        kind, value = typed_target(finding['target_id'])
        wire['notes'].append({kind: value, 'severity': finding['severity'], 'issue': finding['issue']})
    return resume_review_ids.decode(wire, saved, draft)


def identify_findings(review, draft, prefix='finding'):
    targets = review_targets(draft)
    result = deepcopy(review)
    for i, finding in enumerate(result.get('findings', []), 1):
        target = finding.get('target_id')
        if not target:  # Compatibility with previously saved review objects.
            role, number = finding.get('role_key'), finding.get('bullet_number', 0)
            target = f'bullet:{role}:{number}' if role in draft.get('experience', {}) and number else role
        if target not in targets:
            raise ValueError('Review finding must identify an existing exact target.')
        if finding.get('severity', 'repair') not in {'repair', 'advisory', 'factual_blocker'}:
            raise ValueError('Unknown review finding severity.')
        finding.update(finding_id=f'{prefix}-{i}', target_id=target, current_text=targets[target],
                       severity=finding.get('severity', 'repair'))
        if target.startswith('bullet:'):
            _, role, number = target.split(':')
            finding.update(role_key=role, bullet_number=int(number))
        else:
            finding.update(role_key=target.split(':')[0], bullet_number=0)
    return result


REVIEW_COORDINATION = '''Use review_targets as the authoritative target table. Copy target_id exactly; bullet IDs are explicitly ONE-BASED. Do not calculate a bullet position from an unnumbered list. Report all material issues in this first pass, including technical consistency and incorrect project scope. Use repair for a concrete writing defect, advisory for optional improvements or JD coverage gaps, and factual_blocker only for an actual unresolved factual/candidacy conflict. Hypothetical project assumptions alone are not factual blockers. Conventional skills such as performance tuning are not defects merely because they are not product names. Do not require an entire baseline, denominator, comparison period or methodology when a concise metric already has clear meaning. A stated achieved latency or workload can stand without a baseline. Do not remove useful quantitative evidence solely to prefer qualitative wording. No invented requirements or requests for a full project story inside a bullet.'''


def patch_target(change):
    if change['target'] == 'bullet':
        return f"bullet:{change['role_key']}:{change['bullet_number']}"
    if change['target'] == 'experience_title':
        return f"title:{change['role_key']}"
    if change['target'] == 'skills':
        return f"skills:{change['group_number']}"
    return change['target']


def target_matches(finding, target):
    return finding['target_id'] == target or (finding['target_id'] == 'skills' and target.startswith('skills:'))


def reconcile_review_links(review):
    """Derive links from unique exact targets, never model list numbering.

    Do not infer semantic targets, invent changes, override factual blockers,
    or choose between ambiguous owners. Normal validation still rejects those.
    """
    result = deepcopy(review)
    findings = result.get('findings', [])
    resolved = {}
    for index, change in enumerate(result.get('changes', []), 1):
        owners = [i for i, finding in enumerate(findings) if target_matches(finding, patch_target(change))]
        if len(owners) == 1 and findings[owners[0]].get('severity') in {'repair', 'advisory'}:
            resolved[index] = owners[0]
    for owner_index, finding in enumerate(findings):
        owned = [index for index, owner in resolved.items() if owner == owner_index]
        # Remove a resolved change's incorrect old claims before attaching it
        # to its authoritative target. Unresolvable claims remain errors.
        retained = [index for index in finding.get('change_indices', []) if index not in resolved]
        finding['change_indices'] = list(dict.fromkeys(retained + owned))
        if owned:
            finding['severity'] = 'repair'
    return result


def validate_dispositions(patch, findings):
    expected = {f['finding_id']: f for f in findings}
    seen, linked = set(), set()
    for item in patch.get('dispositions', []):
        fid = item['finding_id']
        if (fid not in expected or fid in seen or not item.get('reason', '').strip()
                or item.get('status') not in {'patched', 'unchanged', 'blocked'}):
            raise ValueError('Repair must account for each finding exactly once with a reason.')
        seen.add(fid)
        indices = item.get('change_indices', [])
        if item['status'] == 'patched' and not indices:
            raise ValueError('A patched finding must link its replacement.')
        if item['status'] != 'patched' and indices:
            raise ValueError('Unchanged or blocked findings cannot claim replacements.')
        for index in indices:
            if not 1 <= index <= len(patch['changes']) or not target_matches(expected[fid], patch_target(patch['changes'][index - 1])):
                raise ValueError('Repair replacement does not match its finding target.')
            linked.add(index)
    if seen != set(expected) or linked != set(range(1, len(patch['changes']) + 1)):
        raise ValueError('Repair omitted a finding or returned an unrelated replacement.')


REPAIR_PROMPT = '''Return only replacements needed to resolve repair_issues or review_findings in current_draft. An empty changes array means no change. Never return a complete resume or unchanged fields.
Apply the supplied writing_rules and resume_mode_context.writing_rules. Preserve the checked project plan, contribution order, planned functional experience titles, sound wording and measurements. Do not add responsibilities or numbers merely to make a patch.
For headline, return its exact old_text and replacement title. For summary, old_text must be the exact unique sentence or passage to replace; replacement contains only the new passage. Do not repeat the rest of the summary. Multiple summary edits must not overlap.
For a bullet, identify role_key and its one-based bullet_number, copy its exact old_text and return one complete replacement bullet including consistent measurement metadata and the same contribution_number. This replaces only that bullet. Internal measurement labels belong in metadata, never prose.
For skills, return only an affected group using its one-based group_number, exact expected_category, and replacement category/items. Preserve useful existing items in that group. Do not add, remove or reorder groups. Category must be an allowed category.
Use no duplicate targets, unrelated edits, missing targets, confirmation questions or placeholders. Changes are checked and merged locally before the assembled resume is reviewed.'''


def repair_schema(roles, skill_categories=None, findings=None, *, current_draft=None):
    schema = draft_schema(roles, skill_categories)
    bullet = schema['properties']['experience']['properties'][roles[0]['key']]['properties']['bullets']['items']
    category = {'type': 'string', 'enum': sorted(skill_categories)} if skill_categories else STRING
    result = obj({'changes': {'type': 'array', 'items': {'anyOf': [
        obj({'target': {'type': 'string', 'enum': ['headline', 'summary']}, 'old_text': STRING, 'replacement': STRING}),
        obj({'target': {'type': 'string', 'enum': ['bullet']},
             'role_key': {'type': 'string', 'enum': [r['key'] for r in roles]},
             'bullet_number': {'type': 'integer', 'minimum': 1}, 'old_text': STRING, 'replacement': bullet}),
        obj({'target': {'type': 'string', 'enum': ['skills']},
             'group_number': {'type': 'integer', 'minimum': 1}, 'expected_category': STRING,
             'category': category, 'items': {'type': 'array', 'items': STRING, 'minItems': 2, 'maxItems': 5}}),
    ]}}})
    if current_draft is not None:
        # Bind each role, one-based position and old text together. Keep the
        # exact-match guard in apply_repairs even with constrained output.
        changes = result['properties']['changes']['items']['anyOf']
        changes[:] = [
            obj({'target': {'type': 'string', 'enum': ['headline']},
                 'old_text': {'type': 'string', 'enum': [current_draft.get('headline', '')]}, 'replacement': STRING}),
            obj({'target': {'type': 'string', 'enum': ['summary']}, 'old_text': STRING, 'replacement': STRING}),
        ]
        result['$defs'] = {'measurement': bullet['properties']['measurement']}
        for role, entry in current_draft.get('experience', {}).items():
            for number, original in enumerate(entry.get('bullets', []), 1):
                replacement = obj({'measurement': {'$ref': '#/$defs/measurement'},
                    'contribution_number': {'type': 'integer', 'enum': [number]},
                    'text': deepcopy(bullet['properties']['text'])})
                changes.append(obj({'target': {'type': 'string', 'enum': ['bullet']},
                    'role_key': {'type': 'string', 'enum': [role]},
                    'bullet_number': {'type': 'integer', 'enum': [number]},
                    'old_text': {'type': 'string', 'enum': [original['text']]},
                    'replacement': replacement}))
        for number, group in enumerate(current_draft.get('skills', []), 1):
            changes.append(obj({'target': {'type': 'string', 'enum': ['skills']},
                'group_number': {'type': 'integer', 'enum': [number]},
                'expected_category': {'type': 'string', 'enum': [group['category']]},
                'category': category, 'items': {'type': 'array', 'items': STRING, 'minItems': 2, 'maxItems': 5}}))
    if findings:
        result['properties']['dispositions'] = {'type': 'array', 'minItems': len(findings), 'maxItems': len(findings), 'items': obj({
            'finding_id': {'type': 'string', 'enum': [f['finding_id'] for f in findings]},
            'status': {'type': 'string', 'enum': ['patched', 'unchanged', 'blocked']},
            'change_indices': {'type': 'array', 'items': {'type': 'integer', 'minimum': 1}}, 'reason': STRING})}
        result['required'].append('dispositions')
    return result


def apply_repairs(draft, patch):
    """Apply exact, indexed replacements atomically; never guess a target."""
    result = deepcopy(draft)
    seen, summary_spans = set(), []
    for change in patch['changes']:
        target = change['target']
        if target in {'headline', 'summary'}:
            old, new = change['old_text'], change['replacement']
            text = str(draft.get(target, ''))
            if not new.strip() or (target == 'headline' and old != text):
                raise ValueError('Repair title/summary replacement is empty or targets stale text.')
            if target == 'summary':
                if not old or text.count(old) != 1:
                    raise ValueError('Repair summary passage must match exactly once.')
                start = text.index(old)
                if any(start < end and start + len(old) > begin for begin, end, _ in summary_spans):
                    raise ValueError('Repair summary passages overlap.')
                summary_spans.append((start, start + len(old), new))
                continue
            key = (target,)
            result[target] = new
        elif target == 'experience_title':
            role = change['role_key']
            entry = result.get('experience', {}).get(role)
            if entry is None or entry.get('title', '') != change['old_text']:
                raise ValueError('Repair experience title is stale or missing.')
            if not isinstance(change['replacement'], str) or not change['replacement'].strip():
                raise ValueError('Experience title replacement must be nonempty text.')
            entry['title'] = change['replacement'].strip()
            key = (target, role)
        elif target == 'bullet':
            role, number = change['role_key'], change['bullet_number']
            bullets = result.get('experience', {}).get(role, {}).get('bullets', [])
            if not isinstance(number, int) or not 1 <= number <= len(bullets):
                raise ValueError('Repair bullet target does not exist.')
            if bullets[number - 1]['text'] != change['old_text']:
                raise ValueError('Repair bullet text is stale.')
            if change['replacement']['contribution_number'] != number:
                raise ValueError('Repair must preserve the contribution number.')
            key = (target, role, number)
            bullets[number - 1] = deepcopy(change['replacement'])
        elif target == 'skills':
            number = change['group_number']
            groups = result.get('skills', [])
            if not isinstance(number, int) or not 1 <= number <= len(groups):
                raise ValueError('Repair skill group does not exist.')
            if groups[number - 1]['category'] != change['expected_category']:
                raise ValueError('Repair skill category is stale.')
            key = (target, number)
            groups[number - 1] = {'category': change['category'], 'items': deepcopy(change['items'])}
        else:
            raise ValueError('Unknown repair target.')
        if key in seen:
            raise ValueError('Duplicate repair target.')
        seen.add(key)
    for begin, end, new in sorted(summary_spans, reverse=True):
        result['summary'] = result['summary'][:begin] + new + result['summary'][end:]
    if 'skills' in result:
        result['skills'] = [group for group in result['skills'] if group['items']]
        if draft.get('skills') and not result['skills']:
            raise ValueError('Review cannot remove every skills group.')
    return result


def skill_style_notes(draft):
    notes = []
    for group in draft.get('skills', []):
        for item in group.get('items', []):
            text = str(item).strip()
            if ((len(text.split()) >= 3 and re.search(r'\b(?:adapters?|prototypes?)\b', text, re.I))
                    or (len(text.split()) >= 4 and re.search(r'\b(?:for|using|via|export|patterns)\b', text, re.I))):
                notes.append(f"Skills: prefer conventional technical names to the description '{text}'.")
    return notes


def resume_text_issues(draft):
    """Only hard content errors, not preferences about skill formatting."""
    fields = [('headline', draft.get('headline', '')), ('summary', draft.get('summary', ''))]
    issues = []
    for group in draft.get('skills', []):
        fields.append(('skills category', group.get('category', '')))
        fields.extend(('skill', item) for item in group.get('items', []))
    for key, role in draft.get('experience', {}).items():
        fields.extend((f'{key} bullet {i}', b.get('text', '')) for i, b in enumerate(role.get('bullets', []), 1))
    for field, text in fields:
        if INTERNAL_LABEL_RE.search(str(text)):
            issues.append(f'{field}: internal review/status labels must stay in metadata only; write clean resume text and preserve measurement values and units.')
    return issues


def review_text_view(draft):
    """Review visible writing, not per-bullet status records from the writer."""
    return {key: deepcopy(draft.get(key)) for key in ('headline', 'summary', 'skills')} | {
        'experience': {key: {**({'title': role['title']} if role.get('title') else {}),
                            'bullets': [b.get('text', '') for b in role.get('bullets', [])]}
                       for key, role in draft.get('experience', {}).items()}}


def plan_issues(plan, roles, jd):
    issues = []
    norm = lambda s: re.sub(r'\s+', ' ', str(s)).strip()
    source = norm(jd)
    for level in ('required', 'optional'):
        for index, req in enumerate(plan.get(level, []), 1):
            quote, capability = norm(req.get('jd_quote', '')), norm(req.get('capability', ''))
            if not quote or quote not in source or not capability:
                issues.append(f'{level} {index}: use an exact JD quote and a nonempty capability label. Label={capability!r}; quote={quote!r}')
                continue
    if not plan.get('required') and not any(isinstance(v, str) and v.strip() for v in plan.get('engineering_focus', [])):
        issues.append('Identify the required engineering work before choosing projects.')
    if set(plan.get('experience', {})) != {r['key'] for r in roles}:
        issues.append('Plan must contain exactly the selected employment headings.')
    for role in roles:
        entry = plan.get('experience', {}).get(role['key'], {})
        contributions = entry.get('contributions', [])
        if 'contributions' in entry and len(contributions) != role['bullet_min']:
            issues.append(f"{role['key']}: use exactly {role['bullet_min']} distinct contributions.")
        if not entry.get('system') or not entry.get('workflow') or not entry.get('scope') or not entry.get('assumptions'):
            issues.append(f"{role['key']}: describe the proposed system, workflow, scope and assumptions.")
        for i, text in enumerate(contributions):
            if any(SequenceMatcher(None, str(text).lower(), str(other).lower()).ratio() > .9 for other in contributions[:i]):
                issues.append(f"{role['key']}: remove duplicate contributions.")
    return issues


def normalize_draft(draft, numeric_tokens):
    """Do not let 'one component' padding masquerade as numerical impact.

    Demote unused measurement metadata and trivial scope counts. Never insert
    a measurement or change project responsibility to satisfy metadata.
    """
    result = deepcopy(draft)
    # Separate clearly spaced lists locally. CI/CD, TCP/IP, etc. stay intact.
    # Formatting a valid technical term must never trigger another model call.
    for group in result.get('skills', []):
        group['items'] = [part.strip() for item in group.get('items', [])
                          for part in re.split(r'\s+/\s+', str(item)) if part.strip()]
    for role in result.get('experience', {}).values():
        for bullet in role.get('bullets', []):
            measure = bullet.get('measurement', {})
            if not proposed_numbers(str(bullet.get('text', '')), numeric_tokens):
                # The visible sentence is authoritative. An invisible count or
                # N/A is not evidence and does not justify a full model repair.
                measure.update(kind='qualitative', value='', unit='', status='qualitative')
                continue
            if measure.get('kind') != 'scale' or str(measure.get('value', '')).strip().lower() not in {'1', 'one'}:
                continue
            nouns = r'components?|modules?|products?|portals?|features?|strateg(?:y|ies)|widgets?|integrations?|services?|schemas?|syncs?|toolsets?'
            if not re.search(r'\b(?:' + nouns + r')\b', str(measure.get('unit', '')), re.I):
                continue
            text = str(bullet.get('text', ''))
            if numeric_tokens(text) - {'1'}:
                continue
            text = re.sub(r'\b(?:1|one)\s+(?=(?:[a-z-]+\s+){0,5}(?:' + nouns + r')\b)',
                          lambda m: 'an ' if text[m.end():m.end() + 1].lower() in 'aeiou' else 'a ', text, flags=re.I)
            bullet['text'] = text
            measure.update(kind='qualitative', value='', unit='', status='qualitative')
    return result


def proposed_numbers(text, numeric_tokens):
    """Read explicit quantities in a proposed sentence without a unit whitelist.

    This mode has no source-provenance decision. Version identifiers and known
    language/protocol versions still do not constitute numerical evidence.
    """
    values = set(numeric_tokens(text))
    normalized = normalize_number_words(text)
    for match in re.finditer(r'(?<![\w.])\d[\d,]*(?:\.\d+)?(?:\s*(?:%|percent|x|\+))?(?![\w.])', normalized, re.I):
        before = normalized[max(0, match.start() - 40):match.start()]
        if re.search(r'(?:\b(?:java|python|swift|node(?:\.js)?|react|oauth|tls|http)|\.net)\s*[/v]?\s*$', before, re.I):
            continue
        values.add(canonical_quantity(match.group(), before))
    return values


def bullet_writing_issues(resume, numeric_tokens=None):
    """Check final prose, including manual/editor changes and renderer payloads.

    Metadata/measurement tests can run independently through draft_issues;
    normal generation and PDF export explicitly apply this writing contract.
    """
    issues = []
    experience = resume.get('experience') or {}
    entries = experience.items() if isinstance(experience, dict) else enumerate(experience)
    for key, entry in entries:
        label = entry.get('company') or str(key)
        bullets = entry.get('bullets') or []
        quantitative = 0
        for index, bullet in enumerate(bullets, 1):
            text = str(bullet.get('text', '') if isinstance(bullet, dict) else bullet)
            words = len(text.split())
            if not 25 <= words <= 30:
                issues.append(f'{label} bullet {index}: {words} words; use 25-30 words with a contribution, technical mechanism and outcome, not filler.')
            if numeric_tokens is not None and proposed_numbers(text, numeric_tokens):
                quantitative += 1
        target = math.ceil(.8 * len(bullets))
        if numeric_tokens is not None and quantitative < target:
            issues.append(f'{label}: numerical evidence in {quantitative}/{len(bullets)} bullets; target {target}/{len(bullets)} (80%). Use meaningful quantities, not versions or invented factual evidence.')
    return issues


def ensure_plan_titles(plan, roles):
    result = deepcopy(plan)
    for role in roles:
        entry = result.get('experience', {}).get(role['key'])
        if entry is not None and not str(entry.get('title') or '').strip():
            entry['title'] = 'Software Engineer'
    return result


def apply_plan_titles(draft, plan, roles):
    result = deepcopy(draft)
    for role in roles:
        entry = result.get('experience', {}).get(role['key'])
        if entry is not None and not str(entry.get('title') or '').strip():
            proposed = (plan.get('experience') or {}).get(role['key'], {})
            entry['title'] = str(proposed.get('title') or 'Software Engineer').strip()
    return result


def draft_issues(draft, plan, roles, numeric_tokens, *, check_writing=False):
    issues, notes = resume_text_issues(draft), []
    if check_writing:
        issues.extend(bullet_writing_issues(draft))
    if set(draft.get('experience', {})) != {r['key'] for r in roles}:
        issues.append('Draft must contain exactly the selected employment headings.')
    for role in roles:
        bullets = draft.get('experience', {}).get(role['key'], {}).get('bullets', [])
        if len(bullets) != role['bullet_min']:
            issues.append(f"{role['key']}: preserve the contribution count.")
        count = 0
        for i, bullet in enumerate(bullets, 1):
            text = str(bullet.get('text', ''))
            measurement = bullet.get('measurement', {})
            numbers = proposed_numbers(text, numeric_tokens)
            if bullet.get('contribution_number') != i:
                issues.append(f"{role['key']} {i}: keep the original contribution order.")
            if not text.strip() or len(text.split()) > 55 or re.search(r'\[Confirm|\[(?:metric|number|value)\]|\?', text, re.I):
                issues.append(f"{role['key']} {i}: write a concise finished sentence without questions/placeholders.")
            if numbers:
                count += 1
                if measurement.get('status') != 'illustrative_unverified' or measurement.get('kind') == 'qualitative':
                    issues.append(f"{role['key']} {i}: numerical evidence must be labelled illustrative and quantitative.")
                values = numeric_tokens(str(measurement.get('value', '')) + ' ' + str(measurement.get('unit', '')))
                # This is an explicitly typed measurement field, so extraction
                # need not guess whether its unit noun is on a prose whitelist.
                if not values:
                    declared = normalize_number_words(str(measurement.get('value', '')))
                    for match in re.finditer(r'(?<![\w])\d[\d,]*(?:\.\d+)?(?:\s*(?:%|percent|x|\+))?', declared, re.I):
                        token = canonical_quantity(match.group(), declared[:match.start()])
                        if re.search(r'\bpercent\b|%', str(measurement.get('unit', '')), re.I) and '%' not in token:
                            token += '%'
                        values.add(token)
                # Here value/unit fields describe illustrative magnitudes, not
                # independently verified exactness. Preserve the qualifier in
                # the visible prose; do not confuse '~30%' with a new value.
                magnitude = lambda token: re.sub(r'^[~<>=]+|\+$', '', token)
                visible_values = {magnitude(n) for n in numbers}
                metadata_values = {magnitude(n) for n in values}
                # A unit such as "authentication success rate" can describe
                # the exact percentage already visible in the sentence. Accept
                # only an identical magnitude with an explicit visible percent;
                # never convert fractions or infer a missing numeric value.
                if re.search(r'\b(?:rate|percentage|percent)\b', str(measurement.get('unit', '')), re.I):
                    metadata_values = {value + '%' if not value.endswith('%') and value + '%' in visible_values else value
                                       for value in metadata_values}
                missing = metadata_values - visible_values
                if missing and len(metadata_values) == 1 and visible_ratio_matches_measurement(text, measurement):
                    missing = set()
                # A record may state a delta while the sentence gives its two
                # endpoints. Accept only a demonstrable numeric subtraction.
                if missing and len(missing) == 1 and re.search(r'\bfrom\b.+\bto\b', text, re.I):
                    unit_free = lambda n: re.sub(r'[%x]$', '', n)
                    try:
                        operands = [Decimal(unit_free(n)) for n in visible_values]
                        delta = Decimal(unit_free(next(iter(missing))))
                        if len(operands) == 2 and abs(operands[0] - operands[1]) == delta:
                            missing = set()
                    except Exception:
                        pass
                if not measurement.get('value') or not measurement.get('unit') or not values or missing:
                    issues.append(f"{role['key']} {i}: measurement value/unit must agree with the visible bullet.")
            elif measurement.get('status') != 'qualitative' or measurement.get('kind') != 'qualitative' or measurement.get('value') or measurement.get('unit'):
                issues.append(f"{role['key']} {i}: the proposed measurement is absent from the sentence. Include its illustrative value naturally to support the 80% goal, or set kind/status qualitative and clear value/unit. Do not leave numeric metadata attached to qualitative prose.")
        target = math.ceil(len(bullets) * .8)
        if count < target:
            notes.append(f"{role['company']}: {count}/{len(bullets)} numerical examples; target {target}. Prefer concrete qualitative work to filler numbers.")
    return issues, notes


def render_draft(plan, draft, roles, mode=None):
    lines = ['# ' + draft['headline'], '', '**Experimental proposed draft — project details and measurements are unverified.**', '', draft['summary'], '']
    if mode:
        lines += ['**Profile mode:** ' + mode['label'], '']
    for role in roles:
        entry = plan['experience'][role['key']]
        lines += ['## ' + role['company'] + ' — ' + draft['experience'][role['key']].get('title', entry.get('title') or 'Software Engineer'), '', role['dates'], '', '**Proposed project:** ' + entry['system'], '']
        lines.extend('- ' + b['text'] for b in draft['experience'][role['key']]['bullets'])
        lines += ['', '**Assumptions to review:**', ''] + ['- ' + s for s in entry['assumptions']] + ['']
    return '\n'.join(lines)


PROJECT_HANDOFF_POLICY = """PROJECT CONTEXT: engineering_focus is the transferable job direction. Each checked_plan.experience entry defines an independent proposed project, not the hiring company's product. Preserve its purpose, users, workflow, selected technologies and career scope through writing and review. The original JD supplies relevance and priority, not permission to replace historical business context. Do not import target customers, domain objects or commercial outcomes into those projects. Correct copied business context, unrelated contributions and title-driven AI drift. Required/optional classification is not part of the new plan; older saved plans remain readable. Planning contribution notes use work | intended outcome | measurement opportunity; never copy these labels into resume text. Measurements should support the stated outcome: access-control correctness is not authentication latency, and tested-path coverage does not establish fewer production regressions. Proposed project details and measurements remain unverified; status belongs outside resume prose."""
TARGETING_PROMPT += '\n' + PROJECT_HANDOFF_POLICY
DRAFT_PROMPT += '\n' + PROJECT_HANDOFF_POLICY
REVIEW_PROMPT += '\n' + PROJECT_HANDOFF_POLICY


WRITER_CLAIM_POLICY = """WRITER CLAIM ALIGNMENT: Keep the checked project's purpose, workflow, selected stack and any existing contribution order. Planning work/outcome/measurement notes are fallible writing directions, not observed evidence. Preserve the implemented work; narrow an overstated outcome or choose a direct measurement of it without adding another accomplishment, technology or business claim. Activity counts describe usage/scale, not automatically quality, speed or safety. Coverage describes tested paths, not demonstrated regression reduction. Observe the effect at the same point where it is claimed. Give quantitative measures clear units. Do not turn a measurement opportunity into a verified result: this source-free mode's generated values remain proposed examples with the existing separate factual-status metadata. Prefer a concrete qualitative outcome over a misleading number; numerical coverage never justifies changing the project or inventing supporting work. Resume prose contains only the concise contribution, mechanism and supportable proposed outcome, not internal labels or this reasoning."""
DRAFT_PROMPT += '\n' + WRITER_CLAIM_POLICY
REVIEW_PROMPT += '\n' + WRITER_CLAIM_POLICY


# Contribution selection and final prose share the existing experience call.
EXPERIENCE_WRITING_PROMPT = """Generate only the experience section for the supplied proposed project stories. No actual project accomplishments or measured results are supplied. This is a source-free proposed draft, not verified work history. All generated quantities must have measurement.status illustrative_unverified; qualitative bullets use status qualitative. Never put internal factual-status labels, questions or confirmation requests in resume prose.

The planner has selected only each role's purpose, users, workflow, responsibility boundaries and core stack. No contribution notes are supplied. In this same call, choose distinct important engineering contributions within each project and write their final resume bullets. Do not return a separate contribution plan or reasoning. One contribution per bullet; exactly bullet_min bullets per supplied role. Number contribution_number from 1 independently within each role, preserving the order you choose.

Project constraints are authoritative: preserve each project's own purpose, users, workflow, timeline and scope. Use the JD to prioritize relevant engineering, not to replace those stories with the hiring company's product or business. Never transplant the hiring company's customers, domain objects or commercial outcomes into a role. Earlier roles have narrower implementation and fewer tools; do not turn every role into the same stack or responsibility. Choose definite compatible technologies from the supplied project context; do not introduce unrelated tools or another project. Apply resume_mode_context.writing_rules. The output contains no titles, summary or skills.

For each selected contribution, identify the concrete implemented change and technical mechanism, its direct outcome and a measurement that observes that same outcome. Resolve these together while writing, not as a separate planning call. Narrow a broader outcome if its measurement only demonstrates a narrower capability. Counts describe use/scale, not automatically quality, speed or safety; coverage describes tested paths, not demonstrated regression prevention. Observe the effect at the same point where it is claimed. Do not use an upstream activity count as evidence of a downstream outcome. Do not assume additional work to justify a claim. Preserve concise engineering substance rather than narrating an entire project in every bullet.

Write natural XYZ-style sentences highlighting meaningful engineering work, mechanism and a useful result or scale. Every bullet must contain 25–30 whitespace-separated words inclusive; hyphenated expressions count as one. Never pad with filler or attach another accomplishment to reach length. Aim for meaningful numerical evidence in at least 80% of bullets per role. Generated quantities are proposed examples only, not observed evidence: use internally consistent explicit units and matching measurement metadata. Do not use versions, one-component counts, irrelevant test-pass statistics or arbitrary numbers to satisfy the goal. Prefer a concrete qualitative bullet when no useful quantity fits. Keep numbers outside qualitative measurement metadata. Numerical coverage does not justify inventing another project, supporting implementation or business result. Keep measurement.value and measurement.unit consistent with the visible sentence, and measurement.context concise.

Before returning, silently check project coherence, distinct contributions, career scope, outcome/measurement alignment, exact bullet counts, numbering and word limits. Return only the requested experience JSON.
WRITING AND NUMBER CONTRACT: Write the finished sentence first, then copy one primary numeric quantity stated literally in that sentence into measurement.value and its matching unit into measurement.unit. Never store a calculated percentage when the sentence gives only before/after endpoints. In that case use the achieved endpoint as the measurement and classify it as scale, or state an explicit percentage in the text if that is the chosen primary quantity. Do not label an achieved success rate as an improvement without a stated comparison. Spell numbers as numerals to match metadata. The separate metadata is not permission to call an invented value observed, measured, validated or proven in prose.
CLAIM QUALITY: Highlight important implementation decisions and their direct operational effect. Keep access control tied to permissions, not download availability; tests tied to tested behavior or coverage, not unmeasured confidence or production reliability. Keep each quantity attached to one defined effect: do not use one percentage for both latency and rerender count, or both alert volume and engineer effort. Do not infer workload capacity from implementation alone; quantities remain internally consistent proposed examples. Avoid superlative scope, overnight improvements, arbitrary precision and decorative numbers. Do not use trivial one-item counts to reach the numeric goal. End each bullet with useful engineering content rather than filler such as "by measurement", "reliably", "observed", "across teams" or "overnight". Use meaningful implementation detail to meet length, not another achievement. Earlier-role bullets remain scoped, substantive implementation work.
Before returning, check every text against its metadata and remove awkward qualifiers, unsupported secondary effects and repeated accomplishments.
TECHNICAL ATTRIBUTION: Each bullet has one principal implemented contribution and one principal result. Any secondary mechanism must support that same result, not tack on another achievement. The implemented layer must be capable of causing the result: frontend UI work cannot establish backend concurrent capacity; instrumentation/CI execution alone cannot increase tested-path coverage; authorization cannot establish availability. Test coverage needs writing tests. A throughput or concurrency claim needs an actual batching, parallelism, scheduling or service optimization mechanism in the sentence. Client concurrency is not a measure of a browser component's responsiveness. State the contribution at its actual layer and omit an unsupported capacity claim. Do not add workload figures, user counts or dataset sizes just to make a sentence sound impressive. Numerical examples may be simple and approximate: choose a percentage reduction when it describes a direct change, a final latency for an optimization, or a meaningful workload for a processing contribution, rather than making every bullet a scale claim. Keep the primary measurement explicitly visible in text with matching metadata. Do not force a second quantity into a bullet. Never invent verification language; tests or production can be the setting of the proposed work, not proof of actual history.
SCOPE AND LANGUAGE: Respect each role's core stack. Use concrete standard tool names only where the mechanism needs them; never introduce a competing job framework for a stack that already has one. Select distinct contributions spanning the project's actual feature workflow, not a list of infrastructure keywords. First-role work stays on scoped UI implementation, state handling, accessibility and testing, without unsupported service capacity. Do not state 'qualitative confidence' or other internal planning language in resume text. Stop at the supportable result; prioritize clear human-readable engineering substance over maximal numbers or tool coverage. Accept a qualitative shortfall when useful quantification does not fit."""
REVIEW_QUALITY_POLICY = """FINAL EDITORIAL PASS: Assess the entire resume as a hiring engineer, then return exact typed-ID replacements for concrete writing defects. Preserve relevant project directions, selected mode, ordinary titles and sound contributions. Do not rewrite everything or demand a whole story, baseline or measurement study inside each bullet. Project concepts and measurements remain proposed, not established history.
SUMMARY: Keep roughly 35-55 words explaining specialization and strongest relevant work in natural professional language. Remove planning language, sales claims, technology inventories and repeated skills. Do not add years, credentials or authority.
SKILLS: Consolidate crowded skills into 4-5 focused groups, fewer when sufficient. Inspect every existing group; do not leave a nine-group inventory unchanged. Use supplied allowed categories and 2-5 short conventional items per retained group. Prioritize the core project/JD stack, avoid repeated concepts and generic filler. Consolidate useful existing items through sid replacements and remove redundant groups using empty items arrays. Do not invent tools to fill categories or delete important core skills merely to meet a count.
BULLETS: Preserve distinct implemented contributions and bounded career progression. One principal action, useful mechanism and direct outcome or meaningful scope. Replace decorative counts, undefined percentages, contradictory timings, implausible precision and misleading causality with a narrower clear result. Testing supports tested behavior or coverage, not automatic production reliability; instrumentation supports detection, not unmeasured reliability. A clock time, version or number of verification steps is not itself evidence of impact. Do not invent a new quantity, client fact, benchmark, tool or verification event to repair a weak claim. Keep sound proposed quantities; if a defective quantity cannot be repaired from existing content, remove it and make the result qualitative. Numerical coverage is advisory. Final endpoints without comparison are scale, not improvement. Metadata must copy the primary visible quantity and matching unit; qualitative replacements have empty value/unit and no incidental numeric scope left in the sentence.
Use 25-30 words for every replacement bullet. Meet length with existing implementation or workflow detail, never empty tails, geography, scheduling or new achievements. Remove phrases like 'qualitatively', 'per commit metric' and arbitrary global scope. Preserve concise useful work; no keyword packing. For implausible employer/project fit, narrow to the supplied broad workflow rather than invent a replacement domain. If the checked plan itself needs a new project, record a concise advisory instead of pretending wording establishes it.
Inspect the supplied existing measurement metadata too: return a bid replacement even when the sentence is unchanged if its metadata conflicts with the visible text. Before returning, reread each replacement as resume prose: natural grammar, meaningful units, compatible technical mechanism, no new unsupported facts, no repeated accomplishment, matching metadata and exact original typed ID. Ordinary writing defects require replacements, not advice for the user to copy manually. Use the existing response schema only."""
REVIEW_PROMPT += "\n" + REVIEW_QUALITY_POLICY


CAREER_SCOPE_POLICY = """CAREER SCOPE: Calibrate each historical project and contribution to its place in the supplied career timeline, independently of the target JD's expertise. When the supplied history establishes an early-career period, choose a small application/module workflow inside an existing team system; the candidate implements assigned components, handlers, forms, validation, API consumption, focused tests and bug fixes using existing patterns and team-provided contracts. Make useful engineering decisions within the assigned task, without implying they chose the platform architecture, owned the entire service or established organization-wide infrastructure. Do not reduce all early work to assisting or trivial tasks, and do not invent supervision, training or collaboration events as historical facts.
Show progression through responsibility and depth: scoped implementation within an existing system, then independent feature delivery/integration, then broader feature or service responsibility where the timeline and supplied context support it. A recent JD describes the target job, not the expertise held in the first career period. Earlier projects may retain an established specialization with narrower responsibilities; select only the period-appropriate subset supported by the career context. Do not equate less responsibility with a different specialization. Advanced tools can belong to the team's existing stack without implying that this candidate selected, designed or operated all of it. Scope results to the implemented screen, interaction, endpoint, test or module. Do not attach service concurrency, fleet-wide capacity, organization-wide adoption, platform reliability or architecture ownership to early UI implementation. Keep conventional story-appropriate functional titles; do not force Junior or manufacture Senior/Lead promotions. Judge the substance, not a blacklist of action verbs: independently implementing a component is credible, independently defining a platform is different.
Use actual dates and available career context, not employer name, array order or number of selected roles. The earliest selected role may not be the career start. A single selected recent role must not be automatically downgraded to entry level, and profile mode must not make every historical role equally experienced. If career-start context is missing, keep scope conservative without inventing a fresher designation. The planner must bound early-role system/workflow/scope/assumptions accordingly; the writer must select contributions within those boundaries; the targeting check corrects inflated plan scope, and the final reviewer replaces inflated bullet claims while preserving meaningful technical work. Do not solve scope inflation by merely changing a verb or prefixing 'assisted' to the same platform-scale claim."""
TARGETING_PROMPT += '\n' + CAREER_SCOPE_POLICY
DRAFT_PROMPT += '\n' + CAREER_SCOPE_POLICY
EXPERIENCE_WRITING_PROMPT += '\n' + CAREER_SCOPE_POLICY
REVIEW_PROMPT += '\n' + CAREER_SCOPE_POLICY


SPECIALIST_CONTINUITY_POLICY = """SPECIALIST CAREER CONTINUITY: Before choosing historical projects, distinguish a job requiring sustained experience in one platform/specialization from a generalist job accepting transferable engineering. Ask separately: does the JD require a sustained specialist career, and does the supplied factual history establish that track? A years requirement for a named platform is not a requirement for the same number of years of software work generally. Employment headings, dates and generated project assumptions do not establish platform tenure.
For an established specialist track, preserve the specialization across the supported periods while reducing responsibility backward: assigned platform components or workflow fixes, then independent applications/integrations, then broader delivery and governance where supported. Keep independent project purposes; continuity does not mean copying the same project or the target employer's industry. Do not automatically substitute React/Java/Node generalist work for earlier specialist work merely to show progression. Choose each functional title after selecting its project and scope, not from a saved profile title. Conversely, do not backfill specialist technologies, change actual dates, fabricate specialist titles, or claim required years simply because the posting demands them. With headings-only inputs, mark specialist tenure unestablished and identify the gap; do not silently imply that adjacent development meets it. An uncertain qualification is an advisory gap, not a reason to invent experience or fail generation.
The planner returns a compact career_alignment: specialization (short platform/track), requires_sustained_specialization (whether the JD explicitly requires it), support_status (established only with supplied factual evidence; unestablished when required but unproven; not_required otherwise), gap (one short missing-evidence statement, empty when none). Existing saved plans may lack this metadata. It is planning/review context only, never text to copy into resume prose. Writers and reviewers preserve established specialist continuity and bounded early-career work, without turning an unestablished track into a claim of qualified years. Do not use required/optional classification or a local rejection gate for this decision."""
TARGETING_PROMPT += '\n' + SPECIALIST_CONTINUITY_POLICY
DRAFT_PROMPT += '\n' + SPECIALIST_CONTINUITY_POLICY
EXPERIENCE_WRITING_PROMPT += '\n' + SPECIALIST_CONTINUITY_POLICY
REVIEW_PROMPT += '\n' + SPECIALIST_CONTINUITY_POLICY


EXPERIENCE_TITLE_POLICY = """EXPERIENCE TITLES: Use one short conventional title for each proposed project's work, responsibility and career stage. Preserve the planner's title when it fits. Evaluate roles individually against supplied dates and career context, then check the timeline together: do not flatten substantially different responsibility into one default title, or force a distinct title at every employer. Assigned components in an established first-career period may warrant Associate Software Engineer or Junior Developer; independent feature delivery generally fits Software Engineer or an established specialist developer title; broader hands-on implementation may warrant Software Engineer II where conventional. For a multi-role timeline with an initial assigned-component role and no supplied prior experienced-career context, prefer a conventional Associate or Junior label for that initial role; do not leave it at the default unlevelled title automatically. Examples are not a fixed title ladder. Dates alone do not prove level, promotions or specialist years, and the oldest selected role is not necessarily the career start. Keep the technical family coherent: platform specialists may retain the same title when no credible conventional level distinction fits. Do not append invented qualifiers or change specialization merely to create variation. Avoid compound labels, product names, keyword inventories, slash alternatives and explanatory parentheses. Do not import Senior, Lead, Architect or Manager from the advertised role without supporting career context. Check that older bullets remain appropriately bounded and recent bullets support their proposed title. Correct a mismatch with the smallest necessary title or scope change. Preserve explicit user title overrides. Labels describe proposed functional work, not verified official employment titles or promotion history."""
TARGETING_PROMPT += '\n' + EXPERIENCE_TITLE_POLICY
DRAFT_PROMPT += '\n' + EXPERIENCE_TITLE_POLICY
EXPERIENCE_WRITING_PROMPT += '\n' + EXPERIENCE_TITLE_POLICY
REVIEW_PROMPT += '\n' + EXPERIENCE_TITLE_POLICY


PLANNED_CAREER_HANDOFF = """PLANNED CAREER HANDOFF: The planner selected independent proposed business contexts, platform continuity, ordinary functional titles and chronological responsibility boundaries. Preserve those decisions. Specialization is the technical platform family, not the hiring company's industry. Do not replace an independently selected business context with the target's product, customer category or named program to improve relevance. Do not replace an earlier specialist role with unrelated generalist technologies merely to signal less experience. A proposed platform track and an unestablished factual-tenure assessment can coexist: preserve the proposed design while retaining the qualification gap outside resume prose; do not claim verified years or credentials. Keep conventional planned titles instead of inventing variants or promoting the candidate. Narrow early-role contribution scope rather than changing technical track. Correct an actual conflict or implausibility with the smallest needed change, not wholesale reconstruction."""
TARGETING_PROMPT += '\n' + PLANNED_CAREER_HANDOFF
DRAFT_PROMPT += '\n' + PLANNED_CAREER_HANDOFF
EXPERIENCE_WRITING_PROMPT += '\n' + PLANNED_CAREER_HANDOFF
REVIEW_PROMPT += '\n' + PLANNED_CAREER_HANDOFF


BUSINESS_CONTEXT_AND_TECH_FAMILY_HANDOFF = """PROJECT/FAMILY HANDOFF: Preserve the planned project's independently chosen purpose and plausible employer/client context. Sharing an industry with the hiring company is allowed; copying its distinctive product, niche program or signature workflow into historical roles is not. Do not invent an unrelated consulting client for an operating company, or add named clients and niche facts to a proposed broad client context. Preserve the technical career family, not every current tool in every period. A stable platform may recur with smaller earlier responsibilities; recent AI/agent work may grow from earlier language/API/data/testing foundations without backdating RAG, agent frameworks or provider services. Do not rewrite a foundation role into modern AI work just to repeat the JD stack, or move a project to an unrelated industry merely to make it different. Respect period suitability, ordinary titles, early-career scope, and the distinction between proposed examples and verified employment evidence. Do not manufacture years, credentials or tool-use history."""
TARGETING_PROMPT += '\n' + BUSINESS_CONTEXT_AND_TECH_FAMILY_HANDOFF
DRAFT_PROMPT += '\n' + BUSINESS_CONTEXT_AND_TECH_FAMILY_HANDOFF
EXPERIENCE_WRITING_PROMPT += '\n' + BUSINESS_CONTEXT_AND_TECH_FAMILY_HANDOFF
REVIEW_PROMPT += '\n' + BUSINESS_CONTEXT_AND_TECH_FAMILY_HANDOFF

"""JD-led writing context and conservative checks for known bullet defects.

These checks identify repair targets, not hiring probabilities or factual truth.
Semantic requirement coverage remains the responsibility of the separate audit.
"""

from copy import deepcopy
import re
from difflib import SequenceMatcher
from resume_target_work import target_work_context
from resume_measurements import measurement_rules, measurement_schema, incompatible_time_units


ROLE_EVIDENCE_FIELDS = ("source_bullets", "achievements", "evidence", "metric_evidence")


def role_evidence(source: dict) -> dict:
    """Keep explicitly supplied role evidence without sharing mutable values."""
    return {
        field: deepcopy(source[field])
        for field in ROLE_EVIDENCE_FIELDS
        if isinstance(source.get(field), (str, list, dict)) and source[field]
    }


def project_characteristics(analysis: dict, job_description: str = "") -> dict:
    """Describe the target work, explicitly separate from applicant history."""
    def entries(key, limit):
        values = analysis.get(key) or []
        if not isinstance(values, list):
            return []
        return [str(value).strip() for value in values if str(value).strip()][:limit]

    return {
        "authority": "target_requirements_only_not_candidate_evidence",
        "target_role": str(analysis.get("target_role") or "").strip(),
        "problem_to_solve": str(analysis.get("core_problem") or "").strip(),
        "system_context": str(analysis.get("system_description") or "").strip(),
        "target_work": target_work_context(analysis),
        "priority_requirements": entries("top_requirements", 4),
        "valid_requirement_numbers": list(range(1, len(entries("top_requirements", 4)) + 1)),
        "supporting_requirements": entries("secondary_requirements", 5),
        "workflows": entries("workflows", 6),
        "responsibilities": entries("responsibilities", 6),
        "desired_outcomes": entries("desired_outcomes", 4),
        "raw_job_description": str(job_description or "").strip(),
    }


def project_writing_rules() -> str:
    return "\n".join([
        "JD-DRIVEN PROJECT AND BULLET CONSTRUCTION:",
        measurement_rules(),
        "- Read the target project characteristics before drafting experience.",
        "- target_work describes the employer's required system, not candidate history. Use its workflow and specialist capabilities to select relevant supplied accomplishments before writing. A broad routing label or tool overlap must not override it.",
        "- Keep the actual employer system distinct from the target system. If a required specialization is absent from role sources, state the gap in metadata and emphasize supported transferable contributions; never relabel backend employment as native/mobile work or fuse unrelated source projects to simulate fit.",
        "- Do not credit CI/CD from production caching, monitoring or data pipelines alone. Requirement links need the same underlying capability visible in the cited bullet, not merely a related engineering activity.",
        "- Follow this order: JD -> required project characteristics -> draft contributions -> coherent project narrative -> individual XYZ bullets.",
        "- Identify the system, its users, the objects processed, the problem, and the engineer's contribution; do not start from a fixed AI or ingestion project.",
        "- Supplied role sources are authoritative for drafting: use their stated measurements without asking to reconfirm them or inventing additional baselines. Never replace an available source metric with a confirmation slot.",
        "- Preserve contribution scope: do not add Led, Owned, architecture ownership, new users or implementation mechanisms absent from the source.",
        "- Use supplied role evidence and historical titles to constrain candidate claims. JD characteristics and preliminary skills describe targeting, not verified employment facts.",
        "- If source detail is missing, do not fill it with invented employer projects, tools, responsibilities or measured outcomes; use supported transferable work and leave the specific gap unresolved.",
        "- In a genuine AI project, emphasize the relevant UI, integration, data or automation contribution; do not disguise it as unrelated CRM, ERP or industry experience.",
        "- Lead recent roles with their strongest supported contribution to the top requirements, not a generic enterprise-delivery summary.",
        "- Give each bullet one distinct contribution to a coherent system. Avoid multiple paraphrases of ingestion/retrieval or mirroring the same project across every employer.",
        "- Use XYZ as a meaning check: a specific accomplishment, a clearly defined measure, and the action that produced it. Vary the sentence order naturally.",
        "- Name what is routed, validated, reconciled or synchronized and the actual systems involved when supplied; do not silently convert transaction routing into lead routing.",
        "- Explain the implementation change rather than listing tools. Include a constraint only when it explains a real decision; never require an 'under constraints' clause.",
        "- A plan, design document or ceremony does not itself establish implemented performance gains. Distinguish proposed capacity from measured production results.",
        "- Define ambiguous outcomes such as demo readiness, routing accuracy or feedback velocity; a percentage alone is insufficient.",
        "- Do not use 'Zapier-style', 'UniQuery-like' or analogous product names as proof of direct platform experience.",
        "- Retain the 80% numerical-evidence target. Use supplied metrics with their original accomplishment, measure, baseline, population and time period. Fewer errors is not the same as greater accuracy.",
        "- When a metric is missing, retain a concrete supported qualitative accomplishment. Missing measurement questions belong to review metadata, never in resume sentences. Do not invent numbers or write confirmation placeholders in bullets.",
        "- When project details are missing, use actual supported transferable software work and leave the unsupported requirement as a gap. Never draft hypothetical employer projects, hardware work, customer visits or tools to match the JD. Resume bullets must be completed source-supported accomplishments, not proposals or confirmation requests.",
        "- First return contribution_plan: one short, distinct contribution per planned bullet. Connect these into project_narrative, then write the final XYZ bullets. Do not pad the opening with a repeated summary accomplishment.",
        "- Return bullet_evidence for every bullet: bullet_number, source_refs and confirmation_questions. References use field.index for source_bullets/achievements/evidence/metric_evidence lists (one-based), field.key for objects, or field for a string. Cite only supplied role evidence, never JD, skills suggestions, generated text or the anchor.",
        "- confirmation_questions must concern only unverified facts actually included in that bullet. Do not ask optional follow-up questions about scope, measurements or tools not claimed, and do not reconfirm supplied source facts. Use an empty list when the bullet is supported.",
        "- Every final bullet needs actual source_refs. Remove uncertain details instead of inserting confirmation requests. Evidence limits and questions belong only in project_narrative.evidence_limits and bullet_evidence, outside the resume body. Do not call unverified work direct evidence of a requirement.",
        "- Do not invent baselines, users, durations or incidents to satisfy numerical coverage.",
        "- Before returning, check project coherence, requirement relevance, action/result causality and natural grammar. Rewrite weak bullets without adding unsupported facts.",
        "- Return project_narrative per role: system, users, workflow, personal_contribution and evidence_limits. This is drafting context, not an extra resume section.",
        "- Return requirement_evidence for each actual priority requirement in valid_requirement_numbers (at most four), numbered from 1; never add a fourth when only three exist, per role. Link exact one-based bullet_numbers for direct or transferable support; use fit gap and an empty list when this role does not cover the requirement.",
        "- Requirement links describe evidence visible in the draft, not independently verified employment facts. Do not claim direct fit from a tool name alone.",
    ])


def bullet_quality_findings(payload: dict, blueprints: list[dict]) -> list[dict]:
    """Flag narrow, observable defects; do not attempt general semantic scoring."""
    findings = []
    for blueprint in blueprints:
        key = blueprint["key"]
        bullets = ((payload.get("experience") or {}).get(key) or {}).get("bullets") or []
        for index, value in enumerate(bullets, 1):
            text = str(value).strip()
            issues = []
            if re.search(r"\b(?:Zapier-style|UniQuery-like)\b", text, re.I):
                issues.append(("platform_analogy", "Name the actual implementation; a product analogy does not demonstrate experience with that platform."))
            if re.search(r"\b(?:demo readiness|feedback velocity|conversion proxy metrics|pipeline visibility)\s+(?:by\s+)?(?:(?:about|approximately|roughly)\s+|~)?\d+(?:\.\d+)?\s*(?:%|percent)", text, re.I):
                # Explicit definitions are fine; do not demand that every metric be numeric.
                if not re.search(r"\b(?:defined as|measured (?:as|by)|preparation time|hours? to|time to)\b", text, re.I):
                    issues.append(("undefined_metric", "Define the measured outcome instead of attaching a percentage to an ambiguous label."))
            if re.search(r"\brouting and webhook workflows\b", text, re.I) and not re.search(
                r"\b(?:leads?|contacts?|tickets?|transactions?|requests?|events?|cases?|records?|messages?|traffic|payments?|orders?|tasks?|documents?|accounts?|opportunities|alerts?)\b", text, re.I
            ):
                issues.append(("unnamed_workflow_object", "Identify what the routing workflow processes instead of implying a domain from the word routing."))
            if re.match(r"(?:Authored|Wrote|Documented)\b", text, re.I) and re.search(r"\b(?:plans?|design documents?)\b", text, re.I) and re.search(r"\b(?:increas\w* throughput|reduc\w* latency|cut\w* latency)\b", text, re.I):
                if not re.search(r"\b(?:implemented|deployed|projected|estimated|modeled|modelled|proposed)\b", text, re.I):
                    issues.append(("action_result_gap", "Distinguish a written plan from an implemented improvement or explicitly projected result."))
            if "batching strategies memoization" in text.lower():
                issues.append(("broken_grammar", "Rewrite the malformed implementation clause using supported actions and natural grammar."))
            if re.search(r"\bbuilding\b.*\band coordinated\b", text, re.I):
                issues.append(("parallel_grammar", "Use parallel grammar for the candidate's actions."))
            for code, message in issues:
                findings.append({"role_key": key, "bullet_number": index, "code": code, "message": message})
        for i, first in enumerate(bullets):
            for j in range(i):
                a = re.sub(r"[^a-z0-9% ]", " ", str(first).lower())
                b = re.sub(r"[^a-z0-9% ]", " ", str(bullets[j]).lower())
                if SequenceMatcher(None, a, b).ratio() > .86:
                    findings.append({"role_key": key, "bullet_number": i + 1, "code": "duplicate_accomplishment", "message": f"Substantially repeats bullet {j + 1}; use a distinct supported contribution."})
    return findings


def quality_issue_messages(payload: dict, blueprints: list[dict]) -> list[str]:
    return [
        f"{item['role_key']} bullet {item['bullet_number']} [{item['code']}]: {item['message']}"
        for item in bullet_quality_findings(payload, blueprints)
    ]


def experience_entry_schema(blueprint: dict, analysis: dict | None = None) -> dict:
    """Return project narrative and requirement links with the final bullets."""
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "title": {"type": "string", **({"enum": [blueprint["default_title"]]} if blueprint.get("default_title") else {})},
            "contribution_plan": {"type": "array", "items": {"type": "string"}, "minItems": blueprint["bullet_min"], "maxItems": blueprint["bullet_max"]},
            "project_narrative": {
                "type": "object", "additionalProperties": False,
                "properties": {name: {"type": "string"} for name in (
                    "system", "users", "workflow", "personal_contribution", "evidence_limits",
                )},
                "required": ["system", "users", "workflow", "personal_contribution", "evidence_limits"],
            },
            "bullets": {
                "type": "array", "items": {"type": "string"},
                "minItems": blueprint["bullet_min"], "maxItems": blueprint["bullet_max"],
            },
            "bullet_evidence": {
                "type": "array", "minItems": blueprint["bullet_min"], "maxItems": blueprint["bullet_max"],
                "items": {"type": "object", "additionalProperties": False,
                    "properties": {
                        "bullet_number": {"type": "integer", "minimum": 1, "maximum": blueprint["bullet_max"]},
                        "source_refs": {"type": "array", "items": {"type": "string"}},
                        "confirmation_questions": {"type": "array", "items": {"type": "string"}},
                        "measurement": measurement_schema(),
                    }, "required": ["bullet_number", "source_refs", "confirmation_questions", "measurement"]},
            },
            "requirement_evidence": {
                "type": "array",
                **({"minItems": len(project_characteristics(analysis)["priority_requirements"]), "maxItems": len(project_characteristics(analysis)["priority_requirements"])} if analysis is not None else {}),
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "requirement_number": {"type": "integer", "minimum": 1, **({"maximum": max(1, len(project_characteristics(analysis)["priority_requirements"]))} if analysis is not None else {})},
                        "fit": {"type": "string", "enum": ["direct", "transferable", "gap"]},
                        "bullet_numbers": {"type": "array", "items": {"type": "integer", "minimum": 1}},
                        "reason": {"type": "string"},
                    },
                    "required": ["requirement_number", "fit", "bullet_numbers", "reason"],
                },
            },
        },
        "required": ["title", "contribution_plan", "project_narrative", "bullets", "bullet_evidence", "requirement_evidence"],
    }


def requirement_link_issues(payload: dict, blueprints: list[dict], analysis: dict) -> list[str]:
    """Check references, not semantic relevance. Old drafts remain readable."""
    issues = []
    count = len(project_characteristics(analysis)["priority_requirements"])
    for blueprint in blueprints:
        key = blueprint["key"]
        role = (payload.get("experience") or {}).get(key) or {}
        links = role.get("requirement_evidence")
        if links is None:
            continue
        if not isinstance(links, list):
            issues.append(f"{key} requirement evidence must be a list.")
            continue
        seen = set()
        size = len(role.get("bullets") or [])
        for link in links:
            if not isinstance(link, dict):
                issues.append(f"{key} requirement evidence must contain objects.")
                continue
            number = link.get("requirement_number")
            if type(number) is not int or not 1 <= number <= count or number in seen:
                issues.append(f"{key} has an invalid or duplicate priority requirement reference.")
                continue
            seen.add(number)
            numbers = link.get("bullet_numbers")
            if not isinstance(numbers, list) or any(type(n) is not int or not 1 <= n <= size for n in numbers):
                issues.append(f"{key} requirement {number} references a nonexistent bullet.")
                continue
            fit = link.get("fit")
            if fit not in {"direct", "transferable", "gap"} or (fit == "gap" and numbers) or (fit != "gap" and not numbers):
                issues.append(f"{key} requirement {number} must link supporting bullets or explicitly remain a gap.")
        if seen != set(range(1, count + 1)):
            issues.append(f"{key} must assess every priority requirement, including gaps.")
    return issues


CONFIRMATION_RE = re.compile(r"\[Confirm(?: metric)?\s*:[^\]]*\]", re.I)


def role_source_map(blueprint: dict) -> dict:
    sources = {}
    for field, value in role_evidence(blueprint).items():
        if isinstance(value, list):
            sources.update({f"{field}.{i}": item for i, item in enumerate(value, 1)})
        elif isinstance(value, dict):
            sources.update({f"{field}.{key}": item for key, item in value.items()})
        else:
            sources[field] = value
    return sources


def claim_evidence_issues(payload: dict, blueprints: list[dict], numeric_tokens) -> list[str]:
    """Validate new draft provenance; saved legacy drafts remain readable.

    Source association is explicit. Semantic fidelity is additionally reviewed by
    the model; matching numeric tokens is necessary, not sufficient, evidence.
    """
    issues = []
    for bp in blueprints:
        role = (payload.get("experience") or {}).get(bp["key"]) or {}
        evidence = role.get("bullet_evidence")
        if evidence is None:
            continue
        bullets = role.get("bullets") or []
        sources = role_source_map(bp)
        if role.get("title") != bp.get("default_title"):
            issues.append(f"{bp['key']}: preserve historical title exactly: {bp.get('default_title', '')}.")
        seen = set()
        for item in evidence:
            n = item.get("bullet_number")
            if type(n) is not int or not 1 <= n <= len(bullets) or n in seen:
                issues.append(f"{bp['key']}: invalid or duplicate bullet evidence reference.")
                continue
            seen.add(n)
            bullet = str(bullets[n - 1])
            refs = [ref.removeprefix(bp["key"] + ".") for ref in (item.get("source_refs") or [])]
            questions = item.get("confirmation_questions") or []
            if any(ref not in sources for ref in refs):
                issues.append(f"{bp['key']} bullet {n}: cite only actual role source references.")
            if (not refs and not re.search(r"\[Confirm\s*:", bullet, re.I)) or (questions and not CONFIRMATION_RE.search(bullet)):
                issues.append(f"{bp['key']} bullet {n}: missing inline [Confirm: ...] marker for unverified claims.")
            if CONFIRMATION_RE.search(bullet) and not questions:
                issues.append(f"{bp['key']} bullet {n}: provide a concrete confirmation question.")
            cited_source_text = str([sources[r] for r in refs if r in sources])
            for specialized_claim in (r"\bDAQ\b", r"\bCAN(?:[- ]bus)?\b", r"\bpowertrain\b", r"\bdrivetrain\b", r"\btorque derat\w*", r"\bvehicle (?:data[- ]logging|data[- ]collection) hardware\b"):
                flags = 0 if specialized_claim.startswith(r"\bCAN") else re.I
                if re.search(specialized_claim, bullet, flags) and not re.search(specialized_claim, cited_source_text, flags):
                    issues.append(f"{bp['key']} bullet {n}: specialized hardware or controls claim is absent from cited role evidence; use supported software work and leave the JD-specific requirement as a review gap.")
                    break
            unsupported = numeric_tokens(bullet) - numeric_tokens([sources[r] for r in refs if r in sources])
            if unsupported:
                issues.append(f"{bp['key']} bullet {n}: unsupported metrics {', '.join(sorted(unsupported))}; preserve the cited source quantity, unit and qualifier or remove the unsupported measurement. Keep measurement questions in review metadata, never in resume text.")
            if incompatible_time_units(bullet, [sources[r] for r in refs if r in sources]):
                issues.append(f"{bp['key']} bullet {n}: measurement units differ from the cited source; preserve the original measurement and unit.")
            measurement = item.get('measurement')
            if isinstance(measurement, dict):
                kind = measurement.get('kind')
                if kind == 'qualitative' and (measurement.get('value') or measurement.get('unit') or numeric_tokens(bullet)):
                    issues.append(f"{bp['key']} bullet {n}: qualitative evidence must not contain a claimed measurement; classify supported numerical scope or improvement correctly.")
                elif kind in {'improvement', 'scale'}:
                    if not measurement.get('measure') or not measurement.get('value') or not measurement.get('unit'):
                        issues.append(f"{bp['key']} bullet {n}: numerical evidence must name its measure, supplied value and unit.")
                    if kind == 'improvement' and not measurement.get('connection'):
                        issues.append(f"{bp['key']} bullet {n}: improvement evidence must explain the source-supported action/result connection.")
                    record_numbers = numeric_tokens(' '.join(str(measurement.get(field) or '') for field in ('value', 'unit')))
                    if record_numbers - numeric_tokens([sources[r] for r in refs if r in sources]) or record_numbers - numeric_tokens(bullet):
                        issues.append(f"{bp['key']} bullet {n}: measurement metadata must match both the cited source and the visible bullet.")
        if seen != set(range(1, len(bullets) + 1)):
            issues.append(f"{bp['key']}: provide source references or confirmation questions for every bullet.")
        for link in role.get("requirement_evidence") or []:
            if link.get("fit") == "direct" and any(
                not any(e.get("source_refs") for e in evidence if e.get("bullet_number") == n)
                for n in link.get("bullet_numbers", []) if type(n) is int and 1 <= n <= len(bullets)
            ):
                issues.append(f"{bp['key']}: proposed work cannot establish direct requirement evidence.")
    return issues


def pending_confirmation_findings(payload: dict, blueprints: list[dict]) -> list[dict]:
    return [
        {"role_key": bp["key"], "bullet_number": i, "confirmation": match.group(0)}
        for bp in blueprints
        for i, bullet in enumerate(((payload.get("experience") or {}).get(bp["key"]) or {}).get("bullets") or [], 1)
        for match in CONFIRMATION_RE.finditer(str(bullet))
    ]


def prepare_experience_draft(payload: dict, blueprints: list[dict], numeric_tokens) -> dict:
    """Render provenance in the draft itself so metadata cannot hide uncertainty.

    Adds only confirmation labels/questions, never facts or numeric values.
    Legacy payloads without the new provenance contract are left intact.
    """
    result = deepcopy(payload)
    for bp in blueprints:
        role = (result.get('experience') or {}).get(bp['key']) or {}
        evidence = role.get('bullet_evidence')
        if not isinstance(evidence, list):
            continue
        bullets = role.get('bullets') or []
        by_number = {item.get('bullet_number'): item for item in evidence if isinstance(item, dict)}
        required = (len(bullets) * 4 + 4) // 5
        reserved = sum(bool(numeric_tokens(b)) or bool(re.search(r'\[Confirm metric:', str(b), re.I)) for b in bullets)
        for i, value in enumerate(bullets, 1):
            item = by_number.get(i)
            if item is None:
                continue
            text = str(value)
            refs = item.get('source_refs') or []
            questions = list(item.get('confirmation_questions') or [])
            if not refs and not re.search(r'\[Confirm\s*:', text, re.I):
                text = '[Confirm: proposed work] ' + text
                if not questions:
                    questions.append('Did you perform this proposed contribution in this role?')
            elif questions and not CONFIRMATION_RE.search(text):
                text = '[Confirm: details require confirmation] ' + text
            if not refs and reserved < required and not numeric_tokens(text) and not re.search(r'\[Confirm metric:', text, re.I):
                measure = next((re.sub(r'^Confirm metric:\s*', '', str(q), flags=re.I).rstrip('?') for q in questions if str(q).lower().startswith('confirm metric:')), 'measured outcome for this contribution')
                text += f' [Confirm metric: {measure}]'
                reserved += 1
                questions.append('What source-supported measurement belongs to this accomplishment?')
            if CONFIRMATION_RE.search(text) and not questions:
                questions.append('Please confirm the marked detail before using this accomplishment.')
            bullets[i - 1] = text
            item['confirmation_questions'] = questions
        role['bullets'] = bullets
        unconfirmed = {n for n, item in by_number.items() if not item.get('source_refs')}
        for link in role.get('requirement_evidence') or []:
            numbers = link.get('bullet_numbers') or []
            retained = [n for n in numbers if n not in unconfirmed]
            if numbers and not retained:
                link.update(fit='gap', bullet_numbers=[], reason='Proposed contributions require confirmation; they do not yet establish candidate evidence for this requirement.')
            elif retained != numbers:
                link['bullet_numbers'] = retained
    return result


REVIEW_PROSE_RE = re.compile(
    r"supplied (?:experience |profile |candidate )?record|(?:this resume|the resume) therefore|"
    r"does not include verified|verified accomplishment bullets|evidence needed to validate|"
    r"(?:missing|lack of) (?:verified |confirmed )?(?:candidate |profile )?evidence|"
    r"the candidate(?:'s)?|the supplied (?:profile|experience)", re.I,
)


def resume_body_issues(payload: dict, blueprints: list[dict]) -> list[str]:
    issues = []
    visible = [payload.get('updated_title', ''), payload.get('updated_summary', '')]
    for group in payload.get('updated_skills', []) or []:
        visible.extend([group.get('category', ''), *(group.get('items', []) or [])])
    for role in (payload.get('experience') or {}).values():
        visible.extend(role.get('bullets', []) or [])
    if any(re.search(r'\b(?:illustrative(?:[_\s-]+unverified)?|unverified|needs[_-]user[_-]confirmation)\b', str(text), re.I) for text in visible):
        issues.append('Resume text contains an internal measurement/review status label. Keep status in metadata and review notes, never in resume sentences.')
    if REVIEW_PROSE_RE.search(str(payload.get('updated_summary') or '')):
        issues.append('Summary contains internal review commentary; write a professional summary using actual candidate work and put evidence gaps only in review notes.')
    for bp in blueprints:
        role = (payload.get('experience') or {}).get(bp['key']) or {}
        for n, bullet in enumerate(role.get('bullets') or [], 1):
            if CONFIRMATION_RE.search(str(bullet)):
                issues.append(f"{bp['key']} bullet {n}: unverified proposal or confirmation request cannot be delivered as resume content; use supported work and report the requirement gap outside the resume.")
    return issues

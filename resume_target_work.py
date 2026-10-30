"""JD-grounded work model, separate from candidate history and routing labels."""
from copy import deepcopy
import re
import unicodedata


def jd_source_spans(job_description):
    spans = list(dict.fromkeys(s.strip() for s in re.split(
        r'(?<=[.!?])\s+|(?<=[.!?])(?=[A-Z][a-z])|[\r\n;]+', job_description) if s.strip()))
    return {f'jd_span_{i}': text for i, text in enumerate(spans, 1)}


def _comparison_text(text):
    text = unicodedata.normalize('NFKC', str(text)).casefold()
    text = text.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '–': '-', '—': '-', '‑': '-', '‐': '-'}))
    return re.sub(r'\s+', ' ', text).strip()


def normalize_target_work(analysis, job_description):
    """Resolve selected original JD text, never invent or broaden a capability."""
    result = deepcopy(analysis)
    work = result.get('target_work')
    if not isinstance(work, dict):
        return result
    spans = jd_source_spans(job_description)
    source = _comparison_text(job_description)
    for field in ('users', 'work_objects'):
        values = work.get(field)
        if not isinstance(values, list):
            continue
        grounded, omitted = [], []
        for value in values:
            if isinstance(value, str) and value.strip() and _comparison_text(value) in source:
                grounded.append(value)
            else:
                omitted.append(str(value))
        work[field] = grounded
        if omitted:
            note = f"Unconfirmed {field} omitted; not explicitly stated in the posting: " + ', '.join(omitted)
            unknowns = work.setdefault('unknowns', [])
            if note not in unknowns:
                unknowns.append(note)
    for requirement in work.get('specialist_requirements') or []:
        if not isinstance(requirement, dict):
            continue
        ref = requirement.get('source_span_id')
        if ref in spans:
            # No independently generated label to paraphrase or misattach.
            requirement.clear()
            requirement.update(capability=spans[ref], jd_quote=spans[ref])
    return result


def target_work_schema(job_description=None):
    properties = {key: {"type": "string", "minLength": 1} for key in (
        "system_type", "primary_workflow",
    )}
    properties.update({key: {"type": "array", "items": {"type": "string"}} for key in (
        "users", "work_objects", "engineering_changes", "evidence_expectations", "unknowns",
    )})
    for key in ("engineering_changes", "evidence_expectations"):
        properties[key]["minItems"] = 1
    properties["specialist_requirements"] = {
        "type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {key: {"type": "string", "minLength": 1} for key in ("capability", "jd_quote")},
            "required": ["capability", "jd_quote"],
        },
    }
    if job_description:
        properties['specialist_requirements']['items'] = {
            'type': 'object', 'additionalProperties': False,
            'properties': {'source_span_id': {'type': 'string', 'enum': list(jd_source_spans(job_description))}},
            'required': ['source_span_id'],
        }
    # Extract specialist evidence before describing a system, so the model does
    # not first anchor its description on company industry or a generic title.
    properties = {"specialist_requirements": properties.pop("specialist_requirements"), **properties}
    return {"type": "object", "additionalProperties": False,
            "properties": properties, "required": list(properties)}


def target_work_rules():
    return "\n".join([
        "TARGET WORK BEFORE TECHNOLOGY CLASSIFICATION:",
        "Read the whole JD, including specialist qualification sections, before choosing the role family or route.",
        "First construct target_work: what kind of system is being built, its principal workflow, users and objects (only if stated), implementation changes, specialist requirements and the evidence that would demonstrate them.",
        "Extract specialist_requirements FIRST from responsibilities/qualifications. When job_description_spans are supplied, select their source_span_id values; the server supplies each original capability and quote. Do not reconstruct, paraphrase or join source quotes, and do not return separate capability/jd_quote fields when the schema requests IDs.",
        "For legacy schemas requesting capability and jd_quote, copy a short exact capability phrase inside its own contiguous quote. Never attach a platform capability to an unrelated quote about experience duration or generic software practices.",
        "system_type must name a system class, such as native mobile applications, event-processing services or analytics pipelines. Company products and marketing are not evidence of which product this vacancy builds.",
        "primary_workflow must connect the concrete engineering operations required in the posting, rather than merely say 'develop applications'. Extract engineering_changes from duties (for example implement modules, consume service responses, write tests or troubleshoot) and evidence_expectations from what would demonstrate those capabilities. Both lists must be nonempty.",
        "Exclude page furniture, applicant analytics, benefits and company business descriptions from target-work inference. For example, a retailer's native-app qualification section establishes native-app work, but not a checkout, delivery or inventory project unless duties explicitly name it.",
        "For users and work_objects, extract only noun phrases explicitly present in the role duties/qualifications, copied verbatim. Otherwise return empty lists and record the unknown; do not invent plausible end users.",
        "Users and work_objects are optional context. Omit uncertain or paraphrased entries and record them only as unknowns; do not infer a particular product or customer group to fill these lists.",
        "A language/tool inventory or generic 'scalable software' description is not a system/workflow description. Describe the application or operational capability the engineer must implement.",
        "Specialist references must select actual source text about the specialization. The server resolves ID-based citations; legacy quotes must be exact contiguous spans. Give platform and functional specialization priority over boilerplate duties, without inventing products or changing requirement priority.",
        "Choose a precise role_family even when the fixed generation route is broader. The route selects a writing template; it does not define or replace target_work.",
        "For native/mobile application work, preserve that specialization in system_type, role_family, workflow and evidence expectations. Use fullstack_product as the broad software route when no dedicated native route is available; consuming REST APIs does not turn a native-app role into backend engineering.",
        "Do not invent a particular employer product, feature, user group or business workflow from the company industry. If not stated, put it in unknowns and use a supported application-level description.",
        "This call has no candidate history: never assume years of experience or return candidate weaknesses. gaps may describe only ambiguities in the posting; unknown candidate fit is not a gap established by the JD.",
        "Derive core_problem, system_description, top_requirements and workflows from target_work, then choose the closest available route. Keep specialist capabilities prominent in top_requirements.",
    ])


def target_work_issues(analysis, job_description):
    work = analysis.get("target_work")
    if not isinstance(work, dict):
        return ["Missing target_work: identify the target system and workflow before routing."]
    issues = []
    for key in ("system_type", "primary_workflow"):
        if not str(work.get(key) or "").strip():
            issues.append(f"target_work.{key} must describe actual work required by the posting.")
    for key in ("engineering_changes", "evidence_expectations"):
        if not isinstance(work.get(key), list) or not work[key] or not all(isinstance(v, str) and v.strip() for v in work[key]):
            issues.append(f"target_work.{key} must identify concrete required engineering work and evidence.")
    normalize = lambda value: re.sub(r"\s+", " ", str(value)).strip()
    jd = _comparison_text(job_description)
    for index, requirement in enumerate(work.get("specialist_requirements") or [], 1):
        if not isinstance(requirement, dict):
            issues.append(f"Specialist requirement {index} must be a grounded requirement object.")
            continue
        if 'source_span_id' in requirement:
            issues.append(f"Specialist requirement {index} has an unresolved or invalid JD source reference: {requirement['source_span_id']!r}.")
        quote = normalize(requirement.get("jd_quote") or "")
        if not quote or _comparison_text(quote) not in jd:
            issues.append(f"A specialist requirement quote is absent from the JD; cite exact posting text. Requirement {index}: quote={quote!r}")
        capability = normalize(requirement.get("capability") or "")
        if not capability or _comparison_text(capability) not in _comparison_text(quote):
            issues.append(f"A specialist capability must be stated inside its own JD quote; unrelated evidence cannot support it. Requirement {index}: capability={capability!r}; quote={quote!r}")
    for field in ("users", "work_objects"):
        for value in work.get(field) or []:
            if not str(value).strip() or _comparison_text(value) not in jd:
                issues.append(f"target_work.{field} must use posting text, not inferred product context.")
    return issues


def target_work_context(analysis):
    work = analysis.get("target_work")
    return deepcopy(work) if isinstance(work, dict) else {}

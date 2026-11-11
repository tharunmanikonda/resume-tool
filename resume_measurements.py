"""Shared measurement contract and conservative quantity normalization."""
import re
from decimal import Decimal


def format_percentage_symbols(text):
    """Format explicit numeric percentages without changing percentage-point units."""
    text = re.sub(r'(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(?:percent|per\s+cent)\b',
                  r'\1%', str(text), flags=re.I)
    return re.sub(r'(?<=\d)\s+%', '%', text)


def measurement_rules():
    return "\n".join([
        "NUMERICAL EVIDENCE CONTRACT (applies to drafting, repair and review):",
        "Before writing, identify from cited source evidence: personal action, specific system/workflow, measure, supplied value/unit/qualifier, population or time context if supplied, and the action/result connection.",
        "Choose improvement, scale, or qualitative evidence. Improvement: implemented action + workflow + measured change + supported causal mechanism. Scale: implemented action + workflow + measured operating scope; scope is not an improvement. Qualitative: concrete supported contribution when no measurement is supplied.",
        "Write percentage quantities with the % symbol attached to the number: 30%, not 30 percent or 30 %. Preserve percentage-point differences as percentage points; do not change their meaning.",
        "Use XYZ naturally; do not force a numeric result or a fixed sentence order. Keep the 80% numerical target, counting both supported improvement and scale. Report any remaining shortfall outside resume text.",
        "Preserve the measurement's original meaning, unit, bound/approximation, population and period. Never invent a baseline or convert a final-state measurement into an improvement. Do not move a number to another accomplishment.",
        "Treat 'over 50,000' and '50,000+' as equivalent scope notation. Preserve '<', 'at least', 'approximately' and similar qualifiers; never turn an estimate/bound into an exact count or reverse its direction.",
        "Source provenance does not prove causality. Monitoring/dashboards alone do not explain reduced latency; authentication alone does not explain data-integrity improvements. Name an actual source-supported intervention or limit the claim to the supported observation/action.",
        "When the connection or measurement is missing, retain a supported qualitative or scale claim; put the limitation in review metadata. Do not ask to reconfirm a supplied measurement. Never insert questions, confirmation placeholders or measurement requests into resume sentences.",
        "For every bullet_evidence measurement record, describe its kind, measure, value, unit, context and connection using only cited sources. Empty strings represent missing details, never permission to invent them. A qualitative record has empty value and unit.",
    ])


def measurement_schema():
    props = {"kind": {"type": "string", "enum": ["improvement", "scale", "qualitative"]}}
    props.update({key: {"type": "string"} for key in ("measure", "value", "unit", "context", "connection")})
    return {"type": "object", "additionalProperties": False, "properties": props, "required": list(props)}


_SMALL = dict(zip(
    'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(),
    range(20),
))
_SMALL.update(dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(), range(20, 100, 10))))
_SCALES = {'hundred': 100, 'thousand': 1000, 'million': 1000000, 'billion': 1000000000}
_WORD = '(?:' + '|'.join([*_SMALL, *_SCALES]) + ')'
_WORDS_RE = re.compile(r'\b' + _WORD + r'(?:[ -]+(?:and\s+)?' + _WORD + r')*\b', re.I)


def normalize_number_words(text):
    text = re.sub(r'\bsub[- ]second\b', 'under 1 second', text, flags=re.I)
    def replace(match):
        total = current = 0
        for word in re.split(r'[ -]+', match.group().lower()):
            if word == 'and':
                continue
            if word in _SMALL:
                current += _SMALL[word]
            elif word == 'hundred':
                current = (current or 1) * 100
            else:
                total += (current or 1) * _SCALES[word]
                current = 0
        return str(total + current)
    return _WORDS_RE.sub(replace, text)


def canonical_quantity(raw, before):
    token = re.sub(r'\s+', '', raw.lower()).replace(',', '')
    token = re.sub(r'percent(?:age)?s?', '%', token)
    # Scale abbreviations are numeric notation; binary-size units remain units.
    match = re.fullmatch(r'([$€£]?)(\d+(?:\.\d+)?)([kmb])(\+?)', token)
    if match:
        value = Decimal(match[2]) * {'k': 1000, 'm': 1000000, 'b': 1000000000}[match[3]]
        token = match[1] + format(value, 'f').rstrip('0').rstrip('.') if value % 1 else match[1] + str(int(value))
        token += match[4]
    qualifiers = [
        (r'(?:at least|no fewer than|>=|≥)\s*$', '>='),
        (r'(?:at most|up to|no more than|<=|≤)\s*$', '<='),
        (r'(?:less than|fewer than|under|below|<)\s*$', '<'),
        (r'(?:more than|greater than|over|above|>)\s*$', '+'),
        (r'(?:approximately|about|roughly|~|≈)\s*$', '~'),
    ]
    for pattern, qualifier in qualifiers:
        if re.search(pattern, before, re.I):
            return token.rstrip('+') + '+' if qualifier == '+' else qualifier + token
    return token


_TIME_UNITS = {
    'ms': 'millisecond', 'msec': 'millisecond', 'msecs': 'millisecond',
    'millisecond': 'millisecond', 'milliseconds': 'millisecond',
    's': 'second', 'sec': 'second', 'secs': 'second', 'second': 'second', 'seconds': 'second',
    'min': 'minute', 'mins': 'minute', 'minute': 'minute', 'minutes': 'minute',
    'hour': 'hour', 'hours': 'hour', 'day': 'day', 'days': 'day',
    'week': 'week', 'weeks': 'week', 'month': 'month', 'months': 'month', 'year': 'year', 'years': 'year',
}
_TIMED_QUANTITY = re.compile(r'(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(' + '|'.join(sorted(_TIME_UNITS, key=len, reverse=True)) + r')\b', re.I)


def incompatible_time_units(bullet, sources):
    """Catch changed units, without treating this as a general causality check."""
    def pairs(text):
        return [(Decimal(n.replace(',', '')), _TIME_UNITS[u.lower()])
                for n, u in _TIMED_QUANTITY.findall(normalize_number_words(text))]
    source_pairs = pairs(' '.join(str(source) for source in sources))
    return [(str(value), unit) for value, unit in pairs(bullet) if (value, unit) not in source_pairs]


def visible_ratio_matches_measurement(text, measurement):
    """Recognize a stated per-unit ratio at its declared decimal precision.

    This only checks explicit numerator/denominator arithmetic with matching
    units. It does not invent observations, convert unrelated units, accept
    zero denominators, or infer an unstated denominator from metadata.
    """
    from decimal import InvalidOperation, ROUND_HALF_UP, localcontext
    unit = str(measurement.get('unit', '')).strip().lower()
    parts = re.fullmatch(r'([a-z][a-z-]*)\s*(?:per|/)\s*([a-z][a-z-]*)', unit)
    if not parts:
        return False
    def noun_pattern(noun):
        stem = noun[:-1] if noun.endswith('s') and not noun.endswith('ss') else noun
        return re.escape(stem) + r's?'
    numerator_unit, denominator_unit = (noun_pattern(part) for part in parts.groups())
    number = r'(?<![\w.\-])(\d[\d,]*(?:\.\d+)?)'
    pattern = number + r'\s+(?:(' + numerator_unit + r')\s+)?per\s+' + number + r'\s+(' + denominator_unit + r')\b'
    normalized = normalize_number_words(text).lower()
    declared = str(measurement.get('value', '')).strip().replace(',', '')
    if not re.fullmatch(r'\d+(?:\.\d+)?', declared):
        return False
    try:
        expected = Decimal(declared)
        if not expected.is_finite():
            return False
        for match in re.finditer(pattern, normalized):
            # "one incident per three releases" names the numerator inline;
            # "incidents to one per three releases" names it just before it.
            if not match[2] and not re.search(r'\b' + numerator_unit + r'\s+(?:(?:to|at|of)\s+)?$', normalized[max(0, match.start()-80):match.start()]):
                continue
            numerator, denominator = Decimal(match[1].replace(',', '')), Decimal(match[3].replace(',', ''))
            if denominator <= 0:
                continue
            with localcontext() as ctx:
                ctx.prec = max(28, len(declared) + 10)
                ratio = numerator / denominator
                if expected == ratio:
                    return True
                if expected > 0 and expected.as_tuple().exponent < 0:
                    rounded = ratio.quantize(Decimal(1).scaleb(expected.as_tuple().exponent), rounding=ROUND_HALF_UP)
                    if rounded == expected:
                        return True
    except (InvalidOperation, ArithmeticError, ValueError):
        pass
    return False

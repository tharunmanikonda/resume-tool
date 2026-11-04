# Measurement contract and checker fix

## Implemented

XYZ and the 80% numerical-evidence target remain. Drafting now uses one measurement contract shared with synthesis and final review:

1. Identify the personal action, system/workflow, measure, source value, unit/qualifier, supplied context and action/result connection before writing.
2. Classify evidence as **improvement**, **scale** or **qualitative**. Scale counts as numerical evidence but must not be presented as a measured improvement.
3. Preserve the original measurement meaning, bound, unit, population and period. Do not invent baselines or transfer a number to another accomplishment.
4. If measurement or causal detail is missing, retain a concrete supported qualitative/scale claim and keep the limitation outside resume text. Do not reconfirm supplied numbers or insert measurement questions into bullets.

Every newly generated bullet's internal evidence entry requires a measurement record with kind, measure, value, unit, context and connection. It does not appear in the exported resume. Legacy entries remain readable. Validation checks agreement between numerical metadata, cited sources and the visible bullet, requires an action/result connection for improvement records, and rejects contradictory qualitative labels. These checks establish consistency, not independent verification of employment facts or all semantic causality.

The repair message for an unsupported number now asks the model to preserve the source quantity/unit/qualifier or remove the unsupported measurement. It no longer directs the model to insert a confirmation placeholder. Numerical-coverage messages similarly keep missing-measurement requests outside resume text.

## Checker changes

- Recognizes written quantities, including compound forms such as twenty-five and one hundred and ten.
- Recognizes quantities with modifiers, including monthly audit transactions, telemetry metrics and enterprise applications.
- Normalizes equivalent scope notation: over 50,000 and 50,000+; 1M and 1,000,000.
- Recognizes sub-second as a less-than-one-second bound.
- Preserves distinctions between exact, lower-bound, upper-bound and approximate quantities. A bound cannot silently become an exact value or reverse direction.
- Rejects changed explicit time units, including equal numeric values with different time units.
- Continues to exclude software/protocol version numbers from numerical accomplishment coverage.

The checker does not prove that every source claim has a sound causal explanation. The shared review instructions and measurement connection record address that separate judgment. It does not automatically rewrite an ambiguous source claim into an invented explanation.

## Verification

**448 Python tests passed.** Regression cases cover equivalent quantities, written numbers, modifiers, scale abbreviations, bounds, approximations, changed values, time-unit changes, software versions, measurement-record consistency and shared prompt coverage.

Replayed the saved original baseline and target-work-fix AI responses locally through the updated provenance checker. Both previously triggered the false unsupported-50000+ repair; both now have zero numerical-provenance issues. No fresh OpenAI request was made for this change, and no saved resume was replaced. This verifies local parsing and prompt/schema handoffs, not a fresh end-to-end model-generation result.

The current saved Domino’s resume's numerical-coverage counts are now McKinsey 5/6, Uber 4/5, KPMG 5/5 and Trigent 3/3. These counts include scale and quantified bounds; meeting the numerical target does not resolve its previously documented story, fit or causal-wording issues. Existing stored review notes are not rewritten by this code change.

Private replay details: `tmp/dominos-content-review/measurement-replay.json`.

Implementation: `resume_measurements.py`, the shared bullet schema/evidence checks in `resume_bullet_quality.py`, and generation/audit numeric handling in `app.py`.

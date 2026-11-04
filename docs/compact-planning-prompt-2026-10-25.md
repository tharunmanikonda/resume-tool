# Compact planning prompt

Changed only `PLAN_PROMPT`. The schema, writer, reviewer, validation checks and repair flow are unchanged.

Keep JD interpretation: positioning, target system/purpose, workflow, required and optional capabilities with source-clause references. Use explicit output word budgets: positioning 25, target system 25, target workflow 20, requirement label 8, and up to three unknowns of eight words each.

Per role: system 20 words, workflow 12, scope 15; up to three grouped essential assumptions of ten words each. Each contribution is at most 25 words: `action | mechanism | intended result | measurement opportunity and unit`. No long Work/Result/Measurement paragraphs. The 80% meaningful measurement-opportunity goal remains, without invented observed values.

These are prompt targets, not new hard validators or truncation rules. Output compliance and actual latency have not been measured in a live request.

Career depth applies per historical role using available dates, titles and career context. Earlier-career responsibility is narrower; later relevant work can be deeper. Do not infer stage from employer name, array position, selected-role count or JD demands. One selected role is not automatically the first job. Dates alone do not establish expertise, exact career start or leadership. Technologies must fit the period; JD alignment must not impose the entire target stack on earlier roles. Overall profile-mode positioning does not imply equal historical seniority.

Focused validation: 63 tests passed. No live API calls were run for this change, and no saved resume was rewritten.

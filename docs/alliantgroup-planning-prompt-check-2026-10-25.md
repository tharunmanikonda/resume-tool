# Planning-only measurement check

Only `PLAN_PROMPT` in `jd_draft_experiment.py` changed in this step. Writer, reviewer, schema, validators, UI and saved resume were unchanged. No app restart or generation retry was performed.

Each existing contribution string now prepares work/mechanism, result and measurement opportunity, or a reason for remaining qualitative. The prompt requests ceiling-rounded 80% opportunity coverage per role, forbids filler counts and asks for units without inventing observed values. These planning labels are explicitly excluded from eventual resume bullets.

One user-approved isolated planning request used the same alliantgroup JD, employment headings and professional-mode context. No saved profile accomplishments or source resume were supplied. It completed in 25.64 seconds and passed existing plan validation without repair.

| Role | Contributions | Measurement opportunities | Requested minimum |
| --- | ---: | ---: | ---: |
| McKinsey | 6 | 6 | 5 |
| Uber | 5 | 5 | 4 |
| KPMG | 5 | 5 | 4 |
| Trigent | 3 | 3 | 3 |

Examples: reporting-query latency in milliseconds; merge-to-staging lead time in minutes; ingestion success rate; frontend bundle size and page performance. These are ways to measure proposed work, not factual achievements or supplied measurements. Opportunity coverage is not numeric evidence coverage in a finished resume.

Manual assessment: the model followed the new structure and kept role-level system descriptions. Some opportunities are weaker than others: onboarding incidents and estimation accuracy depend on wider team/process factors; the final component-reuse entry confusingly calls an hours-based measure qualitative. One recent-role contribution says “Led performance and security review,” despite hands-on scope. These are findings for the next controlled decision, not changes made in this step. The existing validator does not assess these semantic questions.

The current writer has not been tested against this plan. No claim is made that it will preserve coverage or avoid copying planning labels into resume text. The next isolated comparison can feed this saved plan to the unchanged writer and inspect that handoff before modifying anything else.

Focused checks: 49 tests passed. Exact request and result are saved locally in `tmp/alliantgroup-plan-measurement-check/request.json` and `result.json`.

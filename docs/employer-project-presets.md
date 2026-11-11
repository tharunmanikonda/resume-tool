# Employer project presets

User-selected drafting contexts live in `config/employer_project_contexts.json`.
They supply domain boundaries and fallback purposes, not fixed bullets, languages,
metrics, titles, named clients or evidence of actual accomplishments.

| Employer | Context | Fallback |
| --- | --- | --- |
| McKinsey | Enterprise referral and internal workflows; client industry unspecified | Referral intake, validation, routing and status tracking |
| Uber | Ride-sharing and trip operations | Trip audits, fare validation and exception investigation |
| KPMG | Financial audit and compliance reporting | Audit reporting, supporting documents and review workflows |
| Trigent | Business web UI modernization; client industry unspecified | Assigned screens/forms, existing API connections, validation and tests |

The user confirmed these anchors from existing saved context. A JD can select a
naturally matching work area inside the employer boundary; otherwise the planner
uses the fallback business purpose. The JD guides engineering emphasis rather
than rewriting the employer into the target's product. Client industries left
unspecified must not be invented. Technical details and claims still require
confirmation against actual work.

Presets are selected by both role key and employer name, so a different profile
reusing a role key does not inherit another employer's context. Only selected
roles are supplied. New contexts participate in generation fingerprints; changing
a preset invalidates incompatible cached planning. Targeting, writing and review
receive the same contexts through the existing call boundary; no extra AI stage
is added. Planning policy version 12 invalidates old plans. Existing saved
resumes remain unchanged until the user explicitly regenerates or edits them.

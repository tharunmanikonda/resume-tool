# Specialist project planning prompt evaluation

Six isolated planning requests compared project-context and title instructions on
one saved Medrina JD. Employment titles and source accomplishments were absent.
Inputs, model settings and output schema were held fixed. Only prompts changed.
No saved resume or application was replaced.

| Variant | Change | Observation |
| --- | --- | --- |
| A | Choose an independent business context before applying the platform | Independent contexts and continuous Power Platform, but generic historical titles |
| B | Convert target use cases to transferable engineering mechanisms | Still copied ACO/EHR context |
| C | A plus a more specific title paragraph | Healthcare context returned under different wording; title variation remained |
| D | A plus consolidated career/continuity/title contract, replacing overlapping appended policies | Independent business contexts, Power Platform in all roles, conventional titles, smaller earliest-role scope |
| D2 | Exact repeat of D | Same four criteria met |
| D3 | Exact repeat of D | Same four criteria met |

The final three requests used identical prompt, input and schema. Their elapsed
times were 12.76, 12.52 and 11.63 seconds. Human inspection supplemented keyword
diagnostics: C still copied healthcare context via provider-network and regional
health-partnership wording that the original keyword list missed. Keyword absence
is not evidence of semantic independence by itself.

At that evaluation stage, the planner matched D's prompt, schema and parsed inputs
at the production call boundary (planning policy version 8). The subsequent
version 9 refinement allows ordinary shared industries, avoids copying distinctive
target products, and preserves technical career families without backdating every
modern tool. The current deployment uses version 9.
Existing downstream stages receive explicit handoff guidance to preserve independent
project purpose, specialist continuity, planned titles and chronological scope.
No model stage was added.

These were planning tests on one JD, not full resume generations or broad evidence
of reliability across roles. Three successful repeats support this candidate over
the previous variants, but do not prove universal correctness or establish factual
employment history. Candidate qualification gaps remain advisory outside resume
prose. Proposed project contexts and platform tenure still require confirmation.

Requests, responses and prompt diffs remain in the local
`tmp/medrina-prompt-evaluation/` directory. No external messages were sent.

## Subsequent writing and review evaluation

Five saved plans were tested downstream without rerunning planning. Four produced
complete drafts; the QA case exhausted its output budget and its automatic retry
timed out. Reviewer-only editorial tests then used the four saved final drafts.
Summaries and some skills improved, but review did not consistently correct weak
metrics or padding. Subjective content-only scores were approximately 7–8/10;
these are neither ATS scores nor evidence of factual employment history.

The reviewer now receives existing measurement metadata alongside typed bullet
IDs. Skills groups may be consolidated or removed using snapshot-scoped skill
IDs; removal occurs after replacements, preserving original targets. Removing
every skills group is rejected. The follow-up test also tightened skill guidance,
so improvements cannot be attributed to metadata visibility alone. A remaining
case contains an incidental step count with qualitative metadata that local
validation rejects; universal review reliability is not claimed.

The accepted implementation retains the existing word-count and numerical goals.
The user accepted practical content relevance rather than requiring perfect
editorial scores. Private inputs and outputs remain local under tmp/.

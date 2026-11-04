# Targeting check before writing

An independent, compact targeting call now runs after project planning and before core/experience writing. It reads the JD first, distinguishes levels and alternative team paths, identifies the selected scope's primary work and supporting strengths, and checks whether the proposed project actually follows those priorities. It is not a whole-plan rewrite or a keyword validator.

The call can return exact corrections to positioning, target system/workflow, role system/workflow/scope, contribution notes and stale role assumptions. Local application preserves role keys, dates/titles, contribution counts and unaffected content; stale/duplicate/invalid corrections fail explicitly. Source-clause references in the assessment resolve to original posting text. Uncertain level/team choices are explicitly conservative assumptions, not verified eligibility. Required AI work stays primary when the JD actually requires it; optional AI does not automatically define an unrelated role.

The assessed direction is passed to core writing, experience writing and final review, and saved with analysis. Planning and targeting decisions are checkpointed. A retry after a writing failure reuses both, rather than repeating the targeting call. Old writing checkpoints that never received a targeting check are discarded before new writing. The original grouped writing and reviewer-to-code-apply workflow remain intact.

## One approved live Wellabe check

Input: the same saved Wellabe JD, AI-heavy project plan and selected employment headings; no source accomplishments. Model: configured synthesis model. Exactly one request, 11.935 seconds; no saved-resume replacement.

The model returned `corrected` and explicitly chose a **conservative Level 2/common engineering scope**. Its rationale was: “The plan overweights optional AI and RAG while omitting the JD’s central .NET lifecycle requirements; use a conservative Level 2 common core.” It did not claim this established the candidate's hiring level.

| Before | Model's proposed correction |
| --- | --- |
| Applied AI and RAG-centered positioning | Maintainable .NET/full-stack enterprise features and production support |
| Web application plus secure RAG assistant | Enterprise web application with services, data access and integrations |
| RAG retrieval as first recent contribution | C#/.NET application features, SQL and service integration |
| MCP/LLM access as second contribution | Service APIs, authentication and error handling |
| Model-grounding tests | Unit, integration and scenario tests for application changes |

It returned 11 targeted replacements and preserved the older role contribution counts. The resulting plan passed existing local plan validation. The check excluded the separate Level 3 mobile/WPF/MAUI and policy/COBOL paths from its chosen common scope rather than combining all team requirements. It retained technical design, collaboration and process improvement as supporting dimensions.

This is evidence for the saved Wellabe example, not a guarantee of matching human judgment on every JD. The live response did not regenerate bullets. Subsequent local refinement allows corrections to stale assumptions as well; that additional field was not rerun live under the single-request approval. Whole-resume quality and total latency with the added stage still need testing.

## Validation and artifacts

533 Python tests passed; extension build and review UI smoke check passed. Tests cover exact atomic plan changes, unchanged required/optional citations, source-grounded priorities reaching both writing calls and final review, cached targeting reuse, profile-mode propagation, and existing save/review behavior. No fixed company names or fixed role count drive the implementation.

Exact live request/response: `tmp/wellabe-targeting-check/request.json`, `response.json`; corrected plan and grounded assessment: `checked-plan.json`. The saved Wellabe resume in the application was not changed.

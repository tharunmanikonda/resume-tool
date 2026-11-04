# Target-work analysis fix and verification

## Result

The analysis defect is confirmed and corrected in the shared app/extension generation code: the final live analysis identifies **native application engineering**, with **native mobile applications** as the target system and source-grounded Kotlin/Swift, REST-consumption, testing and tooling requirements. It no longer infers a pizza-ordering product or customer group from the employer's industry.

This is a fix for target interpretation and its downstream handoff, not a claim that all resume-writing issues are resolved. The isolated downstream test improved contribution ordering and made missing native employment evidence explicit, but still produced weak causal wording and overbroad architecture transfer claims. The known numeric-provenance bug still requests repair. No generated test content replaced the saved Domino’s resume.

## Production changes

- Added a required `target_work` analysis object: specialist requirements with JD quotations, system type, primary workflow, users, work objects, engineering changes, evidence expectations and unknowns.
- Extract specialist evidence before generating a system description. Company industry, page furniture and applicant analytics cannot establish a specific project or user group.
- Require each quoted capability to occur in its own supporting quotation. Require quotations and user/object phrases to exist in the posting. This catches an unrelated experience-duration quote attached to Kotlin/Swift.
- Require nonempty engineering-change and evidence-expectation lists, rather than accepting only a route label and tools.
- Removed the analysis prompt's assumption that the candidate has four-plus years of experience. JD-only analysis cannot establish candidate limitations.
- Preserve specialist role-family labels even when the closest existing template is broader. For native work, the general software route is `fullstack_product`; the semantic role remains native application engineering.
- Pass the complete target-work object through compact analysis and project characteristics, reaching skills, both experience paths, synthesis and audit.
- Added writing guidance to distinguish the target system from the actual employer system and avoid claiming CI/CD from caching, monitoring or data pipelines alone.
- Versioned the analysis cache and reject cached entries lacking a valid work model. App reanalysis and resumed extension generation refresh old analysis and invalidate dependent generated stage caches. App reanalysis preserves the user's edited resume text.
- Kept XYZ and the 80% numerical preference unchanged. This patch does not add mobile employment, new measurements or unsupported technologies.

## Live tests

Five actual API requests were used while testing the fix: one initial test, followed by four explicitly approved fix-verification requests. Each request used the existing configured model. Baseline diagnostics from the previous investigation are preserved separately.

| Test | Observed result | Decision |
| --- | --- | --- |
| Initial work-model analysis | Recognized mobile/web context but invented a pizza-ordering product/users; two quotations did not match source punctuation. | Rejected, not passed downstream. Tightened extraction and grounding. |
| Evidence-first analysis | Identified native mobile applications and left users/product unspecified, but attached a Kotlin/Swift capability to a years-of-experience quote. | Tightened capability-to-quote validation. |
| Corrected analysis v3 | Native application engineering; native mobile target; exact Kotlin/Swift, REST and architecture quotations; no inferred product/users. | Used for the isolated downstream comparison. |
| Recent experience using v3 analysis | Led McKinsey with backend APIs rather than enterprise AI adoption; explicitly marked native employment as a gap. Still retained AI source work, weak architecture transfer and dashboard/latency causality. | Partial improvement, not a finished resume. The existing 50,000-versus-50,000+ bug requested repair. A single-call guard prevented sending another repair request. |
| Final analysis v4 | Native application engineering; native mobile system; valid quotations; nonempty engineering changes and evidence expectations; unknown product/user details remain explicit. | Passed the final contract. |

Final analysis highlights:

- Role: native application engineering.
- Target system: native mobile applications.
- Priorities: Kotlin and/or Swift, consuming RESTful JSON services, unit testing and CI systems.
- Engineering changes: quality/performance implementation, build/deployment artifacts and production troubleshooting.
- Unknowns: specific user groups and application features.

The final workflow sentence remains broad. The posting itself does not establish a specific customer journey or product; the tool must not invent one to make the story more specific. The specialist requirements provide the concrete work characteristics that downstream evidence selection must address.

## What this proves and does not prove

The baseline analysis repeatedly selected backend engineering. Corrected analyses v3 and v4 selected native application engineering while retaining the same JD and configured analysis model. V3 was passed to actual experience generation with saved role sources and preliminary skills held fixed. The prompt instructions also changed, so this is a diagnostic before/after comparison, not a controlled estimate attributing every bullet change solely to analysis. It is one role, not a multi-role quality benchmark.

The experience test is deliberately not reported as a successful end-to-end generation: local validation requested repair for the already-known metric-recognition defect, and semantic weaknesses remained in raw output. Improving analysis does not supply missing employment evidence or repair ambiguous source claims by itself. Project ordering, numeric normalization, stricter semantic requirement coverage and causal sentence review remain separate defects from this patch.

## Verification and artifacts

Regression tests cover source quotation grounding, unrelated capability quotations, inferred user groups, rejecting old cache entries, rejecting invalid new analysis before caching, preservation through compaction/normalization, production prompt handoffs and app session-cache migration without deleting edited text. Existing app and extension pipeline tests also pass.

Final verification: **429 tests passed**. The idle local server was reloaded after confirming zero queued/running/pending generation tasks. Its status endpoint returned HTTP 200 and ready=true. The shared analysis fix is active for the app and extension. No saved resume was replaced.

Private prompts and outputs are preserved under `tmp/dominos-content-review/target-work-fix*`. The final validated result is `tmp/dominos-content-review/target-work-fix-v4/analysis-live-result.json`. The downstream comparison is in `target-work-fix-v3/recent-live-calls.json`; its second record is a local single-call-budget rejection, not a second API request.

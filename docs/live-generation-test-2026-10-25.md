# Live generation test — October 25, 2026

## Verdict

**Partially follows the goals; not ready to treat generated drafts as finished resumes.** JD-driven topic selection improved, and mandatory constraint clauses disappeared. Sentence quality, distinct accomplishments, source fidelity, historical titles, and reliable completion still fail in observable ways. The final audit helps but does not reliably repair these defects.

This is a content-generation test, not a measurement of any employer ATS or recruiter outcome. Preserve the intended XYZ approach and 80% numerical-evidence target; the failures concern how the tool satisfies them.

## Test scope

- Real-data tests: original saved OnPay, Rothera and BankPlus analysis/profile/history snapshots and raw JDs, with explicit user approval for the configured OpenAI API. Two recent roles per application; no new role evidence added.
- Controlled tests: one wholly synthetic candidate with ten supplied source accomplishments, tested against frontend, GTM and automation JDs. The same source evidence was used across these three cases.
- Actual application functions: skills generation, experience generation with validation/retries, followed by synthesis and quality audit for cases that generated successfully. Suggested audit changes were applied locally to inspect the resulting content.
- Generation model: gpt-5-mini. Successful synthesis/audit calls used configured gpt-5.6-luna.
- Six cases, one run per case with built-in retries. Three completed through audit; three failed before synthesis. This small sample is diagnostic, not a statistical benchmark.
- Outputs are local test artifacts. Saved applications, resumes and email were not changed. No applications or messages were sent.

## Run results

| Case | Result | Observations |
|---|---|---|
| Real: OnPay | Completed through audit | GTM focus improved; unverified lead volumes, conversion results and vague visibility metric survived. Historical role titles changed. |
| Real: Rothera | Failed after experience retry | Three actual priority requirements; both attempts added an invalid fourth requirement link. |
| Real: BankPlus | Failed after experience retry | Same three-versus-four requirement-link failure. First returned role still opened with applied AI framing. |
| Synthetic: frontend | Completed through audit | Frontend focus correct. Bad grammar survived because the proposed repair was withheld; unsupported screen-reader detail survived. |
| Synthetic: automation | Completed through audit | Audit removed unsupported record volume and implementation details. Duplicate reconciliation result and inappropriate skill categories remained. |
| Synthetic: GTM | Failed during skills generation | Both skills attempts exhausted output tokens (2900 then 4800); no experience generated. |

## What meets the goals

- The generated Rothera sample discusses React/TypeScript internal applications, and OnPay discusses GTM pipelines, routing and CRM work. Controlled frontend and automation cases likewise produce different focuses from the same supplied history.
- Successful cases no longer require a forced “under [constraint]” clause.
- Generated experience includes project narrative metadata and bullet-level requirement links. This expresses the intended workflow but is not proof that the claims are supported or that each stage was independently checked.
- Successful final samples retain numeric coverage: frontend 5/5, automation 5/5, OnPay 5/6 and 4/5 bullets. The target itself was not removed.

## Content defects with direct evidence

### 1. Sentence repair can fail even when the audit identifies the problem

Frontend initial and final bullet:

> Virtualized large lists with react-window to render 10,000-record datasets, reducing perceived render duration by 45% and lowering main-thread work through windowing and batching strategies memoization.

The ending is malformed. The source only supported react-window virtualization and measured render duration, not batching/memoization or a separate main-thread result. The audit proposed a repair, but the application withheld CHG-BULLET-02 with “Unsupported numeric claims: 10000.” The supplied source explicitly contains “10,000-record”; the numeric-grounding path did not consistently recognize the supported quantity in context. Withholding the repair left the defective original in the final output.

### 2. Metric meaning changes during drafting

Synthetic source: “reducing operator input errors by 20%.” Initial frontend output: “improving operator input accuracy by 20%.” These are not equivalent measurements. The final audit restored the error-reduction wording, showing useful correction, but retained unsupported “screen-reader labels” absent from the supplied source.

### 3. Numbers move between unrelated accomplishments

The synthetic source supplies 10,000 records for React list rendering. The automation draft used that as “processing 10k records nightly” for transaction reconciliation. It also added deterministic matching, optimized SQL joins, SRE users and exponential-backoff implementation details. The final audit removed those examples, but the generator should not have introduced them. Numeric token overlap alone cannot verify that a number belongs to the stated system, baseline, outcome or time period.

### 4. Strong JD similarity can hide unverified employment claims

The real OnPay role blueprints supplied no source_bullets, achievements, evidence or metric_evidence. Nevertheless, both generation and final audit retained:

> Built an enrichment pipeline processing about 45,000 monthly leads, increasing contact coverage by 28% through Python ETL jobs, external enrichment APIs, and scheduled SQL reconciliations.

> Created operational dashboards with React and SQL-backed metrics to surface funnel leakage, enabling RevOps to close priority gaps and improving pipeline visibility by about 35%.

The test inputs do not establish those exact claims. “About” does not label an invented number as awaiting confirmation. “Pipeline visibility” is also not a defined measure. The narrative evidence_limits only cautioned about platform names, while the bullets asserted responsibilities and measured results. A broad narrative disclaimer does not resolve specific unsupported claims.

This does not prove the candidate never did the work; it proves this test context cannot verify it. The draft should make that distinction explicit before content becomes a finished employment claim.

### 5. Duplicate accomplishments remain after audit

Final synthetic automation bullets 1 and 2 both describe automating transaction reconciliation for approximately 60 users and reducing manual processing by 45%. They consume two slots with essentially the same accomplishment. The second ends with repetitive wording: “across a recurring workflow used by operations teams.”

### 6. Historical titles and skills drift

The OnPay final audit changed the saved recent-role titles from “Applied AI Engineer / Full Stack Developer” and “Full Stack Developer” to “GTM Systems Engineer” and “GTM Automation Engineer.” The synthetic audit similarly changed “Full Stack Engineer” to target-role titles. Target positioning should not silently become a change to employment history.

The frontend skills draft initially returned “None” and “Not applicable” in an AI category. Those disappeared during synthesis, but the final automation skills still placed idempotent handlers and duplicate detection under Security & Auth, and scheduled jobs under Cloud & Infrastructure. Schema/category completion is not the same as useful skill organization.

## Why the current safeguards miss these problems

1. **Conflicting prompt instructions.** The actual OnPay experience developer prompt says not to invent missing measured outcomes, then later requests “realistic, rounded estimates ... because work-experience metrics are not stored in the profile” and “otherwise use conservative rounded estimates.” The latter instructions authorize the behavior the former forbids. Keeping 80% numerical coverage requires explicit handling for missing metrics, not contradictory prose. See app.py around lines 2529, 3044 and 3193.
2. **Requirement count is described ambiguously.** Common instructions say “each of the first four top_requirements.” The saved Rothera and BankPlus analyses have three. The schema permits any positive requirement number, and the semantic validator rejects the fourth only after generation. The retry did not correct it. The model should receive the exact valid IDs and the schema should constrain them.
3. **Narrow sentence checks are not a general review.** Current deterministic checks recognize a few earlier defects; they do not catch “batching strategies memoization,” repeated accomplishments, unsupported screen-reader work or vague “pipeline visibility.” Passing those checks does not establish readable or supported content.
4. **The audit still permits generated claims to validate later claims.** Labeling upstream content as draft_claim is helpful, but the grounding path includes upstream role content alongside actual profile evidence. The OnPay audit retained unsupported draft metrics and returned no manual findings. The evidence status needs enforcement, not just labels.
5. **Audit/title instructions still prioritize retitling toward the target.** The audit rationale explicitly treats the advertised title and draft focus as reasons to change employment titles. This conflicts with preserving historical titles in the newer writing rules.
6. **Repair handling is incomplete.** The frontend audit detected a bad bullet but a withheld patch left that bullet in the final result. A rejected repair must remain an unresolved issue and trigger a safe repair or manual review.
7. **Skills generation can exhaust its token budget.** The synthetic GTM case failed before bullet generation despite having relevant source evidence. That is an end-to-end reliability failure, not a judgment about JD fit.

## Required follow-up

- Preserve the JD → project characteristics → contributions → coherent narrative → XYZ sequence, while separating target characteristics, source facts and unconfirmed drafting assumptions.
- Keep the 80% numerical target, preserve source metric meaning and ownership, and flag missing metrics for confirmation rather than silently manufacturing measured results.
- Reconcile all prompt families and the final audit so they apply the same evidence/title rules.
- Use exact requirement IDs/counts and handle withheld repairs as unresolved defects.
- Add semantic review for distinct accomplishments, precise action/result causality, natural sentences and metric definitions.
- Repair skills output-budget/category handling, then rerun these saved cases and preserve before/after evidence.

## Artifacts

The baseline examples above describe the original run. An early rerun reused its raw-output paths; those JSON files now reflect the rerun rather than the original baseline. Later test outputs use versioned directories. See [the fixes and latest verification](resume-generation-fixes-2026-10-25.md) for current outputs and the run history.

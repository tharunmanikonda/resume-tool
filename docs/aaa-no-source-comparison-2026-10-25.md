# AAA test without source resume content

## What was removed

No saved experience bullets, achievement evidence, projects, skills or summary were supplied in either experiment. Only employer/title/location/date headings were retained. Request checks verified that no saved source bullet or project name entered the prompts. No production configuration or saved resume was changed.

Two fresh model calls were made. This is a local diagnostic comparison, not a verified resume or ATS benchmark.

## Experiment A: remove source content, retain current production instructions

Used the same saved AAA analysis, empty preliminary skills and source-free recent-employer metadata in the actual production experience function. The current instructions still demand source-backed historical accomplishments and source references.

The model produced generic API/versioning, AI-assisted tooling and reliability work. It called those contributions supported/transferable even though no accomplishment evidence was supplied, and returned employer keys as source references. Validation rejected all twelve bullets' invalid references. An automatic repair was not sent in this single-call diagnostic.

This establishes that deleting input bullets alone does not implement JD-only generation. The source-dependent prompt, output contract and validation remain incompatible with that mode. It also reveals that the model can fill the gap with unsupported qualitative assertions; omitting numbers does not establish factual support.

## Experiment B: explicit JD-only proposed narrative

Used only the raw AAA JD and employment headings, with a separate experimental prompt/schema. No cached analysis, preliminary skills or candidate project context was supplied. The prompt explicitly labelled every project and responsibility hypothetical, with generated measurements illustrative and unverified.

Requested sequence: JD → required project characteristics → draft contributions → project narrative → concise XYZ bullets. Required work and optional agentic experience were separated. Assumptions were retained outside the bullet text.

Generated stories:

| Heading | Proposed system |
| --- | --- |
| McKinsey | Cross-platform personalization/notifications platform with versioned APIs |
| Uber | Real-time booking/messaging subsystem with mobile clients and an admin console |
| KPMG | Enterprise customer portal/reporting application with Java services |
| Trigent | Customer-facing account-management web application |

These are model-selected examples, not facts inferred from those employers. The former LangChain referral project, trip-anomaly/Isolation Forest story and fixed source measurements were not supplied or reproduced. No instruction specifically banned LangChain.

The output highlighted version negotiation, backward-compatible client migrations, caching/query batching, rollout health gates, testing, AI-assisted development and frontend performance. These are materially different engineering contributions from the source-based test.

The draft is available in `docs/aaa-jd-only-experimental-draft-2026-10-25.md` with assumptions and an explicit unverified label.

## Remaining problems

- The 80% numerical target was not achieved. Current quantity recognition counts McKinsey 3/6, Uber 4/6, KPMG 2/5 and Trigent 2/3. Written quantities with additional modifiers may affect recognition, but the result plainly does not consistently meet the target.
- Some bullet metadata calls quantified content qualitative, including a three-week migration window. The experimental schema does not use or satisfy the production measurement-evidence contract.
- Some numbers merely describe version identifiers, such as v1/v2. Those are not quantitative impact or operating scale and should not count toward the target.
- The target description calls AI-assisted tooling optional/preferred in places, despite the posting explicitly requesting demonstrated experience. Agentic systems were correctly treated as a strong plus. Required/preferred classification still needs checking.
- Some proposed bullets are dense or spread across too many platforms/technologies. Scenario plausibility and concise engineering emphasis need review; there is no source history to establish these as real achievements.
- The two experiments change more than source availability: B deliberately changes instructions/schema and omits the cached analysis. It illustrates the intended new mode but is not a controlled attribution of every improvement solely to deleting sources.

## Conclusion

The saved source content materially constrained the repeated project stories. The JD-only experiment can generate different proposed systems and contributions. Production currently remains a source-based tailoring workflow, and simply removing source content is insufficient. Any JD-only mode must explicitly distinguish generated assumptions from confirmed candidate history and use a compatible measurement/review contract.

Private exact requests/responses and input manifest: `tmp/aaa-jd-test/no-source/`.

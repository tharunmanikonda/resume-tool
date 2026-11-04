# Domino’s generation: call-by-call trace

## Scope and method

Captured production-built requests for JD analysis, preliminary skills, recent experience, older experience, synthesis and final review. Replayed three isolated stages against fixed inputs: analysis using the raw JD, recent experience using the saved analysis/skills and supplied role sources, and review using the current assembled resume and candidate evidence. The experience function automatically retried once: **four API requests across three stages** in total.

The user explicitly approved sharing the Domino’s JD, saved profile/work history and resume for these diagnostic calls. No saved application, resume, profile, production database or production prompt was changed. The harness uses an isolated database and disables workers and cache reads/writes.

These are current-code diagnostic requests, not recovered historical API logs. Historical attribution below uses the saved original/reviewed versions. Do not assume a new replay reproduces the precise historical generation.

Private exact prompts, schemas, outputs and local checks are in `tmp/dominos-content-review/call-trace/`. The reproducible harness is `tmp/dominos-content-review/trace_calls.py`.

## Actual production sequence

JD → analysis → preliminary skills → two experience calls (recent and older, parallel) → synthesis → quality review → patch application → project/profile assembly → export.

Contribution planning, narrative and individual bullets are fields inside each experience call. They are not separate model calls. Skills precede experience. Synthesis cannot rewrite experience bullets. Projects are copied from the profile rather than selected through this sequence.

| Stage | Model in captured request | Inputs | Output and actual authority | Observed issue |
| --- | --- | --- | --- | --- |
| Analysis | gpt-4o-mini | Raw JD and classification instructions | Role family, route, requirements, system/workflow descriptions | Live replay selected `backend_application` again despite explicit native qualifications. No native/mobile route exists in the allowed route list. Native requirements are recognized as terms without defining the central system story. |
| Preliminary skills | gpt-5-mini | Candidate context, compact analysis, permitted category order | Skills only | Raw JD is not passed to this function. Its target-characteristics raw-JD field is empty. A misweighted analysis therefore reaches this stage without the complete original qualification section. This handoff is confirmed locally; this stage was not replayed live. |
| Recent experience | gpt-5-mini | Raw JD, target characteristics, recent-employer sources, preliminary skills and role structure | Contribution plans, narratives, bullets, provenance and requirement links | Native projects are not in this request. It must truthfully retain backend/AI employment. The problem is treating weak associations as requirement support and retaining unclear causal wording. Live replay again grouped disparate contributions into a broad AI platform narrative and retained dashboard-to-latency causality. |
| Older experience | gpt-5-mini | Same structure, older-employer sources | Same output contract | No native project context; requirement-link validation verifies structure, not semantic entailment. Saved older-role output follows the audit/frontend source stories. No live replay was performed for this stage. |
| Synthesis | gpt-5.6-luna | Candidate context including projects, all generated experience, preliminary skills, analysis and raw JD | Headline, summary, skills and historical titles only | Although it sees every bullet, its output schema cannot repair bullets or choose/reorder projects. Historical pre-review output omitted Swift and native projects from the summary; current synthesis was captured, not replayed. |
| Final review | gpt-5.6-luna | Raw JD, canonical resume, candidate evidence, preflight and available narrative context | Patches for title, summary, skills and experience | No project-selection/order patch exists. Live replay returned `approved`, score 84, no patches and no manual findings. It missed known causal weaknesses and described fallback/uptime evidence that exists in the profile but is absent from the current submitted bullets. |
| Assembly/application | Local code | Canonical reviewed content plus profile | Displayed resume and PDF snapshot | Projects are copied in profile order. Canonicalization keeps titles/bullets but drops planning/provenance fields from the active reviewed experience. Original planning remains recoverable in the saved original version. |

## Where each defect enters

### 1. Native qualifications become a backend story in analysis

The raw JD reaches the analysis call intact. Its schema allows several specialist routes but no mobile/native route. The prompt includes detailed instructions for other specialties, without an equivalent native-app prioritization rule. The live result again chose backend engineering, with a core problem of scalable software for the pizza/QSR industry. It retained Kotlin/Swift in top requirements but described the system generically.

The replay also returned candidate-like gaps such as “Limited experience with internationalized software development.” This call receives no candidate history, so it cannot establish that limitation. JD interpretation and candidate-fit assessment are mixed in the analysis output contract.

The missing route is a contributing constraint, not proof that adding a route alone will fix targeting. A mandatory platform/specialization and requirement-priority representation is needed regardless of route name.

### 2. Role sources contain some of the unclear claims

The saved sources already contain the 18% “API overhead” outcome, semantic caching without a named inference workload, and dashboards linked to reduced UI latency. Current writing instructions correctly preserve supplied measurements but do not reliably separate preservation of a fact from acceptance of the source sentence’s causal explanation.

The recent live output cited real source references for those bullets while preserving the same weaknesses. This is not principally a failure to send role evidence downstream. Provenance checks do not prove that the implementation/result relationship is adequately explained.

### 3. Narrative exists, but its semantic links can be wrong

All four employers in the saved **original revision 4** contain contribution plans, project narratives, bullet evidence and requirement evidence. The plan step was not skipped.

In that original version, Uber’s semantic caching and observability bullets were marked **direct** evidence for the continuous-integration requirement. Those activities do not themselves establish CI experience. The validator checks valid requirement numbers, bullet indexes and source references; it does not establish that the cited bullet entails the requirement.

The live recent-role replay also mapped production streaming/fallback work as transferable evidence for CI/CD. That may show operations/reliability, but does not establish build/test/integration workflow experience. The same semantic mapping weakness reproduced.

### 4. The numeric checker actively creates unnecessary repair work

Exact local results:

| Text | Tokens accepted as metrics |
| --- | --- |
| `over 50,000 telemetry metrics` | none |
| `50,000+ telemetry metrics` | `50000+` |
| `50,000 monthly audit transactions` | none |
| `ten enterprise audit applications` | none |
| `more than fifteen UI regressions` | none |
| `five device types` | none |

The checker has a restricted immediate-unit list and does not parse written numbers. It also compares number tokens literally rather than reconciling the source’s quantity representation with an equivalent draft representation.

Live sequence:

1. The source says “over 50,000 telemetry metrics.”
2. The first generated Uber bullet says “50,000+ telemetry metrics.”
3. Validation returns: `unsupported metrics 50000+; use [Confirm metric: specific measure] without invented numbers.`
4. The automatic repair removes that count but asks the user to confirm the telemetry count anyway.
5. Local preparation inserts a confirmation marker from the model’s metadata.
6. Final validation rejects the result as an unverified proposal/confirmation request in resume content.

Thus a supported source quantity is treated as invented, causing a repair that blocks delivery while leaving the original dashboard/latency causal weakness intact. The failure occurred in the diagnostic output only; it did not overwrite the saved Domino’s resume.

The saved numerical counts—McKinsey 4, Uber 3, KPMG 2, Trigent 0—match a fresh local calculation exactly. The earlier claim that these counts necessarily came from an old review was incorrect. The parser explains them. Recognizing quantities is also distinct from judging whether they are useful outcome evidence.

### 5. Synthesis is a packaging stage, not a story repair stage

Its schema allows only title, summary, skills and experience titles. It sees all generated bullets but cannot replace them. A strong-sounding summary therefore does not imply weak experience bullets have been repaired. A relevant native project can be visible in its input without the output having any way to move it earlier in the final document.

### 6. Final review does not consistently distinguish evidence available from evidence visible

The new live audit approved the current resume with no patches. Its requirement reasons cite inference fallback, rate-control and service uptime. Those are supplied source accomplishments, but they are absent from the current Uber bullets. Searching the complete profile is useful for proposing an addition; it should not establish that the submitted document already demonstrates that accomplishment.

The preflight reported zero bullet-quality findings for the current resume despite the causal weaknesses identified during local review. The final model call therefore received no specific deterministic signal for these defects, and its general review instructions did not reliably catch them.

Project bullets appear as profile evidence, but the editable `resume_under_review` contains only title, summary, skills and experience. Project order and project bullet repetition are outside the patch contract.

### 7. Canonicalization removes active trace metadata after review

The original saved experience entries have all planning fields. The reviewed entries have only title and bullets. `_canonical_editable_resume` deliberately constructs that reduced representation; patch application subsequently saves it as active experience. This explains why inspecting only the latest entries made the narrative look absent.

It is a traceability and future-review limitation, not evidence that initial generation lacked a narrative. Preserve immutable planning/provenance separately, and update bullet links when patches change bullets rather than blindly carrying stale links forward.

## Historical attribution and corrections

- Original version: revision 4. Reviewed version: revision 5. Audit base: revision 4. This is the normal patch-application transition, not evidence of stale review by itself.
- McKinsey, Uber and Trigent bullets are identical before and after the historical review. The causal and relevance weaknesses in those final bullets were present before review and survived it.
- KPMG bullet 5 was changed to restore the source-supported 200-developer-hour maintenance measure. Title, summary and skills also received patches.
- The original contribution plans are available in `resume_versions.original`, contrary to the earlier inference based solely on active entries.
- Historical preliminary-skills and synthesis API responses were not recovered as separate raw calls. Current prompt capture establishes what current code sends, not exactly what an older deployed prompt sent.

## Fixes supported by this evidence

1. **Analysis:** Represent mandatory platform/specialist qualifications explicitly, preserve their source wording/section and rank the system story accordingly. Keep JD-only output free of invented candidate gaps. Verify native-app coverage before accepting this analysis.
2. **Planning:** Keep real employer facts unchanged while selecting their relevant transferable contributions. Build a separate candidate-wide project selection/order plan from native project evidence. Do not require unrelated employment to become a mobile story.
3. **Numbers:** Normalize supported quantity expressions and qualifiers consistently for provenance comparison; recognize written quantities and intervening modifiers. Keep outcome quality separate from quantity recognition. Replace the repair instruction that encourages confirmation text in resume content.
4. **Requirement links:** Require exact visible bullet excerpts and a capability explanation for each coverage claim. Reject or downgrade links where caching/monitoring is presented as CI, or a time threshold is inferred from general programming work.
5. **Bullet review:** Evaluate causal mechanism, defined measurement and whether source wording itself is ambiguous. Preserve supported facts without reproducing overclaimed causality. Missing implementation detail belongs in source-quality notes, not an invented explanation.
6. **Synthesis and projects:** Either let a validated editing stage repair bullet text and project order, or make those explicit operations before synthesis. A summary-only response cannot fix an experience narrative.
7. **Final review:** Distinguish `available_in_profile` from `visible_in_final_resume`. A requirement is already covered only when linked to exact final content. Include the actual project section and order in the reviewed document/patch contract.
8. **Traceability:** Retain stage input/output identifiers, prompt versions and source links separately from export text. Check the assembled final artifact after applying patches; revision transitions alone are not stale-review evidence.

This is one job and one replay per isolated stage, with one automatic experience retry. It demonstrates concrete reproducible failures, not their population frequency or an employer’s ATS/hiring outcome. Structured output shape does not establish semantic correctness; OpenAI’s documentation likewise notes that structured outputs can still contain mistakes: https://developers.openai.com/api/docs/guides/structured-outputs.

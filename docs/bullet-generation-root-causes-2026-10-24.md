# Why the generator produces repetitive AI stories and weak bullets

## Finding

The current staged generation path combines a fixed role story, JD-derived skills, sparse candidate history, and a mandatory sentence template. That is a concrete design explanation for the pattern in the reviewed resumes. It is not proof that the current code version produced every historical file or that these issues caused any specific rejection.

All nine reviewed resumes begin the current-role experience with AI delivery, AI features, or AI ingestion. This is the precise finding; saying most of all 180 bullets are AI claims would overstate it. The repetition is concentrated in the first role and first impression.

## 1. The first role has a fixed AI story regardless of the target job

[EXPERIENCE_BLUEPRINTS](/Users/tharun/resume-tool/app.py:211) assigns the first stable role key this anchor:

> enterprise delivery, applied AI workflows, ingestion and retrieval systems, customer-facing software

The other roles also have fixed anchors: operational tooling/transaction validation, audit/compliance/Java/document processing, and frontend migration/QA.

[current_experience_blueprints](/Users/tharun/resume-tool/app.py:9888) and [experience_blueprints_from_snapshot](/Users/tharun/resume-tool/app.py:10537) merge employer, location, dates and title into these defaults while keeping the anchors. They do not select between multiple documented projects based on the JD. In the inspected OnPay snapshot, each history entry contains only key, company, location, title, dates and enabled status.

The experience prompt then says to keep each company as one coherent project story. With only this broad AI story to draw on for the first role, AI becomes the recurring opening even for frontend, ERP and GTM applications. Role-family instructions can change emphasis, but do not provide a different factual project to choose.

## 2. The generation step lacks detailed source accomplishments

[generate_experience_subset_from_analysis](/Users/tharun/resume-tool/app.py:9439) supplies the model with:

- Role metadata and the fixed anchors.
- Preliminary generated skills.
- A compact JD analysis.
- Optional revision context when passed by a caller.

The normal extension call does not pass detailed prior work bullets or a verified project/accomplishment inventory. The existence of `config/base_resume.json` elsewhere in the app does not mean its experience bullets reach this model call.

The code itself documents that role profiles currently store metadata, not work bullets or verified achievement metrics. Consequently, the model must fill in implementation details from a broad story and the desired target stack. “Do not invent expertise” is present in the prompt, but the factual input needed to support specific accomplishments is largely absent in this path.

## 3. Skills are generated before experience and influence its factual content

[generate_skills_from_analysis](/Users/tharun/resume-tool/app.py:5789) receives JD analysis and category order, rather than the candidate's detailed work history. The [experience subset prompt](/Users/tharun/resume-tool/app.py:3076) then directs the writer to use preliminary skills to guide the stack.

This yields a risky dependency:

JD requirements → generated skills → experience using those skills → summary grounded in that experience.

The missing step is selecting candidate-supported work before generating claims. For example, a HubSpot skill in the preliminary list is not evidence of an actual HubSpot implementation. A correct GTM classification does not solve this: OnPay is stored as gtm_engineering, yet its opening remains AI retrieval.

## 4. The prompt prescribes the repetitive sentence shape

[The bullet formula](/Users/tharun/resume-tool/app.py:3178) explicitly asks for:

> [Strong Verb] + [System or workflow] + using [1-3 tools] + under [constraint or engineering decision] + resulting in [grounded measurable impact or a concrete qualitative outcome].

It also requires each bullet to contain tools and a constraint/decision, imposes a 25–30-word range, and requires a 25–40-word first summary bullet. These instructions compete with more general requests for simple wording and varied sentence structures.

This explains why “under tight timelines” and similar phrases survive: the model is filling an explicit slot, even when the constraint does not explain a decision. The observed count is 149 of 180 reviewed bullets containing “under.” This is a descriptive count, not an AI-authorship test.

The user's 80% numerical-evidence target is intentional and can remain. Its implementation needs to distinguish a meaningful measured accomplishment from the mere presence of a metric-shaped expression. XYZ does not inherently require this rigid sentence order or a constraint clause in every bullet.

## 5. Early validators enforce structure more strongly than meaning

[validate_experience_subset_payload](/Users/tharun/resume-tool/app.py:5304) checks title presence, metadata echo, and bullet count. Its analysis-aware wrapper adds JD tool checks for analyst/GTM families, returning early for other families. These checks do not independently establish:

- What the workflow processes, and which systems are connected.
- Whether the action can cause the stated result.
- Whether the metric measures the stated accomplishment.
- Whether the bullet demonstrates a core requirement rather than mentioning related tools.
- Whether the opening project is relevant to the job.

[validate_experience_numeric_coverage](/Users/tharun/resume-tool/app.py:4955) counts metric-like expressions. Its token helper uses units and surrounding language, so it is more than a search for arbitrary digits. Nevertheless, it does not determine whether “demo readiness” is well defined or a claimed result follows from the action. The generator retries on tool/coverage failures; it does not apply a comparable deterministic requirement-evidence or action-result check at that step.

## 6. Later review has an evidence-authority weakness

[Final synthesis](/Users/tharun/resume-tool/app.py:3373) receives complete generated experience and the raw JD, but explicitly cannot rewrite bullets. It can improve the title, summary, skills and work titles while leaving the weak opening story intact.

A separate quality audit does exist and can rewrite bullets; it would be incorrect to say there is no semantic review. However, [_quality_audit_evidence_manifest](/Users/tharun/resume-tool/app.py:7592) labels the current generated experience bullets and skills as **upstream_validated**. The preceding structural checks are not factual validation of those claims. This lets downstream review cite generated narrative as evidence for additional or revised claims.

The manifest supports fields such as source_bullets and achievements when supplied in blueprints, but the inspected normal blueprint builders do not copy those fields from saved role history. Profile projects/certifications supply some independent evidence; they do not independently validate employer-specific claims.

Historical caveat: several examined drafts have manual/kept_current active states and others have applied audit proposals. This review does not attribute every observed sentence to the automatic audit or assert the exact origin of manual edits.

## Direction for the fix

The intended flow should be:

Candidate-supported accomplishments + JD requirements → choose relevant evidence → write bullets → check factual support, action/result connection and requirement coverage → synthesize summary/skills → independently review.

That means:

1. Store actual project/workflow accomplishments per employer, including real tools, personal contributions, outcomes and metric basis.
2. Select the most relevant supported accomplishments before writing, instead of assigning every application the same first-role project story.
3. Keep AI when it accurately describes the work. For a frontend job, select the supported UI contribution within that project; do not disguise an AI project as unrelated CRM or ERP work.
4. Preserve the intentional XYZ/80% policy while allowing natural sentence structures and rejecting undefined or causally disconnected outcomes.
5. Derive final skills from selected candidate evidence and relevant JD requirements; a JD-derived preliminary skill must not independently authorize a historical claim.
6. Keep generated drafts separate from independent evidence in the audit. Require source links for factual claims rather than allowing the draft to validate itself.
7. Re-evaluate openings and top-requirement coverage in the bullet review, with a repair path that can change the selected evidence and ordering.

No generator behavior was changed during this investigation. Findings are from code inspection and comparison with saved outputs; no paid model calls were needed.

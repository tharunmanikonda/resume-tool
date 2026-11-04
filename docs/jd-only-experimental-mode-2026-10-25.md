# Experimental JD-only drafting mode

## Availability

Enable **Settings → Experimental JD-only drafts** in the main app. An **Explore JD-only draft** panel then appears in the app and extension. It is opt-in and off by default. Reload the extension panel after changing the setting; an updated extension build also requires reloading the installed unpacked extension.

The panel generates a separate proposed draft and offers a labelled Markdown download. It does not replace a saved resume, call the factual resume/PDF approval flow or submit an application. Existing source-based generation remains available.

## Implemented workflow

1. Server selects only employment headings: role key, employer, location, dates, historical title and structural bullet counts. Saved bullets, evidence, anchors, projects, skills and summary are excluded from requests.
2. A separate planning call reads the raw JD and distinguishes required capabilities from preferred/bonus ones, with exact supporting quotations. It proposes role-specific systems, workflow, scope, assumptions and distinct contributions.
3. The plan is checked before writing. Missing/invalid quotes, bonus requirements ranked required, missing role scope/assumptions and duplicate contributions receive one targeted revision. An invalid plan is not used downstream.
4. A drafting call receives the checked plan, JD and headings. It writes concise XYZ bullets with explicit illustrative/qualitative measurement records. It does not claim nonexistent source citations.
5. Validation checks structure, contribution ordering, finished prose, measurement/body consistency and numerical coverage. It distinguishes API version identifiers from operating counts. A numeric shortfall is advisory rather than permission to add filler or block the whole draft.
6. A separate assembled-draft review checks JD priority, cross-role repetition, role scope, plan drift and misleading attribution. It is instructed not to demand a complete architecture, missing baselines or every causal step in a concise bullet. Findings are shown as **changes suggested**, rather than treated as factual approval.

The 80% numerical target remains. All generated measurements in this mode are illustrative and unverified. One-component/module/strategy padding is treated as qualitative work. Source-based provenance checking is not replaced or bypassed for factual resumes.

## Implementation

- `jd_draft_experiment.py`: independent prompts, schemas, heading allowlist, plan/draft checks, conservative normalization and proposed-draft rendering.
- `app.py`: feature flag, ephemeral checked-plan sessions, `/api/ai/jd-draft/plan` and `/api/ai/jd-draft/generate`, bounded repairs and separate assembled review.
- `src/JdDraftExperiment.jsx`: shared app/extension panel, assumptions, review findings, labelled download and clearing stale results when the JD changes.
- `src/App.jsx` and `extension/src/panel-main.jsx`: opt-in entry points.

## AAA live verification

The raw AAA JD and employment headings were used without source-resume content. The live plan correctly kept AI-assisted coding/debugging/review required and agentic systems optional, positioning the role as broader software/application engineering.

Development runs exposed approximate-value metadata mismatches, missed noun-modified counts, trivial one-artifact padding, measurements placed only in metadata, and one response that exhausted its output allowance. Their prompts/responses remain in versioned local test directories. These failures were not treated as successful generations.

The final HTTP-handler verification reused the live-generated plan and draft through the corrected validators and ran the assembled review live. Both endpoints returned HTTP 200. This is not a claim that the final code received a wholly fresh plan/draft/review in a single uninterrupted run after the last checker changes. There were 11 actual API requests across the development iterations, including one incomplete response and the final review.

The resulting draft is `docs/aaa-experimental-mode-draft-2026-10-25.md`. The reviewer identified overlapping API/reliability accomplishments between roles and drift from some planned contributions. KPMG and Trigent remain below the 80% numerical target; these are displayed as advisory notes. The draft is therefore an experiment with changes suggested, not a verified or submission-ready resume. The new workflow has not replaced the default flow.

Private exact requests/responses and final HTTP results are under `tmp/aaa-jd-test/experimental-mode*`.

## Checks

- 462 Python tests passed, including source-free request isolation, feature-flag persistence, required/optional grounding, stale plans, measurement consistency and preservation of the existing pipeline.
- App and extension builds passed.
- Browser test passed for sequential plan/generation requests, employment labels, assumption display, labelled download and stale-result clearing.
- Existing app/extension review smoke tests and profile-evidence round-trip checks passed.

The browser test uses mocked responses; the backend HTTP test exercises real model responses separately. This is not an ATS/hiring benchmark or a guarantee of consistently strong generated stories.

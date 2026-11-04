# Resume context handoff fix — October 25, 2026

The pasted output was generated from incomplete candidate context. Both interfaces displayed the shared backend output: a summary discussing missing evidence, an empty skills section, and hypothetical hardware work with confirmation placeholders.

## Causes

- Converting a resume into a profile retained employment metadata but dropped the existing work bullets, summary, technical skills and education.
- Both work-history normalizers in the React app dropped role evidence when the user edited or saved a profile or inline work history.
- Extension snapshots could contain only role metadata even when the profile had detailed accomplishments.
- Early summary generation received JD analysis without the candidate profile; final synthesis lacked the complete candidate context.
- The previous confirmation policy allowed internal questions and proposed work to appear in copyable resume text.
- Regeneration could continue using an old source-poor snapshot instead of updated profile evidence.

## Changes

A shared context builder now supplies the same source material to both pipelines. It backfills accomplishments only when the company, historical title and dates match the configured resume. Explicit profile sources, including an explicitly empty override, take precedence. A differently named candidate's resume is excluded. The active local context now supplies 23 existing work bullets, five technical skill groups and two education entries.

Resume imports, profile normalization, profile editing, main-app sessions, extension snapshots, summary generation, skills generation and final synthesis preserve this context. Profile now exposes a Work accomplishments field for each role. Explicit regeneration refreshes source evidence for matching roles while retaining inline employment edits.

Instructions now require actual supported work rather than hypothetical employer projects. Missing JD expertise stays in review notes. The 80% numerical target is retained; an actual measurement shortage becomes a separate review finding rather than a placeholder in the resume. A narrow source check also rejects the pasted example's unsupported DAQ, CAN and powertrain/control claims when they are absent from cited work sources.

The backend rejects summaries containing internal review commentary, confirmation/proposal bullets and empty completed skills sections before delivering them as successful resume content. Empty skills and defective summaries receive a repair attempt. Main-app bundles now require cache revalidation after a build.

## Verification

- 414 Python tests passed, including candidate-context round trips, main-app endpoint handoff, extension snapshot handoff, source isolation, profile overrides, regeneration, review/body separation and the supplied hardware example.
- The profile and inline editor normalizers passed a JavaScript round-trip test preserving accomplishment arrays and metric evidence without shared mutable references.
- Both app and extension production builds passed.
- A live rerun of the previously approved OnPay case completed generation, synthesis and review. Its final output has a professional summary, five populated skill groups and no confirmation placeholders. Its numerical shortfall is reported separately in review notes.

The OnPay rerun is a live pipeline check, not a live rerun of the pasted Customer Integration Engineer JD. No applications or emails were sent, and existing saved application records were not rewritten.

[Live output preview](../tmp/rejection-analysis/live-context-handoff/onpay/resume-preview.txt)

## Loading the fix

The running local server was identified as a Python process on port 5001, running without automatic code reload. Restart that server, refresh the app/extension, and explicitly regenerate the affected draft to replace old cached generated content. Existing saved output is not silently rewritten.

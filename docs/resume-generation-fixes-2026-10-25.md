# Resume generation fixes and live verification — October 25, 2026

## Outcome

The intended workflow remains JD → required project characteristics → draft work contributions → coherent project narrative → individual XYZ bullets. XYZ and the 80% numerical target remain. The tool now distinguishes supported accomplishments from proposed work and missing measurements instead of silently presenting estimates as measured results.

All six latest cases completed generation, synthesis and final review. The three evidence-backed synthetic controls produced locally applicable corrections. The three real application snapshots require confirmation because they lack detailed role sources and measurements. Reaching review is not the same as having a finished resume.

## Changes

- Reconciled metric instructions across full, legacy, subset, repair, synthesis and audit prompts: use supplied measurements with their original meaning and accomplishment; missing measurements become explicit confirmation slots.
- Added contribution plans before narrative/bullets in the output contract, and a source/confirmation map for every bullet. JD characteristics and preliminary skills cannot serve as role evidence.
- Added deterministic rendering of confirmation labels from metadata. The model cannot hide uncertainty only in internal notes. Proposed work cannot establish direct requirement coverage.
- Retained the 80% numerical target: unfilled measurement slots reserve places in a draft but are explicitly not verified numerical evidence. Pending claims block final approval and PDF creation in both interfaces.
- Constrained requirement links to the actual supplied requirement count, fixing the three-versus-four failure.
- Constrained historical role titles to their supplied values in generation/synthesis and rejected audit patches that rename employment history toward the target role. The top headline remains positioning.
- Repairs now receive the exact previous draft alongside the errors. Added source references down to individual accomplishments and safely resolved unambiguous relative audit references.
- Corrected recognition of quantities such as 10,000-record, which previously blocked a legitimate sentence repair. Added checks for observed broken grammar, vague pipeline-visibility percentages, and substantially repeated bullets.
- A withheld bullet replacement now requires manual review rather than quietly becoming approved. Optional unsupported additions remain separately distinguishable.
- Removed the six-category minimum and filler skills such as None/Not applicable. Increased skills output allowance from 2900/4800 tokens to 4800/7300 across the initial attempt/retry.
- Replaced the mandatory opening summary with a distinct accomplishment. Widened the rigid 25–30-word range to 18–35 so source-grounded sentences need less padding. Added explicit review instructions against tautological tails and category padding.

## Latest live results

| Case | Completed through review | Final review decision | Interpretation |
|---|---|---|---|
| OnPay | True | manual_attention | Project details and measurements require confirmation; draft is not ready for export. |
| Rothera | True | manual_attention | Project details and measurements require confirmation; draft is not ready for export. |
| BankPlus | True | manual_attention | Project details and measurements require confirmation; draft is not ready for export. |
| Frontend control | True | changes_suggested | Review corrections were applied locally for inspection; no withheld patches in the latest control review. |
| GTM control | True | changes_suggested | Review corrections were applied locally for inspection; no withheld patches in the latest control review. |
| Automation control | True | changes_suggested | Review corrections were applied locally for inspection; no withheld patches in the latest control review. |

The real cases use the original saved context and two recent roles each, without adding new work-history facts. Controls use one synthetic role with ten supplied accomplishments. Generation used gpt-5-mini; synthesis and review used configured gpt-5.6-luna. No applications, saved resumes, or email were changed.

## Actual final examples from evidence-backed controls

### Frontend control

Historical title retained: Full Stack Engineer.

- Built React and TypeScript admin tables with filters, pagination, and forms for 200 transaction-review operators, reducing review time by 25%.
- Virtualized 10,000-record React lists with react-window to improve large-list rendering, reducing measured render duration by 45% in transaction-review workflows.
- Added Jest and React Testing Library regression tests to GitHub Actions CI, reducing escaped UI defects by 30% across administration workflows.
- Fixed keyboard focus and validation messages in React forms, reducing operator input errors by 20% across transaction-review workflows.
- Automated daily transaction reconciliation using Python and PostgreSQL, reducing manual processing time by 45% for 60 operations users.

### GTM control

Historical title retained: Full Stack Engineer.

- Connected HubSpot inbound contacts to lead-assignment rules with Python and REST webhooks, reducing median assignment time from 20 to 5 minutes.
- Implemented HubSpot custom objects and lifecycle associations for sales and customer-success handoffs, reducing manual handoff work by 40%.
- Added duplicate-contact checks and idempotent webhook handlers with Python and PostgreSQL, reducing duplicate records in CRM by 35%.
- Built SQL monitoring and retry handling for failed CRM webhooks, reducing the number of unprocessed events by 80%.

### Automation control

Historical title retained: Full Stack Engineer.

- Automated daily transaction reconciliation using Python and PostgreSQL, reducing manual processing time by 45% for 60 operations users.
- Connected HubSpot inbound contacts to lead-assignment rules with Python and REST webhooks, adding idempotent handlers that reduced median assignment time from 20 to 5 minutes and duplicate CRM records by 35%.
- Built SQL monitoring and retry handling for failed CRM webhooks, reducing unprocessed events by 80% across inbound CRM integrations.
- Added pytest validation for reconciliation workflows and exception logs during daily automated processing, reducing invalid transaction records by 22%.
- Improved React admin tables and form validation used by transaction-review operators, reducing review time by 25% and operator input errors by 20% to speed triage.

## Verification and limits

- Automated suite: 400 tests passing, including source association, actual requirement counts, confirmation rendering, historical-title schemas, pending-claim review/PDF gates, numeric quantity parsing, withheld repair handling, and common-word/platform disambiguation.
- Live tests exercise the actual generation, synthesis and review functions. Five cases use version 4; OnPay uses version 5 after fixing the false positive for ordinary “outreach sequencing.” The controls were reviewed again after widening the word range; their previous final results were archived beside them.
- Earlier reruns exposed source-reference formatting failures and confirmation labels being omitted from bullet text. Those failed attempts are retained in versioned folders.
- A test-harness path mistake reused the original raw-output folder during the first rerun. The original baseline examples and findings remain in the baseline report; the original raw JSON paths no longer represent that first baseline. Later outputs use explicit versioned directories.
- This is a small diagnostic sample, not an ATS benchmark or hiring-outcome test. Source references and numeric checks cannot prove every semantic claim; the final model review and candidate confirmation remain necessary.
- Source-poor application snapshots now yield proposed contributions rather than fabricated finished experience. They need actual project details and measurements before the confirmation markers can be resolved.
- Planning happens within the structured generation call, in the requested order. It is not five independent model passes.

## Local artifacts

- [OnPay: generated content, audit and final result](/Users/tharun/resume-tool/tmp/rejection-analysis/live-2026-10-25-v5/onpay/result.json)
- [Rothera: generated content, audit and final result](/Users/tharun/resume-tool/tmp/rejection-analysis/live-2026-10-25-v4/rothera/result.json)
- [BankPlus: generated content, audit and final result](/Users/tharun/resume-tool/tmp/rejection-analysis/live-2026-10-25-v4/bankplus/result.json)
- [Frontend control: generated content, audit and final result](/Users/tharun/resume-tool/tmp/rejection-analysis/synthetic-live-2026-10-25-v4/frontend/result.json)
- [GTM control: generated content, audit and final result](/Users/tharun/resume-tool/tmp/rejection-analysis/synthetic-live-2026-10-25-v4/gtm/result.json)
- [Automation control: generated content, audit and final result](/Users/tharun/resume-tool/tmp/rejection-analysis/synthetic-live-2026-10-25-v4/automation/result.json)

The adjacent calls.json files contain private prompts/responses with API credentials omitted. Keep these test artifacts local.

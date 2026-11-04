# Continuous review and apply

The JD-only generation flow now follows the user-requested architecture:

Planning -> grouped core -> experience -> reviewer returns exact replacements -> deterministic local apply and validation -> save.

The reviewer returns a summary, findings with exact target IDs and one-based replacement indices, and a partial changes array. Each ordinary writing defect must include its exact replacements. The response schema requires at least one replacement reference for a repair finding; advisory and factual-blocker notes carry no replacement references. Local contract checks ensure every repair is linked, targets match and unchanged text is not rewritten accidentally. A prose-only suggestion is not treated as a completed correction.

There is no separate post-review repair model, verification model or iterative fresh-critique loop. The code applies the reviewer-authored replacements directly and validates the resulting draft. Initial drafting can still use its existing bounded formatting repair if the generated draft fails local checks before review. This is a separate failure path.

Target IDs identify headline, summary, skill groups and one-based role bullets. Existing exact-old-text checks and atomic application remain. Reviewers preserve useful numerical evidence and concise technical meaning. Optional suggestions are notes rather than PDF blockers. Genuine unresolved factual conflicts and invalid/stale output remain explicit failures instead of being silently accepted.

For the extension, the existing retry action now reviews AND applies exact replacements to the current saved draft. It preserves the original version, updates the reviewed version/revision and PDF staleness, and saves content plus review outcome atomically. Edits made while the call runs invalidate the result. The action is labelled “Review and apply” for an already-generated JD-only draft. New generation proceeds through this automatically, without needing that button.

Validation: 524 Python tests passed; extension build and review UI smoke check passed. Tests assert the normal call sequence is plan/core/experience/review, with no extra repair or verify call for reviewer changes. They also cover original/reviewed versions, exact replacement targeting, missing-change contract errors, advisory versus factual dispositions, automatic saving of existing-draft corrections and preservation of concurrent user edits.

No live API request was performed for this correction, and the saved New Balance resume was not rewritten or approved. Actual model compliance and end-to-end live behavior remain to be verified.

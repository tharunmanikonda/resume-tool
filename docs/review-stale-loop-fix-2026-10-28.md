# Repeated stale-review fix — October 28, 2026

Inspected Fonzi AI draft `draft-be7f274838df4ee7a7209bd1cbee0f42`, editor save logic, and saved review trace `4496c5f29d834f368c124e36d377b1c6`.

Problems:
- Opening an editor could overwrite the draft-specific history/contact with the asynchronously loaded global profile and trigger an automatic PATCH.
- Re-sending unchanged resume mode or identity refreshed profile/contact snapshots. Re-sending unchanged content unnecessarily reparsed and rebuilt canonical payloads. These incidental changes could increase the revision while review ran.
- Retry Review did not cancel pending autosaves or wait for an in-flight save. Its derived history and autosave fingerprint could differ.
- The latest completed review emitted three exact replacements but linked only two. A third skills replacement corresponded uniquely to an advisory finding with empty change_indices; local linking validation rejected it.

Fixes:
- Keep hydrated draft history/contact when the global profile fetch resolves later.
- Cancel pending autosave at review preflight, wait for in-flight saving, and align saved/edited history. Recheck fingerprints when the autosave timer fires. Genuine new edits after preflight remain saveable and still invalidate a running review.
- Same-mode/same-identity saves keep existing snapshots. Identical content without changed content context does not reparse or rebuild snapshots.
- Recover an unlinked emitted review change only when it has one unique exact finding target and that finding is advisory/repair. Mark that finding as repair and link its emitted change. Do not invent changes, fuzzy-match targets, override factual blockers, or resolve ambiguous ownership. Exact replacement and complete disposition validation remain enforced.

Verification: 608 Python tests pass; both Vite builds and the existing main review UI smoke test pass. New regressions verify an unchanged full editor save during review retains revision/run state and can finish approved; exact unlinked advisory patches recover while ambiguous or blocker-linked patches do not.

Recovery: compared the complete current editable resume and JD with the saved paid review inputs. They matched exactly. Reused that completed response locally through the normal validation/application flow. Review approved at revision 9, preserving original/manual versions. No new OpenAI requests were made. Pre-recovery draft saved under tmp/fonzi-before-review-recovery.json.

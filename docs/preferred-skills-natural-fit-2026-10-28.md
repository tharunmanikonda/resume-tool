# Preferred skills and natural project fit — October 28, 2026

This update supersedes the local priority correction/gating behavior described in generation-failure-fixes-2026-10-28.md.

User direction: consider technical skills described as preferred, a plus, bonus, nice-to-have, familiarity, exposure, desirable or similar language. Include them through concrete work when they naturally fit the chosen project. Do not force them into an unrelated story, invent a responsibility to accommodate them, or treat their inclusion as a coverage quota.

Changes:
- Removed `requirement_priority` and `reconcile_plan_priorities`, including their app/extension/experimental route calls.
- Removed required/optional ranking and mixed-priority errors from local plan validation. The arrays remain posting context, not a project inclusion gate.
- Kept structural checks, actual JD citation checks, selected-role/count checks and exact, atomic replacement application.
- Updated planner, AI targeting, writer and reviewer instructions consistently. The AI targeting step can return an exact contribution correction to include a naturally fitting technology, or remove a forced use. The code applies that correction before writing.
- No new AI calls or automatic paid retries were added.

Verification: 604 local tests pass. Real saved failed plans no longer block on classification labels. Two workflow simulations verify that a Snowflake contribution reaches writing when it fits reporting work, and that its omission does not trigger repair calls for an unrelated service. These use mocked model decisions; no fresh live model request was made.

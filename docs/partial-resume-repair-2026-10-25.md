# Partial resume repairs

The shared app/extension JD-only generator now requests a `changes` array during draft-validation and writing-review repair. Initial writing still produces a complete draft; project planning and review logic remain unchanged in this step. The older experimental diagnostic endpoint is not part of this integration.

- Headline: exact current title plus replacement title.
- Summary: exact unique passage plus replacement passage; multiple non-overlapping edits are allowed.
- Bullet: role key, one-based bullet number, exact current text and one replacement bullet with consistent measurement metadata.
- Skills: one-based group number, expected category and replacement group. Other groups remain intact.
- Empty array: no changes.

The merge works on a copy and rejects stale, missing, duplicate or overlapping targets. A malformed patch cannot partially alter the saved draft. Existing content validation checks the assembled result. The existing second writing review remains after review-driven repair; this change reduces repair output rather than removing review.

The repair response schema contains no full-resume fields. The model still receives the current draft and project context so it can make coherent corrections, but returns only replacements. Timing improvement is not yet measured with a live request. No live generation was run for this change.

Validation: 509 tests passed. Coverage includes title and summary-passage replacements, numbered bullet repairs, preservation of untouched skill groups, atomic rejection of stale/invalid patches, the validation-repair call sequence, and keeping original content when a review repair fails.

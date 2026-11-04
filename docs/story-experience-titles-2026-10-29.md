# Story-aligned proposed experience titles — October 29, 2026

Root cause: JD-only plan entries had no title field. Final canonical assembly unconditionally used blueprint `default_title`, so Salesforce/Apex/LWC projects still displayed Full Stack Developer. Review inputs also omitted experience titles and could not address them through tids.

Changes:
- Each planned role now returns a short conventional functional title appropriate to its own proposed system, work, responsibility and timeline.
- Supplied profile titles inform scope rather than locking draft labels. Employers/dates stay unchanged; proposed functional titles are not asserted to be verified official titles. Do not manufacture promotions or add Senior/Lead to force growth, or assign the target specialization to every earlier role.
- The AI targeting call can correct a role's title if it changes or clarifies that role's project direction.
- Code carries the plan's title into the internal writing draft and canonical result. It does not ask the experience writer to regenerate the same title. Older checkpoints without this field receive a safe profile fallback rather than another validation failure.
- Review receives the experience titles. tid 1 remains the main headline; further tids identify role titles with explicit role_key/scope labels. These are separate from bid numbering. Exact, atomic title patches can update a role without touching its headline, bullets or another employer.
- Reviewed titles flow through editor versions, extension persistence and formatted/export-parsed content. Saved profile titles are not overwritten. Explicit user edits in an existing draft remain its current titles until intentionally reviewed or regenerated.

Verification: 652 local tests pass. Added coverage for a Salesforce recent role with distinct older software/Java/frontend roles across all four modes; plan-to-writing-to-review-to-output propagation; export parser title preservation; role-title correction through tid; targeting title correction; single selected late-career role; extension versions and save/reopen behavior; unchanged profile history. No paid generation or new external API test was run. Existing saved resumes were not rewritten.

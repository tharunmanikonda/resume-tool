# Grouped writing with shared planning

The shared app and extension generator now follows the earlier core/experience handoff pattern found in `generate_resume_core_from_analysis` and `generate_resume_experience_from_analysis`, while retaining JD-only planning and avoiding their legacy source-history inputs.

1. Planning: required/optional requirements, role-level project stories, contributions and measurement opportunities.
2. Core writing: title, summary and technical skills together in one call, using the checked plan and selected mode.
3. Experience writing: all selected roles' bullets in one call, using the same checked plan, rules, mode and generated core sections. The plan controls contributions; core wording is coordination context, not evidence.
4. Assemble and validate the complete draft, then use the existing writing review and partial replacements.

Each writing schema permits only its assigned sections. Experience output cannot overwrite core sections. The plan and core sections are checkpointed before the experience request, allowing a failed experience request to resume without repeating either completed stage. Workflow version 4 invalidates checkpoints from the previous monolithic workflow to avoid silently reusing an old draft under the new flow.

Both scoped prompts preserve the existing writing policy. Experience instructions explicitly turn Work/Result/Measurement opportunity notes into natural bullets rather than copying planning labels. No new source resume, source accomplishments or source skills are added.

The older standalone experimental diagnostic route remains separate. Review criteria and the partial-repair merge are unchanged. No live API request was made for this change, so no claim is made that total latency or generated writing quality has improved. Sequential splitting reduces per-response scope but adds a request; total time must be measured.

Validation covers shared plan/mode handoff in Professional, New Grad, Internship and Co-op; core preservation during experience assembly; checkpoint recovery; extension save behavior; and continued partial repair. Extension production build succeeded.

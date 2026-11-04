# JD-only is the normal Generate Resume workflow

The app and extension now generate through one shared workflow: raw JD and selected employment headings → mode-aware project/contribution plan → concise XYZ bullets, headline, summary and skills → assembled review and one targeted repair when needed → normal resume editor/preview.

The generator receives no saved source bullets, skills, summary, projects or achievement evidence. Employment companies, titles, dates, locations and bullet limits are allowlisted. Profile/contact/education data remain available to the existing document layout locally. Revisions can use the current draft only after it was generated through JD-only; an older source-based resume is not forwarded as generation evidence.

Professional, Internship, Co-op and New Grad use the same workflow. The student modes retain prior experience and mid-level implementation depth while avoiding senior/team-lead positioning. Regeneration receives the selected profile mode.

The separate experimental panel and its Settings toggle were removed from both user flows. Existing Generate actions, editor, preview, Original/Reviewed versions, manual edits, PDF quality gates and review retry remain. The older `/api/ai/generate` endpoint also delegates to the shared workflow. The legacy stage endpoints and hidden diagnostic experiment endpoints remain for compatibility; normal app/extension generation does not call them.

JD-only review retries use the JD, plan, headings, selected mode and edited draft, without introducing saved source evidence. Proposed project details and measurements stay identified in the existing review UI rather than being inserted as questions or labels in resume sentences. A writing-review pass does not establish factual accuracy. If review fails, the validated original remains visible with a retryable review error.

Verification: 475 Python tests passed, including source-isolation sentinels, all four modes, extension/MCP queue behavior, review retries, version preservation and review outages. Both production builds and existing UI contract checks passed. A browser test with simulated responses clicked the normal Generate action in New Grad mode and verified direct resume preview, existing versions and absence of the experiment panel. No live OpenAI requests, applications or emails were sent during this integration change.

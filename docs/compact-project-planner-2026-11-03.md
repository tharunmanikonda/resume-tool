# Compact project planning

The planner now extracts a short engineering focus and selects one independent
proposed project per employment period. It no longer returns required/optional
classification arrays. The original posting is still provided in one request;
there is no separate extraction call.

Contributions are returned as work, outcome and measurement objects. Local
normalization joins them into the existing exact-string contribution contract,
preserving order for targeting corrections and writing. Older string-based plans
remain readable. The experimental view supports both plan formats.

Targeting, writing and review share the project-context policy: preserve each
role's own purpose, users, workflow and career scope rather than transplanting the
hiring company's business. A planning policy fingerprint prevents an old cached
plan and downstream draft from silently bypassing the new planner.

Verification: 660 Python tests passed; app and extension builds passed. New tests
exercise structured-plan normalization and all downstream handoffs in professional,
new-grad, internship and co-op modes without adding calls.

One isolated live planning call used a different ready Rust/Python application,
with the exact production prompt, schema and boundary. It completed on attempt 1
in 18.26 seconds and passed structural validation. It selected platform APIs,
internal gateway work, reporting modules and earlier UI implementation, keeping
AI-assisted engineering separate from building an AI product. This was a planning
test, not a complete live resume generation. The saved application was unchanged.

Content limitations remain: some security outcomes use diagnosis-time measures,
and one test contribution still links regression prevention to coverage. Passing
structural validation does not establish narrative quality or factual correctness.
All generated project contexts remain proposed, not verified employment evidence.

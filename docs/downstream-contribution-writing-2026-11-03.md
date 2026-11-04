# Contribution selection in the experience writer

The planner now selects engineering focus and each role's title, system, workflow,
scope and core technology assumptions. Its schema no longer contains contributions.
The existing experience-writing call chooses contributions and produces the final
bullets together, rather than expanding preselected outcome/measurement pairs.
No production model stage was added.

The live-tested writer prompt includes visible-number metadata matching, direct
technical attribution, career scope and natural language guidance. The existing
typed-ID reviewer applies exact replacements for awkward units or unsupported
claims. Its quality guidance was updated alongside the writer. Qualitative
normalization remains the same local step used by the app.

Targeting schemas now restrict corrections to fields actually present in the
plan; project-only plans cannot receive nonexistent contribution replacements.
Legacy plans with contribution notes still normalize and validate. Planning policy
version 4 invalidates incompatible cached planning/writing checkpoints.

Verification: 665 Python tests and both app/extension builds passed. Added coverage
exercises project-only handoffs across all four profile modes with the same five
stages, alongside existing legacy-plan compatibility tests.

Live tests used the previously saved independent Cosign project contexts with all
contribution notes removed. Two writer tests and one existing-flow review were
run; no applications, emails or saved resumes were changed. The selected writer
took 22.37 seconds; the review took 11.69 seconds and replaced four bullets. After
the app's normal metadata cleanup, there were no structural validation issues.
Numerical coverage shortfalls remained advisory in two roles. These timings do
not include fresh planning, targeting or core-section generation.

The reviewed draft was judged approximately 8/10 in editorial quality, a subjective
assessment rather than a calibrated score or factual verification. It still needs
confirmation of project details and numerical claims; unit tests establish pipeline
compatibility, not that every future generated sentence will be correct.

## Career scope follow-up

Planning policy version 5 adds shared career-scope guidance to planning, targeting,
core writing, experience writing and review. Earlier-career work should demonstrate
scoped implementation inside an existing team system; later roles may demonstrate
independent features and broader responsibility. Tool familiarity is distinct from
choosing architecture or owning the platform. The policy uses dates and available
history, never a special employer name, array order or selection count. A single
selected recent role is not automatically entry level. It does not force Junior
titles or mechanically replace verbs with "assisted."

All-mode handoff tests verify the guidance reaches all five stages. The 665-test
suite passed. No additional paid model call was made for this follow-up; the saved
test resumes are unchanged.

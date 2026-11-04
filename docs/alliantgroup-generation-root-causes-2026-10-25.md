# alliantgroup generation: failed checks and latency

The saved task history contains six failed attempts for draft `draft-0bf256e7582f48548978e062b055124b`. Local validation is fast; repeated model calls after validation failures account for the delay. These are application checks, not ATS checks.

| Attempt | Time in worker | Saved failure |
| --- | ---: | --- |
| 1 | 75.5 seconds | Required JD quote/label mismatch |
| 2 | 62.1 seconds | Required and optional JD quote/label mismatches |
| 3 | 50.0 seconds | Optional qualification ranked required |
| 4 | 52.7 seconds | Required JD quote/label mismatch |
| 5 | 95.4 seconds | Skills formatting: `.NET Core / .NET` |
| 6 | 54.5 seconds | Skills formatting: `ETL / batch ingestion`, `OAuth2 / JWT` |

Total worker time across these attempts: approximately 390 seconds (6 minutes 30 seconds). This was multiple failed attempts and user-triggered retries, not one continuously running job. Each plan call took approximately 20–38 seconds in the logs; each draft call approximately 25–32 seconds. A single automatic repair therefore added another full model request before the task failed.

## Confirmed failure cases

The slash check rejected any skill containing a spaced slash. It treated valid alternatives/groupings as an invalid project description and blocked the entire resume. Those terms can instead be split locally: `OAuth2`, `JWT`, `ETL`, `batch ingestion`, `.NET Core`, `.NET`. Established names without spaced slashes, such as `CI/CD` and `TCP/IP`, are preserved.

The original plan check combined two distinct conditions into one generic error: whether a quote existed in the JD and whether a short capability label appeared literally within that quote. Against this actual JD, the label `.NET` with the actual phrase `dot-net` fails the old check. This is a reproduced validator failure mode; the earlier rejected model plans were not saved, so it is not proof that this exact pair caused attempts 1, 2 or 4.

The priority check used the first occurrence of a short quote and examined text after it. Against this JD, a required label `Confluence` can be associated with the earlier documentation sentence ending in `desirable`, even though the intended reference is the later tools section. This reproduces a context-selection defect; the precise rejected quote from attempt 3 was not retained.

A local benchmark of the accepted saved plan averaged approximately 15 milliseconds per plan check. The checks themselves did not consume the minutes; their rejection triggered more model generation.

## Changes and their purpose

- Planning selects a source-clause identifier from the actual JD. The server resolves the original text, avoiding fragile quote transcription and comparisons between normal labels and posting typography. Preference checks inspect that selected clause.
- Safe spaced-slash formatting is normalized locally. Subjective skill descriptions are review hints, not pre-review generation blockers.
- The 80% numerical-evidence goal remains in the writing instructions and review notes. Missing the advisory target alone no longer triggers a full draft rewrite.
- Invalid plans and drafts, their exact failed checks and completed steps are checkpointed. A retry resumes the affected stage instead of discarding completed work.
- Each new model call saves its prompt, schema, inputs, output/error and timing locally in `tmp/jd-generation-traces/`. API keys are excluded.
- Local validation exceptions are explicitly marked non-network errors. A skill phrase containing the word `timeout` cannot accidentally trigger the network retry wrapper. This is a separately reproduced risk, not a confirmed cause of these six failures.

## Checks that remain blocking

Missing role/section content; wrong selected role keys or contribution structure; internal status labels in visible resume text; unfinished placeholders/questions; inconsistent measurement text versus metadata; and genuine mandatory-versus-preferred conflicts still require repair. The final reviewer continues to assess relevance, technical coherence, duplication, scope and wording with one bounded repair. A writing review does not verify proposed work-history details or measurements.

The six historical failures did not reach a successful final review, and did not fail ATS screening. Earlier per-check raw outputs cannot be reconstructed; new traces are intended to remove that diagnostic blind spot.

## Approved live verification

Task `task-fb3c8c31644a4c1f9ae6fd1107bd9496` reused the saved plan and took 58.9 seconds. Draft generation took 33.9 seconds and its repair took 25.0 seconds. The slash failures did not recur. The task still failed before review because the repair retained unused measurement metadata on qualitative sentences: for example, `value: 1`, `unit: ingestion pipeline` while the sentence said “a ... pipeline” without a quantity. Other records used `N/A` while incorrectly retaining quantitative kinds.

The exact outputs are saved in traces `b736ce49fb3e43a8be9869c51350cc0d` and `472d31060fe84c4aa5f697c8cff0b107`. This is a confirmed model output/metadata mismatch, rather than speculation from an old generic error.

The additional fix treats visible prose as authoritative: when it contains no measurement, locally clear value/unit and set kind/status to qualitative. It does not add numbers, rewrite bullets or erase conflicting quantities that actually appear in prose. Both captured outputs pass draft validation after this normalization; no further API call was made. Local replay results are saved in `tmp/alliantgroup-generation-audit/live-replay.json`.

This removes a needless repair/failure path but does not establish a successful end-to-end generation: the approved live task failed before the additional fix and never reached final review. Both captured outputs contain only 2 quantitative bullets out of 19, a substantial miss against the 80% goal. That remains an explicit quality advisory rather than being represented as success. Final review latency and acceptance remain unverified for this retry.

Validation: 499 tests passed, including unused-metadata normalization, preservation of genuine quantity conflicts, slash skills, source-clause grounding and advisory-only shortfalls.

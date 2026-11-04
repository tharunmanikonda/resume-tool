# Fresh measurement-contract generation test

## Verdict

The local number-recognition fix works on fresh model output. The new measurement contract is followed structurally, and numerical validation/repair completed. **The generated content is not ready to approve:** semantic causal gaps and merging of separate accomplishments remain. A populated measurement connection field does not prove a source-supported connection.

## What ran

Three fresh OpenAI requests through the production generation/repair functions:

1. Recent roles: McKinsey and Uber.
2. Older roles: KPMG and Trigent.
3. The exact recent-role repair requested by validation.

Used the saved Domino’s JD, validated native-app analysis v4, saved skills and original work-history evidence. All four employers were generated anew, producing 19 experience bullets. Prompts, schema and outputs were saved separately. Analysis and skills were held fixed; synthesis, final audit and PDF export were not rerun. No saved draft/profile/application was changed.

The diagnostic harness initially prevented an automatic second request. Its second recent-call record is a local budget rejection, not an API request. The exact captured repair was then sent separately and saved in `recent-repair-call.json`.

## Numerical behavior

- All 19 new bullets received internal measurement records with kind, measure, value, unit, context and connection.
- The older-role batch passed on its first attempt.
- The recent batch was rejected for two substantive consistency errors: a sub-second response-time claim was labelled qualitative, and the fallback/uptime bullet's measurement metadata included 200,000+ weekly trips that did not appear in that bullet.
- The repair reclassified the response-time evidence as scale and made the trip count visible in the fallback/uptime bullet. Local production validation then passed with zero issues.
- No unsupported-50000+ false rejection occurred. Equivalent quantities and original telemetry scope were accepted.
- No confirmation placeholders were required for supplied measurements.

These results show that the new checks catch measurement-record contradictions. They also expose a weakness: the model can satisfy metadata/body consistency by adding a separately sourced number to a bullet, even when the causal relationship between those accomplishments is not established.

## Content review failures

| Fresh output | Assessment |
| --- | --- |
| McKinsey: increased interactions “by improving backend routing and evaluation latency” | Adds an implementation explanation not established by the cited referral-pipeline accomplishment. The formula appears to encourage filling a causal slot instead of leaving an unknown connection unresolved. |
| Uber: dashboards “reducing average UI latency to 1.2 seconds and improving troubleshooting speed” | Still credits monitoring with a latency reduction without naming an actual source-supported optimization. Adds a troubleshooting-speed outcome without a supplied measurement or clear implementation account. |
| KPMG: JWT authentication “preventing data integrity failures” | Preserves the source's weak causal wording; source provenance alone does not justify the causal claim. |
| Repaired Uber fallback bullet: maintained 99.9% uptime and “supported audits covering 200,000+ weekly trips” | Combines the fallback accomplishment with trip-audit volume from a different source bullet. Both numbers are supplied, but the specific combined responsibility is not established merely by citing both sources. This should be reviewed as a possible accomplishment merge, not accepted solely because the numbers match. |
| Trigent: tests “detected and fixed” regressions | Retains the distinction problem between test detection and the engineer's fixes. |

Recent-role requirement mapping also remains weak: monitoring/reliability is still labelled direct support for CI/CD, despite writing guidance against that substitution. This is a separate semantic coverage defect, not a numerical parser failure.

## Implication

The formula and number parser are necessary but insufficient. Numerical consistency must remain separate from:

- evidence for a specific action/result connection;
- permission to combine source accomplishments;
- requirement coverage actually demonstrated in a visible bullet;
- final human readability and technical credibility.

The next repair must distinguish “remove a mismatched metadata value” from “move that value into the bullet,” and require a causal explanation to be directly supported or omitted. This test does not establish an end-to-end quality pass or an ATS/hiring outcome.

Private test artifacts: `tmp/dominos-content-review/measurement-live-test/`.

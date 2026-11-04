# Explicit rate arithmetic validation — October 29, 2026

Salas O'Brien review trace `230609b38aa0486e8242529c110f4770` correctly targeted global bid 11 (Uber bullet 5). The reviewer removed a redundant parenthetical decimal, retaining “one per three releases” and metadata value `0.33`, unit `incidents per release`. Literal numeric-token comparison rejected the equivalent rounded rate. The typed-ID applier itself targeted the correct item.

Added a conservative explicit-ratio equivalence check in resume_measurements.py, used by the existing proposed-draft measurement validation. It requires a visible numerator and denominator, matching numerator/denominator units, and exact arithmetic or rounding to the metadata's declared decimal precision. The numerator noun must appear inline or immediately before the stated count. Zero denominators, negative counts, missing ratios, unrelated units and different magnitudes remain invalid. Fractional rates do not round down to an asserted zero. No visible content or measurement values are rewritten by the validator.

644 tests pass, including the exact production bullet, accepted decimal precision variants, explicit number words, mismatched values/units, missing denominators, zero denominators and negative counts.

Recovery: confirmed the saved JD and complete typed review item/ID table match the current editable resume. The canonical re-review snapshot lacks the original generation's internal measurement records, so its hash differs. The saved response was rebound only after exact item/role/text/ID and JD comparison, then applied through the normal snapshot-checked review path. Approved at revision 2, with original/manual versions preserved. Pre-recovery snapshot: tmp/salas-before-ratio-review-recovery.json. No new OpenAI requests.

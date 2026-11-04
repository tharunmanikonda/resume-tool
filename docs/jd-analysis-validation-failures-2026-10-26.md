# Repeated JD analysis failures

The local task history shows seven recent `JD target-work validation failed` attempts: four for Wellabe and three for Mintive. All stopped in preliminary JD analysis, before project planning and resume writing. The earlier fixes to `jd_draft_experiment.plan_issues` did not cover this separate validator in `resume_target_work.py`.

The preliminary model was required to return both a copied quote and a capability label literally contained in that quote. The server checked the quote as a contiguous posting substring and the capability as a literal substring of the quote. Equivalent typography could fail quote matching, and natural capability paraphrases could fail the second condition. A missing or unrelated quote must still fail, but a generic error did not distinguish these cases. Invalid raw outputs were not retained, so the exact historical phrase pairs cannot be reconstructed; these mechanisms are confirmed from code and local tests, not exact attribution of every lost model response.

The upstream extraction now supplies a numbered table of original posting spans. Its structured schema asks specialist requirements to select only a `source_span_id` from an enum. The server resolves the selected original text into the existing capability/jd_quote representation. The model no longer needs to generate two independently matching strings. The rest of target-work inference, routing, planning and writing remains in place.

Legacy-format checks normalize equivalent Unicode typography, case and whitespace. They still reject quotes that do not occur in the posting and capabilities attached to unrelated quotes. Source-reference normalization is not fuzzy semantic matching. Unknown source IDs fail. New cache versioning avoids reusing the old extraction contract.

Preliminary calls now save raw output, normalized result, exact validation issues, schema, prompt and timing in `tmp/jd-analysis-traces/`; API keys are excluded. Errors identify the requirement index and failing strings, instead of repeating only a generic message.

Validation: 527 tests passed. Coverage includes source-ID selection/resolution without extra calls, source immutability, schema and downstream compatibility, smart-apostrophe/hyphen equivalence while retaining C#/C++, invalid references and genuinely invented/unrelated evidence. No live API request was made for this fix and the saved failed drafts were not retried.

The separate GenPark failure in historical task records concerns a flattened required/preferred section reaching the planning priority checker. It is a different failure path, not evidence that this upstream quote extraction caused every historical issue. No blanket claim of eliminating all generation errors is made.

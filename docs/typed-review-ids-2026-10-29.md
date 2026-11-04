# Typed integer review IDs — October 29, 2026

User-approved contract:
- `tid`: main title ID (its own namespace).
- `psid`: professional summary ID (its own namespace).
- `sid`: skills group ID, numbered across the included groups.
- `bid`: experience bullet ID, numbered 1..N across every selected role, without restarting for each employer.

## New live review flow

The application captures an immutable draft and its exact bullet-ID-to-location mapping. It computes a snapshot ID covering the content and ordered bullet locations. The review receives typed `review_items` and that snapshot ID, not a separate unnumbered copy or a string target/link table.

The response has `review_summary`, `titles`, `summaries`, `skills`, `bullets` and `notes`. Unchanged sections return empty arrays. Each replacement includes its typed integer ID, replacement and reason. Bullets retain typed measurement metadata. The model does not return contribution numbers, role/local bullet targets, old_text, findings/dispositions, or change_indices. The code supplies those details from the saved mapping.

Example partial response:

```json
{
  "snapshot_id": "the supplied snapshot ID",
  "review_summary": "Clarified contributions",
  "titles": [{"tid": 1, "replacement": "Software Engineer", "reason": "Use the natural role title"}],
  "summaries": [],
  "skills": [],
  "bullets": [
    {"bid": 18, "replacement": "Complete revised bullet text", "measurement": {"kind": "qualitative", "value": "", "unit": "", "context": "", "status": "qualitative"}, "reason": "Clarify the contribution"}
  ],
  "notes": []
}
```

The application resolves ID 18 against the saved snapshot, creates an internal exact replacement, and applies the normal atomic replacement/content checks. Title/summary IDs cannot address bullets. Response order does not affect replacement location. Unknown, duplicate, wrong-type or stale IDs are rejected. A changed bullet count/order/content cannot reuse the old mapping. Database revision/run-token protections remain in place for edits during review.

Planner instructions, project fit, normal title policy, 25–30-word writing policy and numerical-evidence goals are unchanged by this addressing migration. No new model calls are added. The initial bounded writing-validation repair still has its existing internal exact-target contract; it does not use reviewer finding-to-change indices.

## Stored response compatibility

Pre-migration saved review responses can be read locally. Their exact targets and original text are validated, then converted to typed IDs using the captured snapshot. Their old change_indices are ignored entirely. New live review schemas do not request legacy fields. Legacy test/helper code remains available for stored payloads but is no longer on the new coordinated review path.

## Verification

628 Python tests pass. New coverage includes bids 12/15/18 returned in a different order, all four namespaces with ID 1 simultaneously, unchanged items, unknown/duplicate/non-integer IDs, insertion/deletion/reordering/text edits after capture, the new strict response schema, complete review/application of title + summary + skills + multiple bullets with one model call, and a stored response referencing nonexistent indices 4/5.

Transit Technologies recovery: compared its complete current editable resume/JD with saved trace `b253608889bb47749dd98e1b082f923a`. They matched. Converted/applied its already completed response through the new compatibility reader. Approved at revision 2; no additional OpenAI request. A pre-recovery snapshot is retained in tmp. New live-model adherence to the typed schema has not been tested with an external API request.

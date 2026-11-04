# JD section and qualification priority fix

The CHAMP Backend Engineer and ITW ERP Developer failures came from flattened JD text crossing responsibilities, required qualifications, preferred qualifications and benefits. LinkedIn's reader also collapsed all whitespace in description candidates. The planner selected a large source clause, normalization expanded paraphrased capability labels to that clause, and validation treated any preference marker in the paragraph as qualifying the required item.

Changes:
- Preserve visible description line breaks and recover block/list/BR separators in detached HTML fallbacks for LinkedIn, ATS and Dice readers. Compact title/company extraction remains unchanged.
- Split backend source text at section headings, existing sentence/newline boundaries and common glued requirement starts. Evidence remains exact source text; section priority is separate metadata, passed to planning and targeting.
- Preserve short model capability labels. For saved broad citations, narrow to a unique local passage using label terms; reject ambiguous evidence spanning required and preferred sections instead of guessing. Keep valid saved quotations when clause numbering changes.
- Validate local evidence and section priority, including optional items without their own preference marker. Restrict trailing preference lookup to the same local clause. Existing mixed-clause and parenthetical-preference checks remain.
- Include the source-parser version in workflow checkpoint fingerprints so retries do not reuse incompatible old clause IDs or corrupted labels.

Offline replay uses retained raw model outputs and their original source tables, not a new generation. ITW's saved case now passes. CHAMP no longer produces the six false optional-priority errors, but its raw model output truly classified mandatory Apache Camel integration/routing as optional. The new validation correctly retains that error. Moving only that requirement to required makes the replay pass. We did not silently reclassify it in production or change saved resumes.

Validation: 546 Python tests passed; real Chromium DOM extraction regression passed for visible LinkedIn descriptions and all three detached HTML fallbacks; ATS/review UI smoke checks passed; extension production build passed. Regression fixtures contain the public JDs and original requirement outputs, not private employment narratives.

The idle application was restarted on port 5001 with its extension worker enabled. Reload the unpacked extension and refresh the job page to use the extraction change. No live OpenAI requests were made and failed jobs were not automatically requeued.

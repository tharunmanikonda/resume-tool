# Additional JD parsing and priority edge cases

Scope: local parsing, citation preservation and required/optional validation. No resume content policy changes, no new OpenAI calls, no automatic retries of saved jobs.

Reproduced and corrected:
- Independent skills separated by commas or semicolons, including `Java required; AWS preferred`, rather than only separators followed by the word experience. Shared tool lists stay together. Separators inside parentheses/brackets are protected.
- Explicit optional/negated-required wording such as `Kubernetes is optional` and `Python is not required` within a generally required section.
- Parenthetical explanations such as `preferred but not required` or `preferred for this role`. These no longer disappear as if they were a preferred database/language variant. Named variants (Postgres preferred) and preferred durations retain the existing base-requirement behavior.
- Inline named preferences such as `cloud platforms, preferably AWS`: distinguish the underlying cloud capability from the preferred provider.
- Basic, bonus, desirable, optional and must-have heading variants; repeated whitespace, wrapped headings, nonbreaking spaces, common Unicode hyphens and Markdown heading punctuation.
- Abbreviated examples (`e.g.`), technology lists and version strings inside parentheses/brackets are preserved instead of split into fragments. Punctuation-only fragments are excluded.
- Explicit mandatory wording without a section heading remains enforceable. Travel requirements remain context, not mandatory engineering skills.

The parser still retains exact source substrings, short capability labels and local section/annotation priority. Ambiguous citations crossing required and optional sections remain rejected. Source-parser version 4 invalidates incompatible generation checkpoints on retry.

Validation: 581 Python tests passed. Saved CHAMP, ITW and T-Mobile regression replays remain covered, including retention of CHAMP's genuine Apache Camel misclassification. A structural scan of 100 recent saved JDs passed exact-substring evidence, nonempty evidence, deterministic clause IDs and priority-map alignment checks. This corpus scan checks structural integrity, not semantic correctness of every model plan.

No extension source changed in this follow-up. The idle backend was restarted after validation. Saved resumes and failed task records were not replaced or requeued.

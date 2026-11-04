# alliantgroup: previous versus compact-plan resume

One explicitly approved complete comparison ran with the same alliantgroup JD, employment headings, selected roles and Professional mode. The only generation-policy change was the shorter planning prompt with per-role career-depth guidance. No source accomplishments were supplied. The previous app resume was preserved; the new result is a local comparison artifact. Generation is variable, so one paired run is evidence about these outputs, not a reliable latency benchmark or hiring prediction.

| Measure | Previous | Current |
| --- | ---: | ---: |
| Total generation time | 120.5 sec | 101.7 sec |
| Planning time | 35.0 sec | 24.2 sec |
| Planning JSON characters | 15,955 | 5,795 |
| Planning text words | 1,847 | 682 |
| Resume words, including section labels | 924 | 739 |
| Resume characters | 7,012 | 5,318 |
| Experience bullets | 19 | 19 |
| Bullets with recognized quantities | 17/19 (89%) | 14/19 (74%) |
| Final model-review findings | 11 | 8 |
| Final writing-review disposition | Manual attention | Manual attention |

Planning response size fell 63.7%; total time fell 15.6% in this run. All 19 new contribution notes were 20 words or fewer. Current stage times: plan 24.200 sec; core 14.392; experience 16.517; first review 12.683; partial repair 21.886; second review 11.948. Both versions required a repair and second review. No output-limit failure occurred in the current run.

## Human assessment of these two outputs

The current version is the stronger starting draft overall: it is more readable, has a more conventional technical-skills list and clearer implementation contributions. Examples include Angular request batching/caching tied to page load, .NET/OpenAPI and database tuning tied to request latency, and explicit xUnit/Playwright work tied to an 18-percentage-point coverage increase. The previous version has awkward wording such as “target throughput of 1,200 RPS,” “audit security findings by 100 occurrences,” and “sprint predictability ... against planned vs delivered story-points.” Its skills catalog is longer and contains more project-description phrases.

The new result does not meet every user goal:

- Career progression remains incomplete. Trigent is frontend-focused, but “Built a reusable Angular component library and Storybook catalog, contributing 28 components” still gives it broad authorship without clearly expressing first-job responsibility boundaries. KPMG still uses unqualified database-design wording. The prompt addition alone did not establish the intended progression across every role. This is about responsibility scope, not a blanket ban on words such as “built,” “designed” or “led.”
- Numerical coverage decreased from 17 to 14 bullets. Current per-role counts are McKinsey 5/6, Uber 3/5, KPMG 4/5 and Trigent 2/3. Uber and Trigent miss their rounded 80% targets. The plan offered measurement opportunities for all contributions, but the writer/repair did not preserve useful quantification consistently.
- Metric quality remains uneven. Form-validation test pass rate and regression-run success rate are weaker accomplishment measures than clear application reliability or delivery outcomes. Some result attribution is broader than the planned mechanism.
- The new plan/summary give Azure ML inference more prominence, while the JD also requires AI-assisted development. The new resume does include Copilot development work, but the AI emphasis still merits review rather than assuming that any AI implementation is the right target story.
- C++, PHP and Flutter coverage remains absent from the proposed work. Adding keywords alone would not fix this. Some reviewer requests for baselines/methodology are debatable under the concise-bullet policy; finding counts are not an objective quality score.

Both outputs are proposed drafts, not verified candidate accomplishments. This comparison assesses writing and internal coherence, not factual truth, ATS passage or hiring success. The current resume should not be automatically selected for submission simply because it is shorter and faster.

## Next single issue to investigate

Check why responsibility boundaries were not explicit enough in the compact plan for earlier roles, and whether the writer followed those boundaries. Do this before changing metrics, review policy or the UI again. No additional code changes were made during this comparison.

## Local artifacts

- Previous resume: `tmp/compact-plan-comparison/previous-resume.md`
- Current resume: `tmp/compact-plan-comparison/current-resume.md`
- Current full result: `tmp/compact-plan-comparison/current.json`
- Timed calls and raw outputs: `tmp/compact-plan-comparison/current-calls.json`
- Previous timed run: `tmp/grouped-live-test-report.json`

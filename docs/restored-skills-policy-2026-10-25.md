# Restored skills selection

Restored the earlier core/skills policy inside the current JD-only grouped workflow: select the strongest relevant day-to-day skill names, avoid explanations and mini-sentences, omit weak categories, preserve category order, avoid repeated concepts, and use two to five items per included category. Removed the newer instructions to build a substantial section and preserve breadth across historical roles.

Normal app and extension generation now pass the existing analysis-selected skill-category route into the shared generator. Core generation uses that route's category list instead of the entire allowed-category union. Local category normalization uses the existing `normalize_skills_for_order` helper. Direct generator callers without analysis retain a fallback based on plan positioning. No extra model request was introduced.

Core schema limits item arrays to five. Skill-group repair replacements use the same role-category list and five-item maximum. This is a per-category bound, not a new arbitrary total-skills cap. The model should omit irrelevant categories rather than filling all allowed slots.

The old source-history generator is not re-enabled: skills still describe proposed mechanisms in the shared checked plan. Planning and experience structure, source-free inputs, partial merge, and review flow remain intact. Workflow version 5 prevents reuse of cached broad skills generated under the old policy.

No live API request or rewrite of a saved resume was performed. Tests cover category ordering/filtering, unchanged core-to-experience coordination, the two-to-five schema policy, repair limits and app/extension generation.

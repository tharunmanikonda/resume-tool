# Grouped writing live test

The app was restarted and one explicitly approved end-to-end alliantgroup Software Engineer test ran through the normal extension worker. Draft `draft-0bf256e7582f48548978e062b055124b`; task `task-ce4f819a67f442acb890416c9761bf57`.

| Call | Seconds | Response JSON characters |
| --- | ---: | ---: |
| Planning | 34.990 | 15,955 |
| Title, summary and skills | 11.947 | 3,543 |
| Experience bullets | 19.253 | 8,340 |
| First review | 12.560 | 3,868 |
| Partial repair | 28.835 | 3,685 |
| Second review | 12.799 | 4,126 |

Worker start-to-completion: **120.528 seconds**. Model calls total 120.384 seconds, with approximately 0.144 seconds elsewhere in the worker. Every request completed on its first attempt; no output-limit retry or transport retry appears in these traces.

The resume was assembled and saved successfully: draft status `ready`, audit status `manual_attention`, saved resume content 7,012 characters. This is successful generation/save, not a claim of final writing approval or verified candidate facts.

The partial repair returned eight replacements: one summary passage, four skill groups and three McKinsey bullets. The final review contains eleven findings. Some original flagged bullets in Uber, KPMG and Trigent were not patched; skill and measurement concerns also remain. Therefore the patch merge works, but the repair response did not resolve every first-review finding. No further repair was started and no code changes were made in response to this test.

Planning was the longest call; partial repair was second longest. Core and experience together took 31.2 seconds. In the earlier recorded run used for latency inspection, monolithic writing took 28.8 seconds and full rewrite took 23.7 seconds; that run had a different posting, so it is not a controlled speed comparison. The new patch response is much smaller than that earlier full rewrite (3,685 versus 9,116 JSON characters), but its request took longer. Smaller output alone did not establish a latency improvement in this single run; actual API token usage, reasoning-token usage and server waiting time are not recorded.

Exact timings, final findings and trace identifiers: `tmp/grouped-live-test-report.json`. API prompts and outputs remain in the existing local trace folder. No applications or emails were sent.

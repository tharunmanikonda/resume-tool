# Daily job monitor report

- Status: **Completed with failures**
- Scanned at: `2026-11-02T22:12:15+00:00`
- Monitors: 14
- New candidates: 0
- Needs review: 0

## Monitor results

| Monitor | Status | Fetched | Unseen | Candidates | Review | State updated |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| cbre | ok | 1258 | 59 | 0 | 0 | yes |
| cdk | ok | 39 | 2 | 0 | 0 | yes |
| cisco | ok | 80 | 5 | 0 | 0 | yes |
| crunchyroll | ok | 99 | 0 | 0 | 0 | yes |
| ebay | ok | 159 | 9 | 0 | 0 | yes |
| intepros | ok | 30 | 2 | 0 | 0 | yes |
| iqvia | failed | 0 | 0 | 0 | 0 | no |
| nbcu | ok | 293 | 10 | 0 | 0 | yes |
| nvidia | ok | 140 | 17 | 0 | 0 | yes |
| occ | ok | 67 | 3 | 0 | 0 | yes |
| ocient | ok | 15 | 0 | 0 | 0 | yes |
| rivian | ok | 30 | 0 | 0 | 0 | yes |
| tiktok | ok | 1875 | 12 | 0 | 0 | yes |
| waymo | ok | 169 | 0 | 0 | 0 | yes |

## Failures

- **iqvia**: Error: 502 Bad Gateway: https://iqvia.wd1.myworkdayjobs.com/wday/cxs/iqvia/IQVIA/jobs     at fetchJson (file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:205:27)     at process.processTicksAndRejections (node:internal/process/task_queues:95:5)     at async file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:588:23     at async worker (file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:193:24)     at async Promise.all (index 0)     at async mapWithConcurrency (file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:196:3)     at async workdayListings (file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:582:24)     at async main (file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:869:17)

## Not automated

- **Tesla**: Tesla still requires a dedicated virtual-list browser runner with complete index coverage.

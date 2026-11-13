# Daily job monitor report

- Status: **Completed with failures**
- Scanned at: `2026-11-13T20:22:31+00:00`
- Monitors: 14
- New candidates: 0
- Needs review: 1

## Monitor results

| Monitor | Status | Fetched | Unseen | Candidates | Review | State updated |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| cbre | ok | 976 | 34 | 0 | 0 | yes |
| cdk | ok | 47 | 0 | 0 | 0 | yes |
| cisco | ok | 80 | 2 | 0 | 0 | yes |
| crunchyroll | ok | 100 | 1 | 0 | 0 | yes |
| ebay | ok | 191 | 15 | 0 | 0 | yes |
| intepros | ok | 20 | 0 | 0 | 0 | yes |
| iqvia | ok | 799 | 23 | 0 | 1 | yes |
| nbcu | ok | 325 | 19 | 0 | 0 | yes |
| nvidia | failed | 0 | 0 | 0 | 0 | no |
| occ | ok | 60 | 0 | 0 | 0 | yes |
| ocient | ok | 15 | 0 | 0 | 0 | yes |
| rivian | ok | 30 | 0 | 0 | 0 | yes |
| tiktok | ok | 1873 | 4 | 0 | 0 | yes |
| waymo | ok | 164 | 1 | 0 | 0 | yes |

## Failures

- **nvidia**: Error: 500 Internal Server Error: https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs     at fetchJson (file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:235:21)     at process.processTicksAndRejections (node:internal/process/task_queues:95:5)     at async nvidiaListings (file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:513:21)     at async main (file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:929:67)

## Not automated

- **Tesla**: Tesla still requires a dedicated virtual-list browser runner with complete index coverage.

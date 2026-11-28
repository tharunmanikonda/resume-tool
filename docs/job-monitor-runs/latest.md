# Daily job monitor report

- Status: **Completed with failures**
- Scanned at: `2026-11-28T03:45:10+00:00`
- Monitors: 14
- New candidates: 0
- Needs review: 0

## Monitor results

| Monitor | Status | Fetched | Unseen | Candidates | Review | State updated |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| cbre | failed | 0 | 0 | 0 | 0 | no |
| cdk | ok | 44 | 0 | 0 | 0 | yes |
| cisco | ok | 60 | 0 | 0 | 0 | yes |
| crunchyroll | ok | 95 | 0 | 0 | 0 | yes |
| ebay | ok | 155 | 0 | 0 | 0 | yes |
| intepros | ok | 20 | 0 | 0 | 0 | yes |
| iqvia | ok | 359 | 0 | 0 | 0 | yes |
| nbcu | ok | 270 | 0 | 0 | 0 | yes |
| nvidia | ok | 100 | 0 | 0 | 0 | yes |
| occ | ok | 60 | 0 | 0 | 0 | yes |
| ocient | ok | 20 | 0 | 0 | 0 | yes |
| rivian | ok | 30 | 0 | 0 | 0 | yes |
| tiktok | ok | 1770 | 0 | 0 | 0 | yes |
| waymo | ok | 143 | 0 | 0 | 0 | yes |

## Failures

- **cbre**: locator.evaluateAll: Execution context was destroyed, most likely because of a navigation     at cbreSearchListings (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:813:68)     at async file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:846:14     at async worker (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:217:24)     at async mapWithConcurrency (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:220:3)     at async cbreListings (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:851:15)     at async main (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:973:13)

## Not automated

- **Tesla**: Tesla still requires a dedicated virtual-list browser runner with complete index coverage.

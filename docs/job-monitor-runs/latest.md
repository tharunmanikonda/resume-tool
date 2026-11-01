# Daily job monitor report

- Status: **Completed with failures**
- Scanned at: `2026-11-01T22:36:41+00:00`
- Monitors: 14
- New candidates: 6
- Needs review: 5

## Monitor results

| Monitor | Status | Fetched | Unseen | Candidates | Review | State updated |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| cbre | failed | 0 | 0 | 0 | 0 | no |
| cdk | ok | 38 | 0 | 0 | 0 | yes |
| cisco | ok | 60 | 0 | 0 | 0 | yes |
| crunchyroll | ok | 101 | 0 | 0 | 0 | yes |
| ebay | ok | 145 | 0 | 0 | 0 | yes |
| intepros | ok | 20 | 0 | 0 | 0 | yes |
| iqvia | ok | 1694 | 426 | 6 | 5 | yes |
| nbcu | ok | 201 | 0 | 0 | 0 | yes |
| nvidia | ok | 100 | 0 | 0 | 0 | yes |
| occ | ok | 60 | 0 | 0 | 0 | yes |
| ocient | ok | 15 | 0 | 0 | 0 | yes |
| rivian | ok | 30 | 0 | 0 | 0 | yes |
| tiktok | ok | 1871 | 0 | 0 | 0 | yes |
| waymo | ok | 169 | 0 | 0 | 0 | yes |

## New candidates

- **iqvia**: [Application Security Analyst I](https://iqvia.wd1.myworkdayjobs.com/job/Kathmandu-Nepal/Application-Security-Analyst-I_R1572581) (high; Kathmandu, Nepal)
  Match: target_title:security, profile_signal:python:+2, profile_signal:java:+1, profile_signal:javascript_react:+1, profile_signal:backend_apis:+2, profile_signal:cloud_containers:+2, profile_signal:qa_automation:+2
- **iqvia**: [Senior Software Engineer (Python and Java)](https://iqvia.wd1.myworkdayjobs.com/job/Kathmandu-Nepal/Software-Development-Engineer--Python-and-Java-_R1574719) (high; Kathmandu, Nepal)
  Match: target_title:software, profile_signal:python:+2, profile_signal:java:+1, profile_signal:backend_apis:+2, profile_signal:distributed_systems:+2, profile_signal:data_streaming:+2, profile_signal:databases:+1, profile_signal:cloud_containers:+2, profile_signal:observability:+1, profile_signal:qa_automation:+2
- **iqvia**: [Software Development Engineer (Python and Java)](https://iqvia.wd1.myworkdayjobs.com/job/Kathmandu-Nepal/Software-Development-Engineer--Python-and-Java-_R1574712) (high; Kathmandu, Nepal)
  Match: target_title:software, profile_signal:python:+2, profile_signal:java:+1, profile_signal:backend_apis:+2, profile_signal:distributed_systems:+2, profile_signal:data_streaming:+2, profile_signal:databases:+1, profile_signal:cloud_containers:+2, profile_signal:observability:+1, profile_signal:qa_automation:+2
- **iqvia**: [Senior Data QA Engineer](https://iqvia.wd1.myworkdayjobs.com/job/Kathmandu-Nepal/Senior-Data-QA-Engineer_R1574701) (medium; Kathmandu, Nepal)
  Match: target_title:technical_review, profile_signal:data_streaming:+2, profile_signal:databases:+1, profile_signal:cloud_containers:+2, profile_signal:qa_automation:+2
- **iqvia**: [Full Stack Engineer](https://iqvia.wd1.myworkdayjobs.com/job/Kathmandu-Nepal/Full-Stack-Engineer_R1574663) (medium; Kathmandu, Nepal)
  Match: target_title:full_stack, profile_signal:python:+2, profile_signal:java:+1, profile_signal:backend_apis:+2, profile_signal:cloud_containers:+2, profile_signal:qa_automation:+2
- **iqvia**: [AI Engineer](https://iqvia.wd1.myworkdayjobs.com/job/Athens-Greece/AI-Engineer_R1573508) (high; Athens, Greece)
  Match: target_title:ai_ml, profile_signal:python:+2, profile_signal:backend_apis:+2, profile_signal:databases:+1, profile_signal:cloud_containers:+2, profile_signal:qa_automation:+2, profile_signal:agentic_tooling:+3

## Failures

- **cbre**: page.goto: net::ERR_ABORTED at https://careers.cbre.com/en_US/careers/SearchJobs?search=platform+engineer&jobRecordsPerPage=25&jobOffset=25&jobSort=postedDate&jobSortDirection=DESC Call log:   - navigating to "https://careers.cbre.com/en_US/careers/SearchJobs?search=platform+engineer&jobRecordsPerPage=25&jobOffset=25&jobSort=postedDate&jobSortDirection=DESC", waiting until "domcontentloaded"      at cbreSearchListings (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:758:16)     at async file:///home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:795:14     at async worker (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:193:24)     at async mapWithConcurrency (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:196:3)     at async cbreListings (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:800:15)     at async main (/home/runner/work/resume-tool/resume-tool/ops/company_jobs_fetch.mjs:92...

## Not automated

- **Tesla**: Tesla still requires a dedicated virtual-list browser runner with complete index coverage.

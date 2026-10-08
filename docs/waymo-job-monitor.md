# Waymo Job Monitor

Last successful baseline scan: 2026-10-07 America/Chicago
Source: Official Waymo Careers search and job-detail pages

Latest trial scan: 2026-10-07 1:45 AM America/Chicago

- Current listings: 176
- New listing URLs: 0
- Baseline URLs no longer present: 0
- Detail pages opened: 0

## Baseline

- Department: Software Engineering
- Listings reviewed: 176
- Full-time listings: 137
- Full-time United States listings: 122
- Full-time U.S. title survivors before detailed requirements review: 62
- Stable result-list identity: canonical official job URL
- Numeric requisition ID: available only after opening a job-detail page
- Current highest numeric ID observed: `5542`
- Unique requisition IDs across 176 listings: 168

## Incremental Scan Strategy

1. Read the six lightweight Software Engineering result pages.
2. Canonicalize each job URL and calculate its identity hash.
3. Ignore URLs already present in `known_url_hashes`.
4. Open each unseen URL once to capture its requisition ID and advance the numeric high-water mark.
5. Apply title, employment-type, experience-level, and U.S. location filters to unseen URLs.
6. Fully classify requirements only for filter survivors and retain High or Medium matches.
7. Add every observed listing URL to the baseline after a successful scan.

## Programmatic Runner

Run the complete monitor with:

```text
.venv/bin/python waymo_job_monitor.py
```

The runner launches a headless browser, reads every result page, performs local URL deduplication and title filtering, opens only new surviving detail pages, extracts requisition IDs, classifies requirements, atomically updates the state file, and prints a JSON summary. Use `--dry-run` to test without changing state.

To build or reuse the cached catalog and return the ten highest-ID active matches:

```text
.venv/bin/python waymo_job_monitor.py --recent 10
```

The first run fetches details only for active listings that survive the local title, location, employment-type, and seniority filter. Later runs reuse the cached classifications and fetch details only for newly eligible URLs. The recent list includes High/Medium candidates plus Low review-worthy roles when fewer than ten strong matches exist; fully filtered roles remain excluded. Daily notifications continue to use only High/Medium candidates.

Waymo IDs generally increase as requisitions are created, but they are not a safe identity or ordering key:

- Search results are ordered by title rather than requisition ID.
- Active IDs ranged from `3246` to `5542` in the baseline and appeared in mixed order.
- Some IDs have revision suffixes, such as `4070-3`.
- Different active titles can share one ID. For example, `4304` appeared on three Perception roles and `4350` appeared on three Maneuvering Tech levels.

Waymo cannot safely use a numeric high-water mark as the first-stage filter because IDs are absent from search results and are not unique per listing. URL identity provides the same no-repeat behavior without opening old detail pages. Numeric IDs are retained only as recency evidence and reporting metadata; a new URL must never be rejected solely because its ID was previously seen.

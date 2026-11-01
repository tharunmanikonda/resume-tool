# GitHub Actions job monitors

The `Daily job monitors` workflow runs the repository's programmatic job
monitors once per day and can also be started manually from the Actions tab.

## Schedule

The workflow uses `0 13,22 * * *` (UTC), which runs at 7:00 AM and 4:00 PM
Central Standard Time. Because GitHub cron schedules use UTC, the same fixed
schedule runs at 8:00 AM and 5:00 PM during Central Daylight Time. GitHub may
delay scheduled jobs during periods of high Actions load.

The afternoon scan fetches the current official listings again. Stable job IDs
prevent already-seen roles from being processed or reported twice, while a role
first published during the day remains unseen and is evaluated normally.

## State and reports

Each monitor continues to use its existing authoritative state file:

```text
docs/<company>-job-monitor-state.json
```

A successful source updates its known IDs, candidate/rejected catalogs, source
timestamps, and last-successful-scan timestamp. A failed or incomplete source
does not update its state. The batch writes these aggregate artifacts:

```text
docs/job-monitor-runs/latest.json
docs/job-monitor-runs/latest.md
```

The workflow commits changed state and reports back to the branch using the
`github-actions[bot]` identity. The commit includes `[skip ci]`, preventing the
state-only commit from starting unrelated push workflows such as production
deployment.

The Action summary shows fetched/unseen counts, candidates, review items, and
source failures. The JSON report preserves candidate IDs, URLs, priorities,
matching requirements, and material gaps for downstream processing.

When a run finds at least one new candidate, the workflow opens a GitHub Issue
whose body contains the complete run summary and candidate links. GitHub can
then deliver the notification through email, the GitHub mobile app, or normal
repository notification subscriptions. The repository needs a `job-monitor`
issue label; the workflow creates or updates that label automatically.

## Repository setting

The workflow declares `contents: write`. The repository's Actions settings
must allow workflows to create commits. If the default branch has rules that
forbid direct bot pushes, grant the workflow an exception or change the commit
step to open a pull request.

## Manual run

From GitHub, open **Actions**, select **Daily job monitors**, and choose
**Run workflow**. Locally, the equivalent command is:

```bash
python job_monitor_batch.py
```

The command exits nonzero when any source fails, after writing the report and
retaining successful state updates from the other sources.

## Tesla

Tesla is intentionally not marked as scanned by this batch. Its current search
requires complete index coverage of a virtualized browser list. It should be
added only after a standalone browser runner reproduces that coverage check in
GitHub Actions; until then, the report lists Tesla under `not_automated`.

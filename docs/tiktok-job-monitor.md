# TikTok Job Monitor

The TikTok monitor reads the official Life at TikTok public careers API and
unions results from broad software, data, platform, reliability, cloud,
security, test, systems, database, mobile, and machine-learning searches.
Software engineering internship and co-op searches are included as well.

Stable TikTok job-post IDs are the deduplication key. The public API does not
provide a dependable posted date, so `first_seen_at` in
`docs/tiktok-job-monitor-state.json` is the freshness source of truth. Each
listing already includes its description and qualifications, allowing the
normal deterministic classifier to run without separate job-page requests or
OpenAI API calls.

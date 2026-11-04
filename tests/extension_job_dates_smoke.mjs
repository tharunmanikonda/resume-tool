import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const worker = fs.readFileSync('extension/public/service-worker.js', 'utf8');
const start = worker.indexOf('const jobContextTokens =');
const end = worker.indexOf('chrome.runtime.onMessage.addListener', start);
let fetchCount = 0;
let apiPayload = { id: 8846269002, first_published: '2026-11-03T17:51:29-05:00', updated_at: '2026-11-03T17:54:17-05:00' };
const writes = [], broadcasts = [];
const sandbox = vm.createContext({ URL, Map, Symbol, Date, AbortSignal,
  fetch: async (url, options) => { fetchCount++; assert.equal(options.credentials, 'omit'); return { ok: true, json: async () => apiPayload }; },
  chrome: { storage: { session: { set: async value => writes.push(value) } },
    action: { setBadgeBackgroundColor: async () => {}, setBadgeText: async () => {} },
    runtime: { sendMessage: async value => broadcasts.push(value) } },
});
vm.runInContext(worker.slice(start, end) + '\nthis.apiUrl = greenhouseJobApiUrl; this.fetchDates = fetchJobDates; this.publish = publishJobContext; this.tokens = jobContextTokens; this.requests = jobDateRequests;', sandbox);
const jobUrl = 'https://job-boards.greenhouse.io/censys/jobs/8846269002';
assert.equal(sandbox.apiUrl(jobUrl), 'https://boards-api.greenhouse.io/v1/boards/censys/jobs/8846269002');
for (const invalid of ['https://greenhouse.io.evil.test/censys/jobs/8846269002', 'https://evil.test/censys/jobs/8846269002', 'http://job-boards.greenhouse.io/censys/jobs/8846269002']) assert.equal(sandbox.apiUrl(invalid), '');
const dates = await sandbox.fetchDates({ url: jobUrl });
assert.equal(dates.posted_at, apiPayload.first_published);
assert.equal(dates.updated_at, apiPayload.updated_at);
assert.equal(dates.posted_at_source, 'greenhouse_api');
await sandbox.fetchDates({ url: jobUrl });
assert.equal(fetchCount, 1, 'Repeated context reads reuse the API result');
sandbox.requests.clear();
apiPayload = { id: 8846269002, updated_at: '2026-11-03T17:54:17-05:00' };
const updatedOnly = await sandbox.fetchDates({ url: jobUrl });
assert.equal(updatedOnly.posted_at, undefined, 'Updated time must never be treated as posted time');
sandbox.requests.clear();
apiPayload = { id: 123, first_published: '2026-11-03' };
assert.equal(await sandbox.fetchDates({ url: jobUrl }), null, 'Reject metadata for another job');
assert.equal(await sandbox.fetchDates({ url: 'https://jobs.dover.com/a/b' }), null);
const oldToken = Symbol(), currentToken = Symbol();
sandbox.tokens.set(1, currentToken);
await sandbox.publish(1, { source_metadata: dates }, oldToken);
assert.equal(writes.length, 0, 'Late API results cannot restore the previous job');
await sandbox.publish(1, { source_metadata: dates }, currentToken);
assert.equal(writes.length, 1);
assert.equal(broadcasts.length, 1);
sandbox.tokens.delete(1);
await sandbox.publish(1, { source_metadata: dates }, currentToken);
assert.equal(writes.length, 1, 'Closed or cleared tabs must stay cleared');

const panel = fs.readFileSync('extension/src/panel-main.jsx', 'utf8');
const formatStart = panel.indexOf('function jobDateDisplay(');
const formatEnd = panel.indexOf('function JobDates(', formatStart);
const format = vm.runInNewContext(panel.slice(formatStart, formatEnd) + '\nformatJobDate', { Date });
assert.equal(format(''), '');
assert.equal(format('not a date'), '');
assert.match(format('2026-11-03'), /Nov 3, 2026/);
assert.doesNotMatch(format('2026-11-03'), /AM|PM|GMT|UTC/, 'Date-only metadata must not invent a posting time');
console.log('Job date metadata smoke passed: API dates, cache, provenance, unavailable dates, stale-job guard, and date-only formatting.');

const display = vm.runInNewContext(panel.slice(formatStart, formatEnd) + '\njobDateDisplay', { Date });
const screenshotTime = Date.parse('2026-11-03T22:38:00-06:00');
const sourceTime = display('2026-11-03T23:02:23-06:00', screenshotTime);
assert.match(sourceTime.text, /Nov 3, 2026/);
assert.doesNotMatch(sourceTime.text, /11:02|PM|CST/);
assert.equal(sourceTime.note, 'Site reports a future time');
const zoneless = display('2026-11-03T23:02:23', screenshotTime);
assert.doesNotMatch(zoneless.text, /11:02|PM|CST/);
assert.equal(zoneless.note, 'Site did not provide a timezone');
const past = display('2026-11-03T17:51:29-05:00', screenshotTime);
assert.equal(past.note, '');
assert.match(past.text, /:/);
console.log('Date anomaly checks passed: future source timestamps flagged; timezone-less timestamps stay date-only.');

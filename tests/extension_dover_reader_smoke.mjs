import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const url = 'https://jobs.dover.com/fb8be073-3c76-4885-8d1f-d8dec5220eef/56aed3f6-7da1-4e7a-9bf4-b5418ae1744c';
  await page.route('https://jobs.dover.com/**', route => route.fulfill({ contentType: 'text/html', body: '<html><body><main><h1>Sr. Software Engineer</h1></main></body></html>' }));
  await page.goto(url);
  await page.evaluate(() => {
    window.messages = [];
    window.chrome = { runtime: { id: 'test', getManifest: () => ({version:'1.6.1'}), getURL: path => `https://extension.test/${path}`, sendMessage: async message => window.messages.push(message), onMessage: { addListener: () => {}, removeListener: () => {} } } };
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify({ '@type': 'JobPosting', title: 'Sr. Software Engineer', hiringOrganization: {name:'Caretria'}, datePosted: '2026-11-03', validThrough:'2026-12-03T22:23:02Z', description:'<p>Develop .NET applications and SQL Server databases. Design and maintain secure APIs, support production systems, review code, test business workflows, and collaborate with software engineering teams.</p>' });
    document.head.append(script);
  });
  await page.addScriptTag({ content: fs.readFileSync('extension/public/ats-content-script.js', 'utf8') });
  await page.waitForFunction(() => window.messages.some(m => m.type === 'JOB_CONTEXT'));
  const context = await page.evaluate(() => window.messages.find(m => m.type === 'JOB_CONTEXT').context);
  assert.equal(context.source, 'dover');
  assert.equal(context.external_job_id, '56aed3f6-7da1-4e7a-9bf4-b5418ae1744c');
  assert.equal(context.company_name, 'Caretria');
  assert.equal(context.source_metadata.posted_at, '2026-11-03');
  assert.equal(context.source_metadata.posted_at_source, 'page_metadata');
  assert.equal(context.source_metadata.updated_at, '');
  // Changing only metadata must still update the captured context.
  await page.evaluate(() => {
    const script = document.querySelector('script[type="application/ld+json"]');
    const job = JSON.parse(script.textContent); job.datePosted = '2026-11-02'; script.textContent = JSON.stringify(job);
  });
  await page.waitForFunction(() => window.messages.at(-1)?.context?.source_metadata?.posted_at === '2026-11-02');
  console.log('Dover reader smoke passed: role capture, date-only publication, expiry excluded, metadata updates.');
} finally { await browser.close(); }

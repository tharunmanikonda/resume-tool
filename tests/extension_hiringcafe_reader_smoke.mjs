import assert from 'node:assert/strict';
import fs from 'node:fs';
import { chromium } from 'playwright';

const source = fs.readFileSync('extension/public/hiringcafe-content-script.js', 'utf8');
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.route('https://hiringcafe.com/**', route => route.fulfill({ body: '<html><body><main></main></body></html>', contentType: 'text/html' }));
  await page.goto('https://hiringcafe.com/classic');
  await page.evaluate(() => {
    window.messages = [];
    window.listeners = [];
    window.chrome = { runtime: {
      id: 'test-runtime', getManifest: () => ({ version: '1.6.0' }),
      getURL: file => `https://extension.test/${file}`,
      sendMessage: async message => { window.messages.push(message); },
      onMessage: { addListener: fn => window.listeners.push(fn), removeListener: fn => { window.listeners = window.listeners.filter(item => item !== fn); } },
    } };
  });
  await page.addScriptTag({ content: source });
  await page.waitForFunction(() => window.messages.some(m => m.type === 'JOB_CONTEXT_CLEARED'));
  assert.equal(await page.evaluate(() => window.messages.filter(m => m.type === 'JOB_CONTEXT').length), 0, 'Search listings must not become jobs');

  const description = '<h2>Requirements</h2><ul><li>Build Python services and maintain production APIs with automated monitoring.</li><li>Design reliable distributed systems and collaborate with product teams to ship customer features.</li></ul>';
  // Mirrors the classic drawer: no URL change, Full View permalink, @ company, prose article.
  await page.evaluate(description => {
    document.querySelector('main').innerHTML = `<section role="dialog"><a href="/job/engineer-acme-job111">Full View</a><div><h1>Software Engineer</h1><div><span>@ Acme</span><a>View All Jobs</a></div><div><svg></svg><span>Austin, Texas</span></div></div><article class="prose">${description}</article></section>`;
  }, description);
  await page.waitForFunction(() => window.messages.some(m => m.context?.external_job_id === 'job111'));
  const first = await page.evaluate(() => window.messages.find(m => m.type === 'JOB_CONTEXT').context);
  assert.equal(first.company_name, 'Acme');
  assert.equal(first.role_title, 'Software Engineer');
  assert.equal(first.location, 'Austin, Texas');
  assert.equal(first.source, 'hiringcafe');
  assert.equal(first.url, 'https://hiringcafe.com/job/engineer-acme-job111');
  assert.match(first.job_description, /Requirements\n/);
  assert.match(first.job_description, /monitoring\.\nDesign/);

  // Reader reinjection should not duplicate the button, observers, or listeners.
  await page.addScriptTag({ content: source });
  assert.equal(await page.locator('#resume-generator-hiringcafe-trigger').count(), 1);
  assert.equal(await page.evaluate(() => window.listeners.length), 1);
  await page.getByRole('button', { name: 'Open Resume Generator' }).click();
  assert.equal(await page.locator('#resume-generator-hiringcafe-panel iframe').count(), 1);
  await page.getByRole('button', { name: 'Close Resume Generator' }).click();
  assert.equal(await page.locator('#resume-generator-hiringcafe-panel').count(), 0);

  // Change the selected job before the asynchronous description refreshes.
  await page.evaluate(() => {
    document.querySelector('[role=dialog] a').href = '/job/platform-beta-job222';
    document.querySelector('h1').textContent = 'Platform Engineer';
    document.querySelector('h1 + div span').textContent = '@ Beta';
  });
  await page.waitForFunction(() => window.messages.at(-1)?.type === 'JOB_CONTEXT_CLEARED');
  await page.waitForTimeout(1100);
  assert.equal(await page.evaluate(() => window.messages.some(m => m.context?.external_job_id === 'job222')), false, 'Old description must not be published under new job ID');
  await page.evaluate(() => {
    document.querySelector('article').innerHTML = '<h2>Platform requirements</h2><p>Build Kubernetes infrastructure and deploy secure production workloads. Support incident response, improve distributed system performance, and maintain reliable internal developer tooling for engineers.</p>';
  });
  await page.waitForFunction(() => window.messages.some(m => m.context?.external_job_id === 'job222'));
  const second = await page.evaluate(() => window.messages.at(-1).context);
  assert.equal(second.company_name, 'Beta');
  assert.match(second.job_description, /Kubernetes/);

  await page.evaluate(() => document.querySelector('[role=dialog]').remove());
  await page.waitForFunction(() => window.messages.at(-1)?.type === 'JOB_CONTEXT_CLEARED');

  // A full page uses matching JSON-LD; ignore structured data left by another job.
  await page.evaluate(description => {
    history.pushState({}, '', '/job/backend-gamma-job333');
    document.querySelector('main').innerHTML = `<div><h1>Backend Engineer</h1><div>Gamma</div><div class="mt-2">Chicago, Illinois</div></div><section id="job-description"><h2>Job description</h2><article>${description}</article></section>`;
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify({ '@type': 'JobPosting', identifier: { value: 'job222' }, title: 'WRONG ROLE', hiringOrganization: { name: 'WRONG COMPANY' }, description: 'Wrong description '.repeat(20) });
    document.head.append(script);
  }, '<h2>Backend requirements</h2><p>Develop Java services and event pipelines. Collaborate with engineering teams on scalable databases, production support, API reliability, security, performance, and continuous delivery automation.</p>');
  await page.waitForFunction(() => window.messages.some(m => m.context?.external_job_id === 'job333'));
  assert.equal(await page.evaluate(() => window.messages.at(-1).context.company_name), 'Gamma');
  await page.evaluate(() => {
    document.querySelector('script[type="application/ld+json"]').textContent = JSON.stringify({ '@type': 'JobPosting', identifier: { value: 'job333' }, title: 'Backend Engineer', hiringOrganization: { name: 'Gamma Inc' }, description: '<p>Verified backend description with Java, SQL, distributed data processing, secure APIs, continuous integration, production monitoring and operational ownership across all services.</p>' });
  });
  await page.waitForFunction(() => window.messages.at(-1)?.context?.company_name === 'Gamma Inc');
  await page.evaluate(() => { history.pushState({}, '', '/classic'); });
  await page.waitForFunction(() => window.messages.at(-1)?.type === 'JOB_CONTEXT_CLEARED');
  await page.evaluate(() => window.__resumeGeneratorHiringCafeLifecycle.shutdown());
  assert.equal(await page.locator('#resume-generator-hiringcafe-trigger').count(), 0);
  console.log('HiringCafe reader smoke passed: drawer, permalink, SPA updates, stale data, panel, reinjection, cleanup.');
} finally {
  await browser.close();
}

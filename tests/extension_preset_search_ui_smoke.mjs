import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { chromium } from "playwright";

const root = path.resolve("extension/dist");
const server = http.createServer((request, response) => {
  const file = path.resolve(root, "." + new URL(request.url, "http://localhost").pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) {
    response.writeHead(404); response.end(); return;
  }
  response.setHeader("Content-Type", file.endsWith(".js") ? "application/javascript" : file.endsWith(".css") ? "text/css" : "text/html");
  response.end(fs.readFileSync(file));
});
let browser;
try {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 360, height: 820 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    const event = { addListener() {}, removeListener() {} };
    window.openedSearches = [];
    window.chrome = {
      runtime: {
        id: "test-extension", onMessage: event,
        async sendMessage(message) {
          if (message.type.startsWith("OPEN_")) { window.openedSearches.push(message); return { success: true }; }
          if (message.path === "/api/extension/status") return { success: true, ai_ready: true, identities: [], experience_history: [] };
          return { success: true, drafts: [], profile: {}, application: {}, context: null };
        },
      },
      storage: { local: { async get() { return {}; }, async set() {} }, onChanged: event },
    };
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/sidepanel.html`);
  await page.getByRole("button", { name: "Job Search", exact: true }).click();
  await page.getByRole("button", { name: "48h", exact: true }).click();
  async function openPreset(label) {
    const before = await page.evaluate(() => window.openedSearches.length);
    await page.locator(".search-group").filter({ has: page.locator("h4").filter({ hasText: / - 48h$/ }) }).getByText(label, { exact: true }).click();
    await page.waitForFunction((count) => window.openedSearches.length > count, before);
    const opened = await page.evaluate(() => window.openedSearches.at(-1));
    assert.equal(opened.type, "OPEN_LINKEDIN_JOB_SEARCH");
    const url = new URL(opened.url);
    assert.equal(url.hostname, "www.linkedin.com");
    assert.equal(url.searchParams.get("f_TPR"), "r172800");
    assert.equal(url.searchParams.get("sortBy"), "DD");
    assert.equal(url.searchParams.get("location"), "United States");
    return url.searchParams;
  }
  for (const label of ["Workday", "Salesforce", "ServiceNow"]) {
    const params = await openPreset(label);
    assert.ok(params.get("keywords").includes(label));
    assert.equal(params.has("f_E"), false);
    assert.equal(params.has("f_JT"), false);
  }
  let params = await openPreset("Data analyst");
  assert.equal(params.get("keywords"), '"Data Analyst"');
  params = await openPreset("SWE internships");
  assert.ok(params.get("keywords").includes('AND ("Intern" OR "Internship")'));
  assert.equal(params.get("f_E"), "1,2");
  assert.equal(params.get("f_JT"), "I");
  params = await openPreset("SWE co-ops");
  assert.ok(params.get("keywords").includes('"Cooperative Education"'));
  params = await openPreset("New grad analyst");
  assert.ok(params.get("keywords").includes('AND ("New Grad" OR "New Graduate" OR "Recent Graduate")'));
  for (const width of [320, 560]) {
    await page.setViewportSize({ width, height: 820 });
    await page.getByRole("button", { name: "48h", exact: true }).scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: `/tmp/resume-preset-search-${width}.png` });
  }
  assert.deepEqual(errors, []);
  console.log("Preset search UI: platform and early-career buttons, broad analyst query, 48h URLs and responsive layout passed.");
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}

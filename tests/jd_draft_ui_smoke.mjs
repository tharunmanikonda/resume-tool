import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { build } from "vite";
import { chromium } from "playwright";

const root = process.cwd();
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "jd-draft-ui-"));
const entry = path.join(root, "tmp", "jd-draft-ui-entry.jsx");
const plan = { role_positioning: "Software Engineer", required: [{ capability: "Build APIs" }], optional: [{ capability: "Agents" }],
  experience: { mckinsey: { system: "Proposed account portal", workflow: "Implement and test APIs", scope: "Module implementation", assumptions: ["Proposed Java implementation"] } } };
const result = { plan, employment_headings: [{ key: "mckinsey", company: "Example Company" }],
  draft: { headline: "Software Engineer", summary: "Proposed application engineering work.", experience: { mckinsey: { bullets: [{ text: "Implemented versioned API contracts for 500 illustrative requests." }] } } },
  markdown: "# Proposed draft\n\nUnverified illustrative measurements", numerical_notes: [] };
fs.writeFileSync(entry, `import React from 'react'; import {createRoot} from 'react-dom/client'; import Draft from '../src/JdDraftExperiment.jsx';
const root=createRoot(document.getElementById('root')); window.requests=[];
const props={enabled:true, jobDescription:'Build APIs',enabledKeys:['mckinsey'],resumeMode:'professional',request:async(path,body)=>{window.requests.push({path,body}); return path.endsWith('/plan')?{plan_id:'plan-1'}:${JSON.stringify(result)};}};
root.render(React.createElement(Draft,props)); window.changeMode=()=>root.render(React.createElement(Draft,{...props,resumeMode:'new_grad'})); window.changeJd=()=>root.render(React.createElement(Draft,{...props,jobDescription:'A different job'}));`);
await build({ configFile: false, logLevel: "error", build: { outDir: temp, emptyOutDir: false,
  rollupOptions: { input: entry, output: { entryFileNames: "app.js" } } } });
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", req.url === "/app.js" ? "text/javascript" : "text/html");
  res.end(req.url === "/app.js" ? fs.readFileSync(path.join(temp, "app.js")) : '<div id="root"></div><script type="module" src="/app.js"></script>');
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 480, height: 900 }, acceptDownloads: true });
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.getByRole("button", { name: "Explore JD-only draft" }).click();
  await page.getByText("Implemented versioned API contracts for 500 illustrative requests.").waitFor();
  assert.ok(await page.getByRole("heading", { name: "Example Company" }).isVisible());
  const requests = await page.evaluate(() => window.requests);
  assert.equal(requests.length, 2);
  assert.ok(requests[0].path.endsWith("/plan") && requests[1].path.endsWith("/generate"));
  assert.deepEqual(Object.keys(requests[0].body).sort(), ["enabled_experience_keys", "job_description", "resume_mode"]);
  assert.deepEqual(requests[1].body, { plan_id: "plan-1", resume_mode: "professional" });
  await page.getByText("Proposed scope and assumptions").click();
  assert.ok(await page.getByText("Proposed Java implementation").isVisible());
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download proposed draft" }).click();
  const download = await downloaded;
  assert.match(fs.readFileSync(await download.path(), "utf8"), /Unverified illustrative/);
  await page.screenshot({ path: path.join(root, "tmp/jd-draft-ui-smoke.png"), fullPage: true });
  await page.evaluate(() => window.changeMode());
  await page.getByText("New Grad", {exact:true}).waitFor();
  await page.getByRole("button", { name: "Download proposed draft" }).waitFor({state:"detached"});
  await page.getByRole("button", { name: "Explore JD-only draft" }).click();
  await page.getByRole("button", { name: "Download proposed draft" }).waitFor();
  const modeRequests = await page.evaluate(() => window.requests.slice(-2));
  assert.equal(modeRequests[0].body.resume_mode, "new_grad");
  assert.equal(modeRequests[1].body.resume_mode, "new_grad");
  await page.evaluate(() => window.changeJd());
  await page.getByRole("button", { name: "Explore JD-only draft" }).waitFor();
  await page.getByRole("button", { name: "Download proposed draft" }).waitFor({state:"detached"});
  console.log("JD-only shared app/extension UI: generation, assumptions, download and stale-result reset passed.");
} finally {
  await browser.close();
  server.close();
  fs.rmSync(entry, { force: true });
  fs.rmSync(temp, { recursive: true, force: true });
}

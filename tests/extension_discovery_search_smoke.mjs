import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const root = process.cwd();
const panel = fs.readFileSync(path.join(root, "extension/src/panel-main.jsx"), "utf8");
const worker = fs.readFileSync(path.join(root, "extension/public/service-worker.js"), "utf8");

const expectations = [
  [panel, "googleRecentSearchUrl", "Google recent search URL builder"],
  [panel, "tbs: \"qdr:d,sbd:1\"", "past-24h and date-sort filter"],
  [panel, "site:boards.greenhouse.io", "Greenhouse discovery search"],
  [panel, "site:jobs.ashbyhq.com", "Ashby discovery search"],
  [panel, "site:jobs.lever.co", "Lever discovery search"],
  [panel, "site:ats.rippling.com", "Rippling discovery search"],
  [panel, "site:higheredjobs.com", "HigherEdJobs discovery search"],
  [panel, "linkedinJobSearchUrl", "LinkedIn jobs URL builder"],
  [panel, "LINKEDIN_JOB_SEARCHES", "LinkedIn job search presets"],
  [panel, "Core SWE", "Core SWE LinkedIn group"],
  [panel, "Intern / New Grad", "intern/new grad LinkedIn group"],
  [panel, "Web / Full Stack", "web/full stack LinkedIn group"],
  [panel, "Application / Integration", "application/integration LinkedIn group"],
  [panel, "Enterprise Platforms", "enterprise platform LinkedIn group"],
  [panel, "Platform / DevOps", "platform/devops LinkedIn group"],
  [panel, "Language-Based", "language-based LinkedIn group"],
  [panel, "QA Adjacent", "QA adjacent LinkedIn group"],
  [panel, '"Software Engineer" OR "Software Developer" OR "Software Development Engineer"', "Core SWE Boolean search"],
  [panel, '"Application Developer" OR "Application Engineer" OR "Application Integration Engineer"', "application engineer Boolean search"],
  [panel, '"Workday Engineer" OR "Workday Integration Engineer"', "Workday enterprise search"],
  [panel, '"Salesforce Developer" OR "Salesforce Engineer"', "Salesforce enterprise search"],
  [panel, '"ServiceNow Developer" OR "ServiceNow Engineer"', "ServiceNow enterprise search"],
  [panel, 'keywords: \'"Data Analyst"\'', "LinkedIn broad data analyst preset"],
  [panel, 'keywords: \'"Business Analyst"\'', "LinkedIn broad business analyst preset"],
  [panel, '"ERP Analyst" OR "Business Systems Analyst"', "LinkedIn ERP/business systems preset"],
  [panel, "LINKEDIN_TIME_WINDOWS", "LinkedIn time window selector"],
  [panel, "r3600", "LinkedIn 1h option"],
  [panel, "r14400", "LinkedIn 4h option"],
  [panel, "r21600", "LinkedIn 6h option"],
  [panel, "r43200", "LinkedIn 12h option"],
  [panel, "r64800", "LinkedIn 18h option"],
  [panel, "r86400", "LinkedIn 24h option"],
  [panel, "r172800", "LinkedIn 48h option"],
  [panel, "JobSearchWorkspace", "top-level Job Search workspace"],
  [panel, "workspace === \"job-search\"", "main Job Search tab"],
  [panel, "f_TPR: timeRange", "LinkedIn 24h filter"],
  [panel, "sortBy: \"DD\"", "LinkedIn newest-first sort"],
  [panel, "OPEN_LINKEDIN_JOB_SEARCH", "panel LinkedIn job opener"],
  [panel, "OPEN_DISCOVERY_SEARCH", "panel discovery opener"],
  [panel, "OPEN_JOB_SEARCH_RESOURCE", "panel job-search resource opener"],
  [panel, "FrogHireAI Chrome extension", "FrogHireAI resource"],
  [worker, "OPEN_LINKEDIN_JOB_SEARCH", "worker LinkedIn job opener"],
  [worker, "allowedTimeRanges", "worker restricts LinkedIn time windows"],
  [worker, "r64800", "worker allows LinkedIn 18h filter"],
  [worker, "r172800", "worker allows LinkedIn 48h filter"],
  [worker, "OPEN_DISCOVERY_SEARCH", "worker discovery opener"],
  [worker, "qdr:d", "worker requires past-24h filter"],
  [worker, "OPEN_JOB_SEARCH_RESOURCE", "worker job-search resource opener"],
  [worker, "froghire.ai/help/faq", "worker allows FrogHire FAQ"],
];

const missing = expectations
  .filter(([source, needle]) => !source.includes(needle))
  .map(([, , label]) => label);

if (missing.length) {
  throw new Error(`Missing extension discovery pieces: ${missing.join(", ")}`);
}

const start = panel.indexOf("function linkedinJobSearchUrl(");
const end = panel.indexOf("const LINKEDIN_TIME_WINDOWS", start);
assert.ok(start >= 0 && end > start);
const { groups, build } = vm.runInNewContext(`${panel.slice(start, end)}; ({ groups: LINKEDIN_JOB_SEARCHES, build: linkedinJobSearchUrl })`, { URLSearchParams });
const presets = groups.flatMap((group) => group.items);
const preset = (label) => {
  const item = presets.find((item) => item.label === label);
  assert.ok(item, `Missing preset: ${label}`);
  return item;
};
for (const item of presets) {
  const params = new URL(item.url).searchParams;
  assert.equal(params.get("keywords"), item.keywords, `${item.label}: query round-trips`);
  assert.equal(params.get("location"), "United States");
  assert.equal(params.get("sortBy"), "DD");
  let depth = 0;
  const logic = item.keywords.replace(/"[^"\n]+"/g, "TERM");
  assert.ok(!/"/.test(logic), `${item.label}: balanced quotes`);
  assert.ok(!logic.replace(/TERM|AND|OR|NOT|[()\s]/g, ""), `${item.label}: no implicit operators`);
  for (const char of logic) {
    if (char === "(") depth++;
    if (char === ")") depth--;
    assert.ok(depth >= 0, `${item.label}: balanced grouping`);
  }
  assert.equal(depth, 0);
  if (!item.experience) assert.equal(params.has("f_E"), false, `${item.label}: no hidden experience filter`);
  if (!item.jobType) assert.equal(params.has("f_JT"), false, `${item.label}: no hidden job type filter`);
}
for (const label of ["Data analyst", "Business analyst", "Product analyst", "Operations analyst"]) {
  assert.ok(!preset(label).keywords.includes("SQL"), `${label}: SQL is not mandatory`);
}
for (const label of ["New grad SWE", "New grad analyst"]) {
  const item = preset(label);
  assert.match(item.keywords, /\) AND \("New Grad" OR "New Graduate" OR "Recent Graduate"\)$/);
  assert.equal(new URL(item.url).searchParams.get("f_E"), "1,2");
}
assert.match(preset("SWE internships").keywords, /\) AND \("Intern" OR "Internship"\)$/);
assert.equal(new URL(preset("SWE internships").url).searchParams.get("f_JT"), "I");
assert.match(preset("SWE co-ops").keywords, /"Co-op" OR "Co op" OR "Coop" OR "Cooperative Education"/);
assert.match(preset("Junior / associate SWE").keywords, /\) AND \("Junior" OR "Associate"\)$/);
const enterprise = groups.find((group) => group.group === "Enterprise Platforms");
assert.deepEqual(Array.from(enterprise.items, (item) => item.label), ["Workday", "Salesforce", "ServiceNow"]);
for (const item of enterprise.items) {
  for (const phrase of item.keywords.matchAll(/"([^"]+)"/g)) assert.ok(phrase[1].startsWith(item.label));
}
for (const timeRange of ["r3600", "r14400", "r21600", "r43200", "r64800", "r86400", "r172800"]) {
  const params = new URL(build({ ...preset("New grad SWE"), timeRange })).searchParams;
  assert.equal(params.get("f_TPR"), timeRange);
  assert.equal(params.get("f_E"), "1,2");
}
assert.ok(preset("QA / test engineering").keywords.includes('"Test Engineer"'));
console.log(`Extension discovery: ${presets.length} presets, Boolean grouping, URL encoding, broad analyst searches, platform groups and explicit early-career filters passed.`);

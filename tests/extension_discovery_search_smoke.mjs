import fs from "node:fs";
import path from "node:path";

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
  [panel, '"Data Analyst" SQL', "LinkedIn data analyst preset"],
  [panel, '"Business Analyst" SQL', "LinkedIn business analyst preset"],
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

console.log("Extension discovery search smoke passed.");

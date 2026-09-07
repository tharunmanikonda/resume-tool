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
  [panel, "linkedinJobSearchUrl", "LinkedIn jobs URL builder"],
  [panel, "LINKEDIN_JOB_SEARCHES", "LinkedIn job search presets"],
  [panel, "LINKEDIN_TIME_WINDOWS", "LinkedIn time window selector"],
  [panel, "r3600", "LinkedIn 1h option"],
  [panel, "r14400", "LinkedIn 4h option"],
  [panel, "r21600", "LinkedIn 6h option"],
  [panel, "r43200", "LinkedIn 12h option"],
  [panel, "r64800", "LinkedIn 18h option"],
  [panel, "r86400", "LinkedIn 24h option"],
  [panel, "JobSearchWorkspace", "top-level Job Search workspace"],
  [panel, "workspace === \"job-search\"", "main Job Search tab"],
  [panel, "f_TPR: timeRange", "LinkedIn 24h filter"],
  [panel, "sortBy: \"DD\"", "LinkedIn newest-first sort"],
  [panel, "OPEN_LINKEDIN_JOB_SEARCH", "panel LinkedIn job opener"],
  [panel, "OPEN_DISCOVERY_SEARCH", "panel discovery opener"],
  [worker, "OPEN_LINKEDIN_JOB_SEARCH", "worker LinkedIn job opener"],
  [worker, "allowedTimeRanges", "worker restricts LinkedIn time windows"],
  [worker, "r64800", "worker allows LinkedIn 18h filter"],
  [worker, "OPEN_DISCOVERY_SEARCH", "worker discovery opener"],
  [worker, "qdr:d", "worker requires past-24h filter"],
];

const missing = expectations
  .filter(([source, needle]) => !source.includes(needle))
  .map(([, , label]) => label);

if (missing.length) {
  throw new Error(`Missing extension discovery pieces: ${missing.join(", ")}`);
}

console.log("Extension discovery search smoke passed.");

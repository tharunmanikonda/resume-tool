import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const manifest = JSON.parse(fs.readFileSync(path.join(root, "extension/public/manifest.json"), "utf8"));
const worker = fs.readFileSync(path.join(root, "extension/public/service-worker.js"), "utf8");
const launcher = fs.readFileSync(path.join(root, "extension/src/launcher.js"), "utf8");
const atsReader = fs.readFileSync(path.join(root, "extension/public/ats-content-script.js"), "utf8");

const scripts = manifest.content_scripts || [];
const atsEntry = scripts.find((entry) => (entry.js || []).includes("ats-content-script.js"));
if (!atsEntry) throw new Error("Manifest does not register ats-content-script.js.");

for (const pattern of ["*://jobs.lever.co/*", "*://boards.greenhouse.io/*", "*://jobs.ashbyhq.com/*", "*://ats.rippling.com/*"]) {
  if (!(atsEntry.matches || []).includes(pattern)) throw new Error(`ATS reader missing match pattern: ${pattern}`);
}

const expectations = [
  [worker, "isSupportedAtsJobUrl", "worker ATS URL detector"],
  [worker, "ats-content-script.js", "worker ATS reader injection"],
  [worker, "const isAts = isSupportedAtsJobUrl(jobUrl)", "worker opens ATS source links"],
  [worker, "*://jobs.lever.co/*", "worker Lever tab lookup"],
  [worker, "*://boards.greenhouse.io/*", "worker Greenhouse tab lookup"],
  [worker, "*://jobs.ashbyhq.com/*", "worker Ashby tab lookup"],
  [worker, "*://ats.rippling.com/*", "worker Rippling tab lookup"],
  [launcher, "ats-content-script.js", "launcher ATS reader injection"],
  [atsReader, "JOB_CONTEXT", "ATS reader publishes job context"],
  [atsReader, "JobPosting", "ATS reader parses JSON-LD"],
  [atsReader, "[\"boards\", \"job-boards\", \"job\"].includes(hostLabel)", "Greenhouse generic host falls back to path slug"],
  [atsReader, "companyFromDescription", "ATS reader infers company from description"],
  [atsReader, "Welcome to", "ATS reader handles Welcome to company text"],
  [atsReader, "greenhouse", "ATS reader detects Greenhouse"],
  [atsReader, "lever", "ATS reader detects Lever"],
  [atsReader, "ashby", "ATS reader detects Ashby"],
  [atsReader, "rippling", "ATS reader detects Rippling"],
];

const missing = expectations
  .filter(([source, needle]) => !source.includes(needle))
  .map(([, , label]) => label);

if (missing.length) {
  throw new Error(`Missing ATS reader pieces: ${missing.join(", ")}`);
}

console.log("Extension ATS reader smoke passed.");

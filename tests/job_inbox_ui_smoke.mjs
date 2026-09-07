import fs from "node:fs";
import assert from "node:assert/strict";

const source = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../src/app.css", import.meta.url), "utf8");

for (const expected of [
  "function JobInbox()",
  "/api/job-sources",
  "/api/job-sources/scan-all",
  "/api/job-leads?",
  "/promote-to-draft",
  "Fresh Jobs",
  "Create resume",
]) {
  assert.ok(source.includes(expected), `Job Inbox UI should include ${expected}`);
}

for (const expected of [
  ".job-workspace",
  ".job-tabs",
  ".job-content",
  ".job-row",
  ".source-form",
]) {
  assert.ok(css.includes(expected), `Job Inbox CSS should include ${expected}`);
}

console.log("job inbox UI smoke test passed");

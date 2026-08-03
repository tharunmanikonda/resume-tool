import assert from "node:assert/strict";
import fs from "node:fs";

const panelSource = fs.readFileSync(new URL("../extension/src/panel-main.jsx", import.meta.url), "utf8");
const cssSource = fs.readFileSync(new URL("../extension/src/panel.css", import.meta.url), "utf8");

assert.match(
  panelSource,
  /`\/api\/extension\/drafts\/\$\{encodeURIComponent\(draftId\)\}\/audit`/,
  "review failures must retain the extension audit retry route",
);
for (const removedRoute of ["/audit/apply", "/audit/keep-current", "/audit/resolve"]) {
  assert.ok(!panelSource.includes(removedRoute), `successful review UI must not use ${removedRoute}`);
}

for (const copy of [
  "Quality review",
  "Reviewing",
  "Passed",
  "Needs manual work",
  "Review failed",
  "Resume changed; review again",
  "Luna reviewed",
  "Original",
  "Luna Reviewed",
  "Changes",
  "Original generated resume · read only",
  "Retry review",
  "Open Full Editor",
]) {
  assert.ok(panelSource.includes(copy), `quality review UI must include ${copy}`);
}

for (const removedControl of ["Accept All", "Reject All", "Finish Review", ">Accept</button>", ">Reject</button>"]) {
  assert.ok(!panelSource.includes(removedControl), `successful review UI must remove ${removedControl}`);
}

for (const sourceRequirement of [
  "draft?.resume_versions",
  "resumeVersionsFromDraft(draft).original",
  "versions.luna_reviewed",
  "versions.manual",
  "draft?.active_resume_version",
  "function defaultResumeVersionView",
  'return "luna_reviewed"',
  "function ResumeVersionSelector",
  'data-resume-version-view="changes"',
  "auditReviewGroups(draft)",
  "auditValueText(group.current)",
  "auditValueText(group.proposed)",
  "{group.reason}",
  'resumeVersionView === "original"',
  'resumeVersionView === "changes"',
  'resumeVersionView === "luna_reviewed"',
]) {
  assert.ok(panelSource.includes(sourceRequirement), `version review behavior must include ${sourceRequirement}`);
}

const originalEditorGuard = panelSource.match(/resumeVersionView === "luna_reviewed" && \["ready", "pdf_ready"\]\.includes\(draft\.status\)/);
assert.ok(originalEditorGuard, "quick editing must only render for the reviewed/current resume view");

const unresolvedStart = panelSource.indexOf("const UNRESOLVED_AUDIT_STATUSES");
const unresolvedEnd = panelSource.indexOf("const RESOLVED_AUDIT_STATUSES", unresolvedStart);
const unresolvedSource = panelSource.slice(unresolvedStart, unresolvedEnd);
for (const status of ["not_started", "running", "reviewing", "changes_suggested", "manual_attention", "technical_failed", "stale"]) {
  assert.ok(unresolvedSource.includes(`"${status}"`), `unresolved audit statuses must include ${status}`);
}

const resolvedStart = panelSource.indexOf("const RESOLVED_AUDIT_STATUSES");
const resolvedEnd = panelSource.indexOf("const STATUS_LABELS", resolvedStart);
const resolvedSource = panelSource.slice(resolvedStart, resolvedEnd);
for (const status of ["approved", "applied", "kept_current"]) {
  assert.ok(resolvedSource.includes(`"${status}"`), `resolved audit statuses must include ${status}`);
}

const pdfButton = panelSource.match(/<button className="primary" disabled=\{[^}]+auditReviewUnresolved\(draft\)[^}]+\} onClick=\{generateDraftPdf\}/);
assert.ok(pdfButton, "Generate PDF disabled logic must keep using unresolved review state");
assert.ok(pdfButton[0].includes('busy.startsWith("audit-")'), "Generate PDF must stay disabled while retry is in flight");

const reviewBandStart = panelSource.indexOf("function QualityReviewBand");
const reviewBandEnd = panelSource.indexOf("function ReviewBasis", reviewBandStart);
const reviewBandSource = panelSource.slice(reviewBandStart, reviewBandEnd);
assert.ok(
  reviewBandSource.includes('state.status === "manual_attention"') && reviewBandSource.includes("quality-findings"),
  "manual-attention reviews must keep findings and recovery actions",
);
assert.ok(
  reviewBandSource.includes('state.status === "technical_failed"') && reviewBandSource.includes("onRetry"),
  "technical failures must retain Retry review",
);

for (const className of [
  ".resume-version-tabs",
  ".resume-version-tabs button.active",
  ".resume-version-note",
  ".quality-change-current",
  ".quality-change-proposed",
  ".quality-changes-view",
]) {
  assert.ok(cssSource.includes(className), `version review styling must include ${className}`);
}
assert.ok(!/quality-change-(?:current|proposed)[^{]*\{[^}]*gradient/i.test(cssSource), "review diff colors must not use gradients");

for (const existing of [
  '>Resume</button><button className={tab === "pdf"',
  ">PDF</button>",
  ">Messages</button>",
  ">Search</button>",
  "function AutofillWorkspace",
  "Application Autofill",
]) {
  assert.ok(panelSource.includes(existing), `existing panel behavior must remain present: ${existing}`);
}

console.log("extension review UI smoke test passed");

import assert from "node:assert/strict";
import fs from "node:fs";

const appSource = fs.readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");

function functionSource(name, nextName) {
  const start = appSource.indexOf(`async function ${name}`);
  const end = appSource.indexOf(`async function ${nextName}`, start + 1);
  assert.notEqual(start, -1, `${name} must exist`);
  assert.notEqual(end, -1, `${nextName} must follow ${name}`);
  return appSource.slice(start, end);
}

const generationFlow = functionSource(
  "continueAiGenerationFromAnalysis",
  "submitAiGeneration",
);

for (const route of [
  "/api/ai/generate-skills",
  "/api/ai/generate-experience-recent",
  "/api/ai/generate-experience-older",
  "/api/ai/final-synthesis",
  "/api/ai/quality-audit",
]) {
  assert.ok(generationFlow.includes(route), `generation flow must call ${route}`);
}

assert.ok(
  generationFlow.includes("Promise.all(["),
  "experience endpoints must run in parallel",
);
assert.ok(
  generationFlow.indexOf("/api/ai/generate-skills")
    < generationFlow.indexOf("/api/ai/generate-experience-recent"),
  "skills must run before experience",
);
assert.ok(
  generationFlow.indexOf("/api/ai/generate-experience-older")
    < generationFlow.indexOf("/api/ai/final-synthesis"),
  "final synthesis must run after experience",
);
assert.ok(
  generationFlow.indexOf("/api/ai/final-synthesis")
    < generationFlow.lastIndexOf("/api/ai/quality-audit"),
  "quality audit must run after final synthesis",
);
assert.ok(
  !generationFlow.includes("generate-title-summary"),
  "generation flow must not call generate-title-summary",
);
assert.ok(
  !generationFlow.includes("review-core"),
  "generation flow must not call review-core",
);

for (const control of [
  "Original",
  "Luna Reviewed",
  "Current Edits",
  "Changes",
  "View Changes",
  "Open Editor",
  "Retry review",
  "Start Editing",
]) {
  assert.ok(appSource.includes(control), `review control must include ${control}`);
}

for (const removedControl of ["Accept All", "Reject All", "Finish Review"]) {
  assert.ok(!appSource.includes(removedControl), `normal review UI must not include ${removedControl}`);
}

for (const contractField of [
  "resume_versions",
  "active_resume_version",
  "resume_content",
  "resume_snapshot",
  "luna_reviewed",
]) {
  assert.ok(appSource.includes(contractField), `version UI must consume ${contractField}`);
}

assert.ok(
  appSource.includes('setResumeVersionView(next.active)')
    && appSource.includes('setGeneratedContentProgrammatically(activeEntry.resume_content)'),
  "the active Luna/manual version must hydrate the editable resume",
);
assert.ok(
  appSource.includes('resumeVersionView === "original"')
    && appSource.includes('resumeVersionView !== "original"'),
  "Original must be selectable and excluded from the editable/PDF state",
);
assert.ok(
  appSource.includes('resumeVersionView === "changes"')
    && appSource.includes("<AuditChangeReview"),
  "Changes must render the existing review-group comparison",
);
assert.ok(
  !appSource.includes("/api/ai/quality-audit/apply")
    && !appSource.includes("/api/ai/quality-audit/keep-current")
    && !appSource.includes("/audit/apply")
    && !appSource.includes("/audit/keep-current"),
  "the main UI must not expose legacy manual review decisions",
);

assert.ok(
  appSource.includes('new URLSearchParams(window.location.search).get("review") === "1"'),
  "main app must recognize review=1 editor navigation",
);
assert.ok(
  appSource.includes("reviewGuidanceStatuses.has(nextAudit.status)")
    && appSource.includes("extensionReviewRequested")
    && appSource.includes("extensionReviewAutoOpenedRef.current"),
  "review guidance must auto-open once, only after an extension draft hydrates into a supported review state",
);
assert.ok(
  appSource.includes("A safe automatic repair was not available.")
    && appSource.includes("update the affected content"),
  "manual-attention guidance must explain why editor work is needed",
);
assert.ok(
  appSource.includes("formatAuditFindingPath(finding.path, audit.history || [])")
    && appSource.includes("<code>{finding.path}</code>"),
  "review findings must show a readable affected section and its audit path",
);
const qualityFooterStart = appSource.indexOf('title={audit.status === "manual_attention"');
const qualityFooterEnd = appSource.indexOf("<AuditChangeReview", qualityFooterStart);
assert.notEqual(qualityFooterStart, -1, "quality review modal must exist");
const qualityFooterSource = appSource.slice(qualityFooterStart, qualityFooterEnd);
assert.ok(
  appSource.includes("reviewGroups.length")
    && appSource.includes("group.current")
    && appSource.includes("group.proposed")
    && appSource.includes("group.reason"),
  "review changes must retain their red/green values and reason",
);
assert.ok(
  qualityFooterSource.includes('["manual_attention", "stale"].includes(audit.status)')
    && qualityFooterSource.includes("Start Editing"),
  "manual-attention and stale guidance must provide Start Editing without proposal actions",
);
assert.ok(
  appSource.includes("focusPreviewEditorRef.current = true")
    && appSource.includes("previewEditorRef.current?.focus"),
  "Start Editing must enter and focus the existing parsed-preview editor",
);

assert.ok(appSource.includes("/api/ai/regenerate"), "standalone regenerate route must exist");
assert.ok(appSource.includes("/regenerate`"), "extension regenerate route must exist");
assert.ok(appSource.includes(">Regenerate<") || appSource.includes("Regenerate\n"), "Regenerate action must exist");

const unresolvedStatuses = appSource.slice(
  appSource.indexOf("const unresolvedAuditStatuses"),
  appSource.indexOf("function auditStateFromPayload"),
);
for (const status of ["running", "reviewing", "changes_suggested", "manual_attention", "technical_failed", "stale"]) {
  assert.ok(unresolvedStatuses.includes(`"${status}"`), `PDF gating must include ${status}`);
}
assert.ok(
  appSource.includes("const reviewBlocksPdf = unresolvedAuditStatuses.has(audit.status)")
    && appSource.includes("&& !reviewBlocksPdf"),
  "Generate PDF eligibility must reject unresolved or stale reviews",
);

console.log("main review UI smoke test passed");

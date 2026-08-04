import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { chromium } from "playwright";

const profileDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "resume-tool-review-smoke-"));

function snapshot(company, title, summary, bullet) {
  return {
    name: "Test Candidate",
    contact: { location: "CA", phone: "555-0100", email: "test@example.com" },
    title,
    summary,
    technical_skills: [{ category: "Programming Languages", items: "Python, Java" }],
    experience: [{
      company,
      location: "CA, USA",
      dates: "May 2025 - Present",
      title,
      bullets: [bullet],
    }],
  };
}

function reviewedDraft(id, company, suffix) {
  const originalSnapshot = snapshot(company, `Original ${suffix} Engineer`, `Original ${suffix} summary`, "Built reliable services.");
  const lunaSnapshot = snapshot(company, `Luna ${suffix} Engineer`, `Luna reviewed ${suffix} summary`, "Built reliable backend services for customer workflows.");
  return {
    id,
    company_name: company,
    role_title: `${suffix} Engineer`,
    status: "ready",
    stage: "complete",
    locked: false,
    identity_id: "outlook",
    enabled_experience_keys: ["mckinsey"],
    experience_history_snapshot: [{
      key: "mckinsey",
      company: "McKinsey & Company",
      location: "CA, USA",
      title: `${suffix} Engineer`,
      dates: "May 2025 - Present",
      enabled: true,
    }],
    title_summary: {
      updated_title: lunaSnapshot.title,
      updated_summary: lunaSnapshot.summary,
    },
    skills: {
      updated_skills: [{ category: "Programming Languages", items: ["Python", "Java"] }],
    },
    experience_recent: {
      experience: {
        mckinsey: { title: lunaSnapshot.title, bullets: lunaSnapshot.experience[0].bullets },
      },
    },
    experience_older: { experience: {} },
    resume_content: `Luna reviewed ${suffix} resume`,
    preview: lunaSnapshot,
    resume_versions: {
      original: {
        resume_snapshot: originalSnapshot,
        resume_content: `Original ${suffix} resume`,
      },
      luna_reviewed: {
        resume_snapshot: lunaSnapshot,
        resume_content: `Luna reviewed ${suffix} resume`,
      },
    },
    active_resume_version: "luna_reviewed",
    resume_revision: 5,
    audit_status: "applied",
    audit_result: {
      schema_version: "2",
      decision: "applied",
      overall_score: 88,
      review_summary: "Luna applied two focused improvements.",
      component_scores: {
        ats_alignment: 90,
        technical_credibility: 88,
        human_tone: 86,
        evidence_quality: 89,
        career_coherence: 87,
      },
      manual_findings: [],
      review_groups: [{
        change_id: `skills.add-java.${id}`,
        section: "skills.skill_additions",
        current: null,
        proposed: { category: "Programming Languages", skill: "Java" },
        reason: "Added a supported language required by the role.",
      }, {
        change_id: `experience.mckinsey.rewrite-1.${id}`,
        section: "experience",
        role_key: "mckinsey",
        company: "McKinsey & Company",
        current: ["Built reliable services."],
        proposed: ["Built reliable backend services for customer workflows."],
        reason: "Made the supported outcome clearer.",
      }],
    },
  };
}

const currentDraft = reviewedDraft("draft-review-smoke", "Example Company", "Backend");
const secondDraft = reviewedDraft("draft-review-second", "Second Company", "Platform");
const servedDrafts = [structuredClone(currentDraft), structuredClone(secondDraft)];

const server = http.createServer((request, response) => {
  const sendJson = (status, payload) => {
    response.writeHead(status, { "content-type": "application/json" });
    response.end(JSON.stringify(payload));
  };
  if (request.url === "/api/extension/status") {
    sendJson(200, {
      success: true,
      server_ready: true,
      ai_ready: true,
      pdf_ready: true,
      onboarding_required: false,
      queue_paused: false,
      identities: [{ id: "outlook", label: "Outlook" }],
      experience_history: currentDraft.experience_history_snapshot,
    });
    return;
  }
  if (request.url?.startsWith("/api/extension/drafts?")) {
    sendJson(200, { success: true, drafts: servedDrafts });
    return;
  }
  const draftMatch = request.url?.match(/^\/api\/extension\/drafts\/([^/]+)$/);
  if (draftMatch && request.method === "PATCH") {
    let body = "";
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      const matchedDraft = servedDrafts.find((item) => item.id === decodeURIComponent(draftMatch[1]));
      const payload = JSON.parse(body || "{}");
      if (!matchedDraft || !payload.quick_edits) {
        sendJson(400, { success: false, error: "Missing quick edits" });
        return;
      }
      const nextSnapshot = structuredClone(matchedDraft.preview);
      nextSnapshot.title = payload.quick_edits.title;
      matchedDraft.preview = nextSnapshot;
      matchedDraft.resume_versions.manual = {
        resume_snapshot: nextSnapshot,
        resume_content: `Manually edited ${matchedDraft.role_title} resume`,
      };
      matchedDraft.active_resume_version = "manual";
      sendJson(200, { success: true, draft: matchedDraft });
    });
    return;
  }
  if (draftMatch && request.method === "GET") {
    const matchedDraft = servedDrafts.find((item) => item.id === decodeURIComponent(draftMatch[1]));
    if (matchedDraft) {
      sendJson(200, { success: true, draft: matchedDraft });
      return;
    }
  }
  if (request.url?.startsWith("/api/extension/autofill-profile")) {
    sendJson(200, {
      success: true,
      profile: { fullName: "Test Candidate", identityLabel: "Outlook" },
      application: {},
    });
    return;
  }
  sendJson(404, { success: false, error: `Unhandled test route: ${request.method} ${request.url}` });
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const serverUrl = `http://127.0.0.1:${server.address().port}`;
const extensionPath = path.resolve(process.env.EXTENSION_DIST_PATH || "extension/dist");
const context = await chromium.launchPersistentContext(profileDirectory, {
  headless: false,
  args: [`--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`],
});

try {
  let worker = context.serviceWorkers()[0];
  if (!worker) worker = await context.waitForEvent("serviceworker");
  const extensionId = new URL(worker.url()).host;
  await worker.evaluate((url) => chrome.storage.local.set({ resumeServerUrl: url }), serverUrl);

  const page = await context.newPage();
  await page.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await page.getByRole("button", { name: /Example Company/ }).first().click();

  const lunaTab = page.getByRole("tab", { name: "Luna Reviewed" });
  assert.equal(await lunaTab.getAttribute("aria-selected"), "true", "Luna Reviewed must be the default when present");
  await page.locator(".resume-preview h1").getByText("Luna Backend Engineer", { exact: true }).waitFor();
  await page.getByText("Edit resume content", { exact: false }).waitFor();
  await page.getByText("Luna reviewed", { exact: true }).waitFor();

  await page.getByText("Edit resume content", { exact: false }).click();
  const titleInput = page.getByLabel("Resume title");
  await titleInput.fill("Edited Backend Engineer");
  await page.getByText("Saved", { exact: true }).waitFor();
  await page.locator(".resume-preview h1").getByText("Edited Backend Engineer", { exact: true }).waitFor();

  await page.getByRole("tab", { name: "Original" }).click();
  await page.locator(".resume-preview h1").getByText("Original Backend Engineer", { exact: true }).waitFor();
  await page.getByText("Original generated resume · read only", { exact: true }).waitFor();
  assert.equal(await page.locator(".quick-editor").count(), 0, "Original view must not expose resume editing");

  await page.getByRole("tab", { name: "Changes" }).click();
  await page.locator(".quality-change-current").first().waitFor();
  await page.locator(".quality-change-proposed").first().waitFor();
  await page.getByText("Skills · skill additions", { exact: true }).waitFor();
  await page.getByText("McKinsey & Company experience", { exact: true }).waitFor();
  assert.equal(
    await page.locator(`[data-review-group="skills.add-java.${currentDraft.id}"] .quality-change-current`).innerText(),
    "REMOVE\nNot present",
    "a skill addition must show that no current content is removed",
  );
  assert.equal(
    await page.locator(`[data-review-group="skills.add-java.${currentDraft.id}"] .quality-change-proposed`).innerText(),
    "ADD\nProgramming Languages: Java",
    "a skill addition must display its category and skill",
  );
  assert.equal(await page.getByRole("button", { name: "Accept" }).count(), 0, "Changes view must not expose Accept");
  assert.equal(await page.getByRole("button", { name: "Reject" }).count(), 0, "Changes view must not expose Reject");

  await page.getByRole("button", { name: /Second Company/ }).first().click();
  await page.waitForFunction(() => document.querySelector('[role="tab"][aria-selected="true"]')?.textContent === "Luna Reviewed");
  assert.equal(await page.getByRole("tab", { name: "Luna Reviewed" }).getAttribute("aria-selected"), "true", "a new draft must reset to Luna Reviewed");
  await page.locator(".resume-preview h1").getByText("Luna Platform Engineer", { exact: true }).waitFor();

  console.log("extension review UI interaction smoke test passed");
} finally {
  await context.close();
  await new Promise((resolve) => server.close(resolve));
  fs.rmSync(profileDirectory, { recursive: true, force: true });
}

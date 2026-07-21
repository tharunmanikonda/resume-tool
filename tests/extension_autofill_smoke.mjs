import { chromium } from "playwright";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const extensionPath = path.resolve("extension/dist");
const serverUrl = process.env.RESUME_SERVER_URL || "http://127.0.0.1:5001";
const profileDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "resume-tool-extension-smoke-"));
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
  page.on("console", (message) => console.log("PAGE", message.type(), message.text()));
  await page.route("https://boards.greenhouse.io/example/jobs/123", async (route) => route.fulfill({
    contentType: "text/html",
    body: `<!doctype html><html><body>
      <main><h1>Software Engineer application</h1>
        <form id="application-form">
          <label for="full_name">Name</label><input id="full_name" name="full_name" required>
          <label for="first_name">First Name</label><input id="first_name" name="first_name" required>
          <label for="last_name">Last Name</label><input id="last_name" name="last_name" required>
          <label for="email">Email</label><input id="email" name="email" type="email" required>
          <label for="phone">Phone</label><input id="phone" name="phone" type="tel">
          <label for="interest">Why are you interested in this role?</label><textarea id="interest" name="interest" maxlength="500"></textarea>
          <label for="auth">Are you legally authorized to work in the United States?</label>
          <select id="auth" name="work_authorization"><option value="">Select</option><option value="yes">Yes</option><option value="no">No</option></select>
          <label for="resume">Resume</label><input id="resume" name="resume" type="file" accept=".pdf">
          <button id="next" type="button">Next step</button>
          <button type="submit">Submit application</button>
        </form>
        <script>
          document.querySelector('#first_name').addEventListener('input', (event) => event.target.dataset.frameworkState = event.target.value);
          document.querySelector('#next').addEventListener('click', () => {
            document.querySelector('#application-form').innerHTML = '<label for="linkedin">LinkedIn URL</label><input id="linkedin" name="linkedin_url"><label for="sponsor">Will you require visa sponsorship?</label><select id="sponsor" name="sponsorship"><option value="">Select</option><option value="yes">Yes</option><option value="no">No</option></select>';
          });
        </script>
      </main>
    </body></html>`,
  }));
  await page.goto("https://boards.greenhouse.io/example/jobs/123");
  await page.waitForSelector("#resume-generator-global-trigger", { timeout: 10000 });
  await page.click("#resume-generator-global-trigger");
  const panel = page.frameLocator("#resume-generator-global-panel iframe");
  const resumeTab = panel.getByRole("button", { name: "Resume", exact: true });
  await resumeTab.waitFor();
  if (!(await resumeTab.getAttribute("class"))?.includes("active")) throw new Error("Resume workspace was not selected by default.");
  await panel.getByRole("button", { name: /Autofill/ }).click();
  await panel.getByText("Application questions").waitFor();
  await panel.getByText("Why are you interested in this role?").waitFor();
  const resumeSelect = panel.getByLabel("Resume to attach and answer with");
  const selectedDraftId = await resumeSelect.inputValue();
  const selectedDraftResponse = await fetch(`${serverUrl}/api/extension/drafts/${encodeURIComponent(selectedDraftId)}`);
  const selectedDraft = (await selectedDraftResponse.json()).draft;
  const questionRow = panel.locator(".application-question").filter({ hasText: "Why are you interested in this role?" });
  const questionId = await questionRow.getAttribute("data-question-id");
  const expectedClipboard = "This is a clipboard smoke-test answer.";
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: "https://boards.greenhouse.io" });
  await worker.evaluate(({ key, question, answer, revision }) => chrome.storage.local.set({
    [key]: { [question]: { answer, resume_revision: revision, created_at: new Date().toISOString() } },
  }), {
    key: `resumeAutofillAnswers:${selectedDraftId}`,
    question: questionId,
    answer: expectedClipboard,
    revision: selectedDraft.resume_revision,
  });
  await resumeSelect.selectOption("");
  await resumeSelect.selectOption(selectedDraftId);
  await questionRow.getByRole("button", { name: "Copy" }).click();
  const copiedText = await page.evaluate(() => navigator.clipboard.readText());
  if (copiedText !== expectedClipboard) throw new Error(`Clipboard mismatch: ${copiedText}`);
  await panel.getByRole("button", { name: "Fill this page" }).click();
  await page.waitForTimeout(1500);
  await panel.getByRole("button", { name: "Attach resume" }).click();
  await page.waitForFunction(() => document.querySelector("#resume")?.files?.length === 1);

  const values = await page.evaluate(() => ({
    fullName: document.querySelector("#full_name").value,
    firstName: document.querySelector("#first_name").value,
    lastName: document.querySelector("#last_name").value,
    email: document.querySelector("#email").value,
    phone: document.querySelector("#phone").value,
    authorization: document.querySelector("#auth").value,
    resumeName: document.querySelector("#resume").files?.[0]?.name || "",
    frameworkState: document.querySelector("#first_name").dataset.frameworkState || "",
  }));
  if (!values.fullName || !values.firstName || values.frameworkState !== values.firstName || !values.lastName || !values.email || values.authorization !== "yes" || !values.resumeName.endsWith(".pdf")) {
    const panelText = await panel.locator("body").innerText();
    throw new Error(`Unexpected autofill values: ${JSON.stringify(values)}\nPanel: ${panelText}`);
  }
  await page.locator("#next").evaluate((element) => element.click());
  await page.waitForFunction(() => document.querySelector("#linkedin")?.value && document.querySelector("#sponsor")?.value);
  values.linkedin = await page.inputValue("#linkedin");
  values.sponsorship = await page.inputValue("#sponsor");
  await page.screenshot({ path: "/tmp/resume-tool-autofill-smoke.png", fullPage: true });
  console.log(JSON.stringify({ extensionId, values }));
} finally {
  await context.close();
  fs.rmSync(profileDirectory, { recursive: true, force: true });
}

const DEFAULT_SERVER = "http://127.0.0.1:5001";
const LOCAL_SERVER_CANDIDATES = [
  DEFAULT_SERVER,
  "http://127.0.0.1:5002",
  "http://localhost:5001",
  "http://localhost:5002",
];

let activeServerUrl = "";
const AUTOFILL_SCRIPTS = ["autofill-config.js", "autofill-matcher.js", "autofill-content.js"];
const ATS_HOST_SUFFIXES = [
  "lever.co", "greenhouse.io", "workday.com", "myworkdayjobs.com", "myworkdaysite.com",
  "linkedin.com", "ashbyhq.com", "ashby.com", "icims.com", "taleo.net", "oraclecloud.com",
  "smartrecruiters.com", "jobvite.com", "avature.net", "successfactors.com", "phenompeople.com",
  "phenom.com", "careers.google.com", "google.com",
];
const autofillProfileCache = new Map();
const autofillProfileRequests = new Map();
const applicationScanTimers = new Map();

async function configuredServerUrl() {
  const stored = await chrome.storage.local.get("resumeServerUrl");
  return String(stored.resumeServerUrl || DEFAULT_SERVER).replace(/\/$/, "");
}

async function probeServer(base) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1400);
  try {
    const response = await fetch(`${base}/api/extension/status`, { signal: controller.signal });
    if (!response.ok) return false;
    const payload = await response.json().catch(() => null);
    return !!payload?.success;
  } catch (_) {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function serverUrl({ forceDiscovery = false } = {}) {
  if (activeServerUrl && !forceDiscovery) return activeServerUrl;
  const configured = await configuredServerUrl();
  const candidates = [...new Set([configured, ...LOCAL_SERVER_CANDIDATES])];
  for (const candidate of candidates) {
    if (await probeServer(candidate)) {
      activeServerUrl = candidate;
      if (candidate !== configured) {
        await chrome.storage.local.set({ resumeServerUrl: candidate });
      }
      return candidate;
    }
  }
  activeServerUrl = "";
  return configured;
}

async function configureExtension() {
  const stored = await chrome.storage.local.get("resumeServerUrl");
  if (!stored.resumeServerUrl) await chrome.storage.local.set({ resumeServerUrl: DEFAULT_SERVER });
  if (chrome.sidePanel?.setPanelBehavior) {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false }).catch(() => {});
  }
  const jobsTabs = await chrome.tabs.query({ url: "https://www.linkedin.com/jobs/*" });
  await Promise.all(jobsTabs.map((tab) => {
    if (!tab.id) return Promise.resolve();
    return chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content-script.js"] }).catch(() => {});
  }));
  const webTabs = await chrome.tabs.query({ url: ["http://*/*", "https://*/*"] });
  await Promise.all(webTabs.filter((tab) => isInspectableWebUrl(tab.url)).map((tab) => {
    if (!tab.id) return Promise.resolve();
    return chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["application-assistant.js"] }).catch(() => {});
  }));
  await Promise.all(webTabs.filter((tab) => !isLinkedInJobsUrl(tab.url)).map((tab) => {
    if (!tab.id) return Promise.resolve();
    return chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["panel-host.js"] }).catch(() => {});
  }));
  await Promise.all(webTabs.filter((tab) => isKnownAtsUrl(tab.url)).map((tab) => ensureAutofillRuntime(tab)));
}

configureExtension();
chrome.runtime.onInstalled.addListener(configureExtension);
chrome.runtime.onStartup.addListener(configureExtension);

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName === "local" && changes.resumeServerUrl) {
    activeServerUrl = "";
    autofillProfileCache.clear();
  }
});

function isLinkedInJobsUrl(url) {
  return String(url || "").startsWith("https://www.linkedin.com/jobs/");
}

function isKnownAtsUrl(url) {
  try {
    const host = new URL(String(url || "")).hostname.toLowerCase();
    return ATS_HOST_SUFFIXES.some((suffix) => host === suffix || host.endsWith(`.${suffix}`));
  } catch (_) {
    return false;
  }
}

function isInspectableWebUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    if (!["http:", "https:"].includes(parsed.protocol)) return false;
    return !["127.0.0.1", "localhost"].includes(parsed.hostname.toLowerCase());
  } catch (_) {
    return false;
  }
}

function applicationApprovalKey(tabId) {
  return `resumeAutofillApproval:${tabId}`;
}

function applicationScope(url) {
  const parsed = new URL(String(url || ""));
  const identifierKeys = [
    "currentJobId", "jobId", "job_id", "jobReqId", "requisitionId", "requisition_id",
    "gh_jid", "lever-origin", "postingId",
  ];
  for (const key of identifierKeys) {
    const value = parsed.searchParams.get(key);
    if (value) return `${parsed.origin}|${key}:${value}`;
  }
  const pathname = parsed.pathname
    .replace(/\/+/g, "/")
    .replace(/\/(apply|application)(?:\/.*)?$/i, "/$1")
    .replace(/\/$/, "");
  return `${parsed.origin}${pathname}`;
}

async function applicationApproval(tab) {
  if (!tab?.id || !isInspectableWebUrl(tab.url)) return null;
  const key = applicationApprovalKey(tab.id);
  const stored = await chrome.storage.session.get(key);
  const approval = stored[key];
  if (!approval) return null;
  const origin = new URL(tab.url).origin;
  const scope = applicationScope(tab.url);
  if (
    approval.origin !== origin
    || approval.scope !== scope
    || Number(approval.expiresAt || 0) <= Date.now()
  ) {
    await chrome.storage.session.remove(key);
    return null;
  }
  return approval;
}

async function setApplicationApproval(tab, identityId = "") {
  const key = applicationApprovalKey(tab.id);
  const approval = {
    mode: "application",
    origin: new URL(tab.url).origin,
    scope: applicationScope(tab.url),
    identityId: String(identityId || ""),
    approvedAt: Date.now(),
    expiresAt: Date.now() + 2 * 60 * 60 * 1000,
  };
  await chrome.storage.session.set({ [key]: approval });
  return approval;
}

async function clearApplicationApproval(tabId) {
  if (tabId) await chrome.storage.session.remove(applicationApprovalKey(tabId));
}

async function ensureAutofillRuntime(tab, { allowGeneric = false } = {}) {
  if (!tab?.id || !isInspectableWebUrl(tab.url)) return false;
  if (!allowGeneric && !isKnownAtsUrl(tab.url)) return false;
  if (allowGeneric) {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      files: AUTOFILL_SCRIPTS,
    }).catch(() => {});
    return true;
  }
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "AUTOFILL_SCAN_FRAME" }, { frameId: 0 });
  } catch (_) {
    await chrome.scripting.executeScript({ target: { tabId: tab.id, allFrames: true }, files: AUTOFILL_SCRIPTS }).catch(() => {});
  }
  return true;
}

async function activeWebTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab || null;
}

async function sendToAutofillFrames(tab, message, { allowGeneric = true } = {}) {
  if (!tab?.id || !isInspectableWebUrl(tab.url)) return [];
  if (!allowGeneric && !isKnownAtsUrl(tab.url)) return [];
  await ensureAutofillRuntime(tab, { allowGeneric });
  const frames = await chrome.webNavigation.getAllFrames({ tabId: tab.id }).catch(() => [{ frameId: 0 }]);
  const responses = await Promise.all((frames || [{ frameId: 0 }]).map(async (frame) => {
    try {
      return await chrome.tabs.sendMessage(tab.id, message, { frameId: frame.frameId });
    } catch (_) {
      return null;
    }
  }));
  return responses.filter(Boolean);
}

function aggregateAutofillStatus(tab, responses, { genericInspection = false } = {}) {
  const statuses = responses.filter((item) => item && typeof item.totalFields === "number");
  const fields = statuses.flatMap((item) => item.fields || []);
  const questionMap = new Map();
  fields.filter((field) => field.applicationQuestion && !field.filled).forEach((field) => {
    const key = field.questionId || `${field.frameUrl || ""}|${field.name || ""}|${field.label || ""}`;
    if (!questionMap.has(key)) questionMap.set(key, field);
  });
  return {
    success: true,
    supported: Boolean(tab && (isKnownAtsUrl(tab.url) || genericInspection && isInspectableWebUrl(tab.url))),
    pageUrl: tab?.url || "",
    pageTitle: tab?.title || "",
    platform: statuses.find((item) => item.platform && item.platform !== "generic")?.platform || statuses[0]?.platform || "",
    applicationPage: statuses.some((item) => item.applicationPage),
    totalFields: statuses.reduce((sum, item) => sum + item.totalFields, 0),
    filledFields: statuses.reduce((sum, item) => sum + item.filledFields, 0),
    matchedFields: statuses.reduce((sum, item) => sum + item.matchedFields, 0),
    fileFields: statuses.reduce((sum, item) => sum + item.fileFields, 0),
    continueEnabled: statuses.some((item) => item.continueEnabled !== false),
    fields,
    questions: Array.from(questionMap.values()),
  };
}

async function refreshAutofillStatusForTab(
  tab,
  {
    identityId = "",
    genericInspection = true,
    notifyPage = true,
  } = {},
) {
  if (!tab?.id || !isInspectableWebUrl(tab.url)) {
    return aggregateAutofillStatus(tab, [], { genericInspection: false });
  }
  const responses = await sendToAutofillFrames(
    tab,
    { type: "AUTOFILL_SCAN_FRAME", identityId },
    { allowGeneric: genericInspection },
  );
  const status = aggregateAutofillStatus(tab, responses, { genericInspection });
  if (notifyPage) {
    chrome.tabs.sendMessage(tab.id, { type: "AUTOFILL_PAGE_STATUS", status }).catch(() => {});
  }
  if (tab.active) {
    chrome.runtime.sendMessage({ type: "AUTOFILL_ACTIVE_STATUS_CHANGED", tabId: tab.id, status }).catch(() => {});
  }
  return status;
}

function scheduleApplicationScan(tabId, delay = 450) {
  clearTimeout(applicationScanTimers.get(tabId));
  applicationScanTimers.set(tabId, setTimeout(async () => {
    applicationScanTimers.delete(tabId);
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab || !isInspectableWebUrl(tab.url)) return;
    await refreshAutofillStatusForTab(tab).catch(() => {});
  }, delay));
}

async function getAutofillProfile(identityId = "") {
  const key = String(identityId || "");
  const cached = autofillProfileCache.get(key);
  if (cached && Date.now() - cached.at < 30000) return cached.value;
  if (autofillProfileRequests.has(key)) return autofillProfileRequests.get(key);
  const query = key ? `?identity_id=${encodeURIComponent(key)}` : "";
  const request = apiRequest({ path: `/api/extension/autofill-profile${query}` })
    .then((payload) => {
      autofillProfileCache.set(key, { at: Date.now(), value: payload });
      return payload;
    })
    .finally(() => autofillProfileRequests.delete(key));
  autofillProfileRequests.set(key, request);
  return request;
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
  }
  return btoa(binary);
}

async function resumeFileForDraft(draftId) {
  const draftResult = await apiRequest({ path: `/api/extension/drafts/${encodeURIComponent(draftId)}` });
  const draft = draftResult.draft;
  if (!draft?.pdf_path || draft.pdf_stale || draft.status !== "pdf_ready" || Number(draft.pdf_revision || 0) !== Number(draft.resume_revision || 1)) throw new Error("Generate the latest PDF before attaching it.");
  const base = await serverUrl();
  const response = await fetch(`${base}/api/download?path=${encodeURIComponent(draft.pdf_path)}&preview=true`);
  if (!response.ok) throw new Error("The generated resume file is unavailable.");
  return {
    base64: arrayBufferToBase64(await response.arrayBuffer()),
    filename: String(draft.pdf_path).split(/[\\/]/).pop() || "resume.pdf",
    mimeType: response.headers.get("content-type") || "application/pdf",
  };
}

function currentRecentPdfDrafts(drafts) {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  return (drafts || [])
    .filter((draft) => {
      const generatedAt = new Date(draft?.pdf_generated_at || "").getTime();
      return Boolean(
        draft?.pdf_path
        && !draft.pdf_stale
        && Number(draft.pdf_revision || 0) === Number(draft.resume_revision || 1)
        && Number.isFinite(generatedAt)
        && generatedAt >= cutoff
      );
    })
    .sort((left, right) => (
      new Date(right.pdf_generated_at || "").getTime()
      - new Date(left.pdf_generated_at || "").getTime()
    ));
}

async function recentPdfDrafts() {
  const payload = await apiRequest({ path: "/api/extension/drafts?limit=50" });
  return currentRecentPdfDrafts(payload.drafts);
}

async function latestRecentPdfDraft() {
  return (await recentPdfDrafts())[0] || null;
}

function resumeDraftOption(draft) {
  return {
    id: draft.id,
    company_name: draft.company_name || "",
    role_title: draft.role_title || "",
    pdf_generated_at: draft.pdf_generated_at || "",
    filename: String(draft.pdf_path || "").split(/[\\/]/).pop() || "resume.pdf",
    resume_revision: draft.resume_revision,
  };
}

async function attachResumeForDraft(tab, selectedDraft) {
  if (!selectedDraft) {
    throw new Error("Generate a new PDF in the Resume tab before attaching it.");
  }
  const file = await resumeFileForDraft(selectedDraft.id);
  const responses = await sendToAutofillFrames(tab, {
    type: "AUTOFILL_ATTACH_FRAME",
    ...file,
  });
  const attached = responses.find((item) => item.success);
  if (!attached) {
    throw new Error(
      responses.find((item) => item.error)?.error
      || "No compatible resume upload field was found.",
    );
  }
  const status = await refreshAutofillStatusForTab(tab);
  return {
    ...attached,
    status,
    draft: resumeDraftOption(selectedDraft),
  };
}

async function answerApplicationQuestion(message) {
  const question = String(message.question || "").replace(/\s+/g, " ").trim();
  const questionId = String(message.questionId || "").trim();
  if (!question || !questionId) throw new Error("Select an application question first.");

  const draftPayload = await apiRequest({ path: "/api/extension/drafts?limit=50" });
  const availableDrafts = currentRecentPdfDrafts(draftPayload.drafts);
  const requestedDraftId = String(message.draftId || "").trim();
  const selectedDraft = requestedDraftId
    ? availableDrafts.find((draft) => draft.id === requestedDraftId)
    : availableDrafts[0];
  if (!selectedDraft) {
    throw new Error(
      requestedDraftId
        ? "The selected resume is no longer current. Choose another PDF generated in the last 24 hours."
        : "Generate a new PDF before asking AI. Answers use PDFs from the last 24 hours.",
    );
  }

  const response = await apiRequest({
    path: `/api/extension/drafts/${encodeURIComponent(selectedDraft.id)}/application-answer`,
    method: "POST",
    body: {
      question,
      max_characters: Math.max(0, Number(message.maxLength || 0)),
    },
  });
  const answer = String(response.answer?.answer || "").trim();
  if (!answer) throw new Error("The AI returned an empty answer.");

  const storageKey = `resumeAutofillAnswers:${selectedDraft.id}`;
  const stored = await chrome.storage.local.get(storageKey);
  const existing = stored[storageKey] && typeof stored[storageKey] === "object"
    ? stored[storageKey]
    : {};
  const saved = {
    answer,
    resume_revision: selectedDraft.resume_revision,
    created_at: new Date().toISOString(),
  };
  await chrome.storage.local.set({
    [storageKey]: { ...existing, [questionId]: saved },
  });
  return {
    success: true,
    answer,
    questionId,
    draft: {
      id: selectedDraft.id,
      company_name: selectedDraft.company_name || "",
      role_title: selectedDraft.role_title || "",
      resume_revision: selectedDraft.resume_revision,
    },
  };
}

async function ensureJobReader(tab) {
  if (!tab?.id || !isLinkedInJobsUrl(tab.url)) return;
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "READ_JOB_CONTEXT" });
  } catch (_) {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content-script.js"] });
  }
}

async function activeLinkedInTab() {
  const tabs = await chrome.tabs.query({ url: "https://www.linkedin.com/jobs/*" });
  return tabs.find((tab) => tab.active) || tabs.sort((left, right) => (right.lastAccessed || 0) - (left.lastAccessed || 0))[0] || null;
}

async function contextForTab(tabId) {
  if (!tabId) return null;
  const key = `linkedinJobContext:${tabId}`;
  const stored = await chrome.storage.session.get(key);
  return stored[key] || null;
}

async function apiRequest(message) {
  const base = await serverUrl();
  const request = async (serverBase) => {
    const response = await fetch(`${serverBase}${message.path}`, {
      method: message.method || "GET",
      headers: message.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: message.body === undefined ? undefined : JSON.stringify(message.body),
    });
    const payload = await response.json().catch(() => ({ success: false, error: `Server returned ${response.status}` }));
    return { response, payload };
  };

  let result;
  try {
    result = await request(base);
  } catch (_) {
    const discovered = await serverUrl({ forceDiscovery: true });
    result = await request(discovered);
  }
  if (result.response.status === 404) {
    const discovered = await serverUrl({ forceDiscovery: true });
    if (discovered !== base) result = await request(discovered);
  }
  if (!result.response.ok) throw new Error(result.payload.error || `Request failed (${result.response.status})`);
  return result.payload;
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "JOB_CONTEXT") {
    const tabId = sender.tab?.id;
    if (!tabId) return false;
    const key = `linkedinJobContext:${tabId}`;
    chrome.storage.session.set({ [key]: message.context }).then(() => {
      chrome.action.setBadgeBackgroundColor({ color: "#0f9f78", tabId }).catch(() => {});
      chrome.action.setBadgeText({ text: "JOB", tabId }).catch(() => {});
      chrome.runtime.sendMessage({ type: "JOB_CONTEXT_CHANGED", tabId, context: message.context }).catch(() => {});
      sendResponse({ success: true });
    });
    return true;
  }

  if (message?.type === "GET_ACTIVE_CONTEXT") {
    activeLinkedInTab()
      .then(async (tab) => {
        await ensureJobReader(tab).catch(() => {});
        if (message.forceRefresh && tab) {
          await new Promise((resolve) => setTimeout(resolve, 700));
        }
        return { tab, context: tab ? await contextForTab(tab.id) : null };
      })
      .then(sendResponse)
      .catch((error) => sendResponse({ error: error.message }));
    return true;
  }

  if (message?.type === "API_REQUEST") {
    apiRequest(message)
      .then((payload) => {
        if (String(message.path || "").includes("/autofill-profile") && message.method && message.method !== "GET") {
          autofillProfileCache.clear();
        }
        sendResponse(payload);
      })
      .catch((error) => sendResponse({ success: false, error: error.message, connectionError: true }));
    return true;
  }

  if (message?.type === "AUTOFILL_GET_PROFILE") {
    getAutofillProfile(message.identityId)
      .then((payload) => sendResponse({ success: true, profile: payload.profile, application: payload.application }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_GET_ACTIVE_STATUS") {
    activeWebTab()
      .then((tab) => refreshAutofillStatusForTab(tab, {
        identityId: message.identityId || "",
        genericInspection: Boolean(message.inspectGeneric),
      }))
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_FILL_ACTIVE") {
    activeWebTab()
      .then(async (tab) => {
        const responses = await sendToAutofillFrames(tab, {
          type: "AUTOFILL_FILL_FRAME",
          identityId: message.identityId || "",
          approved: true,
          safeOnly: true,
        });
        const filledCount = responses.reduce((sum, item) => sum + Number(item.filledCount || 0), 0);
        const skippedCount = responses.reduce((sum, item) => sum + Number(item.skippedCount || 0), 0);
        const errors = responses.flatMap((item) => item.errors || []);
        const status = await refreshAutofillStatusForTab(tab, { identityId: message.identityId || "" });
        return { success: filledCount > 0, filledCount, skippedCount, errors, status };
      })
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_ATTACH_RESUME") {
    const requestedDraftId = String(message.draftId || "").trim();
    const requestedTab = sender.tab?.id && isInspectableWebUrl(sender.tab.url)
      ? Promise.resolve(sender.tab)
      : activeWebTab();
    Promise.all([requestedTab, recentPdfDrafts()])
      .then(([tab, drafts]) => {
        const selectedDraft = drafts.find((draft) => draft.id === requestedDraftId);
        if (!selectedDraft) {
          throw new Error("The selected resume is no longer current. Choose another PDF generated in the last 24 hours.");
        }
        return attachResumeForDraft(tab, selectedDraft);
      })
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_GET_RECENT_RESUMES") {
    recentPdfDrafts()
      .then((drafts) => sendResponse({
        success: true,
        drafts: drafts.map(resumeDraftOption),
      }))
      .catch((error) => sendResponse({ success: false, error: error.message, drafts: [] }));
    return true;
  }

  if (message?.type === "AUTOFILL_ATTACH_CURRENT_RESUME") {
    const tab = sender.tab;
    if (!tab?.id || !isInspectableWebUrl(tab.url)) {
      sendResponse({ success: false, error: "Open a job application page first." });
      return false;
    }
    latestRecentPdfDraft()
      .then((draft) => attachResumeForDraft(tab, draft))
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_ANSWER_QUESTION") {
    answerApplicationQuestion(message)
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_STATUS_CHANGED") {
    if (sender.tab?.id) scheduleApplicationScan(sender.tab.id);
    sendResponse({ success: true });
    return false;
  }

  if (message?.type === "AUTOFILL_APPLICATION_CANDIDATE") {
    const tab = sender.tab;
    if (!tab?.id || !isInspectableWebUrl(tab.url)) {
      sendResponse({ success: false, error: "This page cannot be inspected." });
      return false;
    }
    refreshAutofillStatusForTab(tab)
      .then((status) => sendResponse({ success: true, status }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_APPLICATION_GONE") {
    const tabId = sender.tab?.id;
    clearApplicationApproval(tabId)
      .then(() => sendResponse({ success: true }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_GET_APPROVAL") {
    applicationApproval(sender.tab)
      .then((approval) => sendResponse({ success: true, approval }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_CONFIRM_FILL") {
    const tab = sender.tab;
    if (!tab?.id || !isInspectableWebUrl(tab.url)) {
      sendResponse({ success: false, error: "Open a job application page first." });
      return false;
    }
    (async () => {
      const statusBefore = await refreshAutofillStatusForTab(tab);
      if (!statusBefore.applicationPage) throw new Error("No job application form was detected on this page.");
      const identityId = String(message.identityId || "");
      if (message.mode === "application" && statusBefore.continueEnabled !== false) {
        await setApplicationApproval(tab, identityId);
      } else {
        await clearApplicationApproval(tab.id);
      }
      const responses = await sendToAutofillFrames(tab, {
        type: "AUTOFILL_FILL_FRAME",
        identityId,
        approved: true,
        safeOnly: true,
      });
      const filledCount = responses.reduce((sum, item) => sum + Number(item.filledCount || 0), 0);
      const skippedCount = responses.reduce((sum, item) => sum + Number(item.skippedCount || 0), 0);
      const errors = responses.flatMap((item) => item.errors || []);
      const status = await refreshAutofillStatusForTab(tab, { identityId });
      chrome.tabs.sendMessage(tab.id, { type: "AUTOFILL_APPROVAL_CHANGED" }).catch(() => {});
      return { success: filledCount > 0, filledCount, skippedCount, errors, status };
    })()
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "GET_SERVER_URL") {
    serverUrl().then((url) => sendResponse({ url })).catch((error) => sendResponse({ url: DEFAULT_SERVER, error: error.message }));
    return true;
  }

  if (message?.type === "OPEN_EDITOR") {
    const reviewQuery = message.review ? "&review=1" : "";
    serverUrl().then((base) => chrome.tabs.create({
      url: `${base}/?draft=${encodeURIComponent(message.draftId)}${reviewQuery}`,
    }));
    sendResponse({ success: true });
    return true;
  }

  if (message?.type === "OPEN_APP") {
    serverUrl().then((base) => chrome.tabs.create({ url: base }));
    sendResponse({ success: true });
    return true;
  }

  if (message?.type === "OPEN_LINKEDIN_JOB") {
    const jobUrl = String(message.url || "");
    if (!/^https:\/\/(www\.)?linkedin\.com\/jobs\/view\/\d+\/?(?:[?#].*)?$/i.test(jobUrl)) {
      sendResponse({ success: false, error: "This draft does not have a valid LinkedIn job URL." });
      return false;
    }
    chrome.tabs.create({ url: jobUrl, active: false })
      .then(() => sendResponse({ success: true }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "OPEN_LINKEDIN_SEARCH") {
    const searchUrl = String(message.url || "");
    if (!/^https:\/\/(www\.)?linkedin\.com\/search\/results\/(people|content)\/?(?:[?#].*)?$/i.test(searchUrl)) {
      sendResponse({ success: false, error: "This is not a valid LinkedIn people or post search URL." });
      return false;
    }
    chrome.tabs.create({ url: searchUrl, active: true })
      .then(() => sendResponse({ success: true }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  return false;
});

chrome.webNavigation.onHistoryStateUpdated.addListener((details) => {
  if (details.frameId !== 0) return;
  if (details.url.startsWith("https://www.linkedin.com/jobs/")) {
    chrome.tabs.sendMessage(details.tabId, { type: "READ_JOB_CONTEXT" }).catch(() => {});
  }
  chrome.tabs.sendMessage(details.tabId, { type: "AUTOFILL_NAVIGATION_CHANGED", url: details.url }).catch(() => {});
});

chrome.webNavigation.onReferenceFragmentUpdated.addListener((details) => {
  if (details.frameId !== 0) return;
  chrome.tabs.sendMessage(details.tabId, { type: "AUTOFILL_NAVIGATION_CHANGED", url: details.url }).catch(() => {});
});

chrome.tabs.onActivated.addListener(({ tabId }) => {
  chrome.tabs.sendMessage(tabId, { type: "READ_JOB_CONTEXT" }).catch(() => {});
  chrome.tabs.sendMessage(tabId, { type: "AUTOFILL_NAVIGATION_CHANGED" }).catch(() => {});
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (!changeInfo.url && changeInfo.status !== "complete") return;
  chrome.tabs.sendMessage(tabId, { type: "AUTOFILL_NAVIGATION_CHANGED", url: changeInfo.url || "" }).catch(() => {});
});

chrome.tabs.onRemoved.addListener((tabId) => {
  clearTimeout(applicationScanTimers.get(tabId));
  applicationScanTimers.delete(tabId);
  clearApplicationApproval(tabId).catch(() => {});
});

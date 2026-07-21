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
  await Promise.all(webTabs.filter((tab) => !isLinkedInJobsUrl(tab.url)).map((tab) => {
    if (!tab.id) return Promise.resolve();
    return chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["panel-host.js"] }).catch(() => {});
  }));
  await Promise.all(webTabs.filter((tab) => isAtsUrl(tab.url)).map((tab) => ensureAtsRuntime(tab)));
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

function isAtsUrl(url) {
  try {
    const host = new URL(String(url || "")).hostname.toLowerCase();
    return ATS_HOST_SUFFIXES.some((suffix) => host === suffix || host.endsWith(`.${suffix}`));
  } catch (_) {
    return false;
  }
}

async function ensureAtsRuntime(tab) {
  if (!tab?.id || !isAtsUrl(tab.url)) return false;
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

async function sendToAtsFrames(tab, message) {
  if (!tab?.id || !isAtsUrl(tab.url)) return [];
  await ensureAtsRuntime(tab);
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

function aggregateAutofillStatus(tab, responses) {
  const statuses = responses.filter((item) => item && typeof item.totalFields === "number");
  const fields = statuses.flatMap((item) => item.fields || []);
  const questionMap = new Map();
  fields.filter((field) => field.applicationQuestion && !field.filled).forEach((field) => {
    const key = field.questionId || `${field.frameUrl || ""}|${field.name || ""}|${field.label || ""}`;
    if (!questionMap.has(key)) questionMap.set(key, field);
  });
  return {
    success: true,
    supported: Boolean(tab && isAtsUrl(tab.url)),
    pageUrl: tab?.url || "",
    pageTitle: tab?.title || "",
    platform: statuses.find((item) => item.platform && item.platform !== "generic")?.platform || statuses[0]?.platform || "",
    applicationPage: statuses.some((item) => item.applicationPage),
    totalFields: statuses.reduce((sum, item) => sum + item.totalFields, 0),
    filledFields: statuses.reduce((sum, item) => sum + item.filledFields, 0),
    matchedFields: statuses.reduce((sum, item) => sum + item.matchedFields, 0),
    fileFields: statuses.reduce((sum, item) => sum + item.fileFields, 0),
    fields,
    questions: Array.from(questionMap.values()),
  };
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
      .then(async (tab) => aggregateAutofillStatus(tab, await sendToAtsFrames(tab, { type: "AUTOFILL_SCAN_FRAME", identityId: message.identityId || "" })))
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_FILL_ACTIVE") {
    activeWebTab()
      .then(async (tab) => {
        const responses = await sendToAtsFrames(tab, { type: "AUTOFILL_FILL_FRAME", identityId: message.identityId || "" });
        const filledCount = responses.reduce((sum, item) => sum + Number(item.filledCount || 0), 0);
        const skippedCount = responses.reduce((sum, item) => sum + Number(item.skippedCount || 0), 0);
        const errors = responses.flatMap((item) => item.errors || []);
        const statusResponses = await sendToAtsFrames(tab, { type: "AUTOFILL_SCAN_FRAME", identityId: message.identityId || "" });
        return { success: filledCount > 0, filledCount, skippedCount, errors, status: aggregateAutofillStatus(tab, statusResponses) };
      })
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_ATTACH_RESUME") {
    Promise.all([activeWebTab(), resumeFileForDraft(message.draftId)])
      .then(async ([tab, file]) => {
        const responses = await sendToAtsFrames(tab, { type: "AUTOFILL_ATTACH_FRAME", ...file });
        const attached = responses.find((item) => item.success);
        if (!attached) throw new Error(responses.find((item) => item.error)?.error || "No compatible resume upload field was found.");
        return attached;
      })
      .then(sendResponse)
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (message?.type === "AUTOFILL_STATUS_CHANGED") {
    chrome.runtime.sendMessage({ type: "AUTOFILL_ACTIVE_STATUS_CHANGED", tabId: sender.tab?.id, status: message.status }).catch(() => {});
    sendResponse({ success: true });
    return false;
  }

  if (message?.type === "GET_SERVER_URL") {
    serverUrl().then((url) => sendResponse({ url })).catch((error) => sendResponse({ url: DEFAULT_SERVER, error: error.message }));
    return true;
  }

  if (message?.type === "OPEN_EDITOR") {
    serverUrl().then((base) => chrome.tabs.create({ url: `${base}/?draft=${encodeURIComponent(message.draftId)}` }));
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
    chrome.tabs.create({ url: jobUrl, active: true })
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
  if (details.frameId !== 0 || !details.url.startsWith("https://www.linkedin.com/jobs/")) return;
  chrome.tabs.sendMessage(details.tabId, { type: "READ_JOB_CONTEXT" }).catch(() => {});
}, { url: [{ hostEquals: "www.linkedin.com", pathPrefix: "/jobs/" }] });

chrome.tabs.onActivated.addListener(({ tabId }) => {
  chrome.tabs.sendMessage(tabId, { type: "READ_JOB_CONTEXT" }).catch(() => {});
});

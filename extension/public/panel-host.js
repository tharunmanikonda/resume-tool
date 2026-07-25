(() => {
  let version = "development";
  let runtimeId = "";
  try {
    version = chrome.runtime.getManifest?.().version || version;
    runtimeId = chrome.runtime.id || "";
  } catch (_) {
    return;
  }
  const existingLifecycle = globalThis.__resumeGeneratorPanelHostLifecycle;
  if (
    existingLifecycle?.version === version
    && existingLifecycle?.runtimeId === runtimeId
    && existingLifecycle?.isActive?.()
  ) return;
  existingLifecycle?.shutdown?.();

  const panelHostId = "resume-generator-global-panel";
  const panelTriggerId = "resume-generator-global-trigger";
  const instanceId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  let stopped = false;

  function runtimeAvailable() {
    try {
      return !stopped && Boolean(chrome?.runtime?.id);
    } catch (_) {
      return false;
    }
  }

  function closePanel() {
    document.getElementById(panelHostId)?.remove();
  }

  function extensionUrl(path) {
    if (!runtimeAvailable()) return "";
    try {
      const value = chrome.runtime.getURL(path);
      if (!value || value.startsWith("chrome-extension://invalid")) return "";
      return value;
    } catch (_) {
      return "";
    }
  }

  function togglePanel() {
    const existing = document.getElementById(panelHostId);
    if (existing) {
      existing.remove();
      return false;
    }
    if (!runtimeAvailable()) return false;
    const panelUrl = extensionUrl("sidepanel.html");
    if (!panelUrl) return false;

    const host = document.createElement("div");
    host.id = panelHostId;
    host.dataset.resumeGeneratorInstance = instanceId;
    Object.assign(host.style, {
      position: "fixed",
      inset: "0 0 0 auto",
      width: "min(460px, 100vw)",
      height: "100vh",
      zIndex: "2147483647",
      background: "#fff",
      boxShadow: "-10px 0 32px rgba(0, 0, 0, 0.22)",
    });

    const close = document.createElement("button");
    close.type = "button";
    close.textContent = "Close";
    close.setAttribute("aria-label", "Close Resume Generator");
    Object.assign(close.style, {
      position: "absolute",
      top: "10px",
      right: "12px",
      zIndex: "2",
      border: "1px solid #bbb",
      borderRadius: "6px",
      background: "#fff",
      padding: "6px 10px",
      cursor: "pointer",
    });
    close.addEventListener("click", closePanel);

    const frame = document.createElement("iframe");
    frame.title = "Resume Generator";
    frame.src = panelUrl;
    frame.setAttribute("allow", "clipboard-write");
    Object.assign(frame.style, { width: "100%", height: "100%", border: "0", background: "#fff" });
    host.append(frame, close);
    document.documentElement.appendChild(host);
    return true;
  }

  function ensureTrigger() {
    const existing = document.getElementById(panelTriggerId);
    if (existing?.dataset.resumeGeneratorInstance === instanceId) return;
    existing?.remove();
    const stalePanel = document.getElementById(panelHostId);
    if (stalePanel?.dataset.resumeGeneratorInstance !== instanceId) stalePanel?.remove();
    const trigger = document.createElement("button");
    trigger.id = panelTriggerId;
    trigger.type = "button";
    trigger.textContent = "Resume";
    trigger.dataset.resumeGeneratorInstance = instanceId;
    trigger.setAttribute("aria-label", "Open Resume Generator");
    Object.assign(trigger.style, {
      all: "initial",
      position: "fixed",
      top: "48%",
      right: "0",
      zIndex: "2147483646",
      border: "1px solid #087f5b",
      borderRight: "0",
      borderRadius: "6px 0 0 6px",
      background: "#0ca678",
      color: "#fff",
      padding: "10px 9px",
      font: "600 13px/1 system-ui, sans-serif",
      cursor: "pointer",
      boxShadow: "0 3px 12px rgba(0, 0, 0, 0.18)",
    });
    trigger.addEventListener("click", togglePanel);
    document.documentElement.appendChild(trigger);
  }

  function handleMessage(message, _sender, sendResponse) {
    if (message?.type !== "TOGGLE_RESUME_PANEL") return;
    sendResponse({ success: true, opened: togglePanel() });
  }

  function shutdown() {
    stopped = true;
    try {
      chrome.runtime.onMessage.removeListener(handleMessage);
    } catch (_) {}
    closePanel();
    document.getElementById(panelTriggerId)?.remove();
  }

  globalThis.__resumeGeneratorPanelHostLifecycle = { version, runtimeId, instanceId, isActive: runtimeAvailable, shutdown };
  chrome.runtime.onMessage.addListener(handleMessage);
  ensureTrigger();
})();

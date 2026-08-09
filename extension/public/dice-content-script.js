(() => {
  let readerVersion = "development";
  let runtimeId = "";
  try {
    readerVersion = chrome.runtime.getManifest?.().version || readerVersion;
    runtimeId = chrome.runtime.id || "";
  } catch (_) {
    return;
  }

  const previousLifecycle = globalThis.__resumeGeneratorDiceLifecycle;
  if (
    previousLifecycle?.version === readerVersion
    && previousLifecycle?.runtimeId === runtimeId
    && previousLifecycle?.isActive?.()
  ) return;
  previousLifecycle?.shutdown?.();

  const panelHostId = "resume-generator-dice-panel";
  const panelTriggerId = "resume-generator-dice-trigger";
  const instanceId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  let lastFingerprint = "";
  let timer = null;
  let stopped = false;
  let observer = null;
  let contextWatchdog = null;
  let clearedForNonDetailPage = false;

  function cleanText(value) {
    return String(value || "")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t]+/g, " ")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function runtimeAvailable() {
    try {
      return !stopped && Boolean(chrome?.runtime?.id);
    } catch (_) {
      return false;
    }
  }

  function sendRuntimeMessage(message) {
    if (!runtimeAvailable()) return;
    try {
      const pending = chrome.runtime.sendMessage(message);
      pending?.catch?.(() => {});
    } catch (_) {
      shutdown();
    }
  }

  function extensionUrl(path) {
    if (!runtimeAvailable()) return "";
    try {
      const value = chrome.runtime.getURL(path);
      return value && !value.startsWith("chrome-extension://invalid") ? value : "";
    } catch (_) {
      return "";
    }
  }

  function panelContextInvalid() {
    const frame = document.querySelector(`#${panelHostId} iframe`);
    if (!frame) return false;
    return [frame.getAttribute("src"), frame.src]
      .filter(Boolean)
      .some((value) => String(value).startsWith("chrome-extension://invalid"));
  }

  function isVisible(element) {
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  }

  function stripHtml(value) {
    if (!value) return "";
    const holder = document.createElement("div");
    holder.innerHTML = String(value);
    return cleanText(holder.innerText || holder.textContent || "");
  }

  function diceJobId() {
    const pathId = location.pathname.match(/^\/job-detail\/([^/?#]+)/i)?.[1];
    if (pathId) return pathId;
    return cleanText(new URLSearchParams(location.search).get("selectedJobId"));
  }

  function jobPostingFrom(value) {
    if (!value || typeof value !== "object") return null;
    if (value["@type"] === "JobPosting") return value;
    if (value.mainEntity?.["@type"] === "JobPosting") return value.mainEntity;
    const graph = Array.isArray(value["@graph"]) ? value["@graph"] : [];
    return graph.find((item) => item?.["@type"] === "JobPosting") || null;
  }

  function structuredJob() {
    for (const node of document.querySelectorAll("script[type='application/ld+json']")) {
      try {
        const parsed = JSON.parse(node.textContent || "null");
        const values = Array.isArray(parsed) ? parsed : [parsed];
        for (const value of values) {
          const job = jobPostingFrom(value);
          if (job) return job;
        }
      } catch (_) {}
    }
    return null;
  }

  function locationFromStructured(job) {
    const locations = Array.isArray(job?.jobLocation) ? job.jobLocation : (job?.jobLocation ? [job.jobLocation] : []);
    const values = locations.map((item) => {
      const address = item?.address || {};
      return [address.addressLocality, address.addressRegion, address.addressCountry].filter(Boolean).join(", ");
    }).filter(Boolean);
    if (values.length) return values.join(" / ");
    return job?.jobLocationType === "TELECOMMUTE" ? "Remote" : "";
  }

  function visibleDetailHeading() {
    return [...document.querySelectorAll("aside h1, main h1")].find(isVisible) || null;
  }

  function detailRoot(titleElement) {
    return titleElement?.closest("aside, main") || null;
  }

  function visibleCompanyName(titleElement) {
    const root = detailRoot(titleElement);
    if (!root) return "";
    const links = [...root.querySelectorAll("a[href*='/company-profile/']")].filter(isVisible);
    const beforeTitle = links.find((link) => !titleElement || (link.compareDocumentPosition(titleElement) & Node.DOCUMENT_POSITION_FOLLOWING));
    return cleanText((beforeTitle || links[0])?.textContent);
  }

  function visibleLocation(titleElement) {
    if (!titleElement) return "";
    const title = cleanText(titleElement.textContent);
    const root = detailRoot(titleElement);
    let container = titleElement.parentElement;
    while (container && container !== root) {
      const lines = cleanText(container.innerText || container.textContent)
        .split("\n")
        .map(cleanText)
        .filter(Boolean);
      const titleIndex = lines.findIndex((line) => line === title);
      const candidates = titleIndex >= 0 ? lines.slice(titleIndex + 1, titleIndex + 8) : [];
      const locationLine = candidates.find((line) => /\b(remote|hybrid|on-site|onsite)\b|,\s*[A-Z]{2}(?:,|\b)|,\s*(?:United States|US)\b/i.test(line));
      if (locationLine) return cleanText(locationLine).split(/\s*[•|]\s*/)[0];
      container = container.parentElement;
    }
    return "";
  }

  function descriptionFromHeading(titleElement) {
    const root = detailRoot(titleElement);
    if (!root) return "";
    const headings = [...root.querySelectorAll("h2, h3, h4, [role='heading']")];
    const heading = headings.find((element) => /^(summary|job description|about the job)$/i.test(cleanText(element.textContent)));
    if (!heading) return "";
    const directContent = cleanText(heading.nextElementSibling?.innerText || heading.nextElementSibling?.textContent);
    if (directContent.length >= 120) return directContent;
    return "";
  }

  function metadataContext() {
    const rawTitle = cleanText(document.querySelector("meta[property='og:title']")?.content || document.title);
    const description = cleanText(document.querySelector("meta[property='og:description']")?.content);
    const parts = rawTitle.split(/\s+[|\-]\s+/).filter(Boolean).filter((part) => !/^dice/i.test(part));
    return { roleTitle: parts[0] || "", description };
  }

  function closePanel() {
    document.getElementById(panelHostId)?.remove();
  }

  function togglePanel() {
    const existing = document.getElementById(panelHostId);
    if (existing) {
      existing.remove();
      return false;
    }
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

  function ensurePanelTrigger() {
    const existing = document.getElementById(panelTriggerId);
    if (existing?.dataset.resumeGeneratorInstance === instanceId) return;
    existing?.remove();
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

  function readContext() {
    const externalJobId = diceJobId();
    if (!externalJobId) {
      if (!clearedForNonDetailPage) sendRuntimeMessage({ type: "JOB_CONTEXT_CLEARED" });
      clearedForNonDetailPage = true;
      lastFingerprint = "";
      return;
    }
    clearedForNonDetailPage = false;
    const structured = structuredJob();
    const titleElement = visibleDetailHeading();
    const metadata = metadataContext();
    const roleTitle = cleanText(structured?.title || titleElement?.textContent || metadata.roleTitle);
    const companyName = cleanText(structured?.hiringOrganization?.name || visibleCompanyName(titleElement));
    const jobDescription = stripHtml(structured?.description) || descriptionFromHeading(titleElement) || metadata.description;
    const jobLocation = locationFromStructured(structured) || visibleLocation(titleElement);
    const completeFields = [companyName, roleTitle, jobDescription.length >= 120].filter(Boolean).length;
    const context = {
      source: "dice",
      external_job_id: externalJobId,
      url: `https://www.dice.com/job-detail/${externalJobId}`,
      company_name: companyName,
      role_title: roleTitle,
      location: jobLocation,
      job_description: jobDescription,
      extraction_confidence: completeFields === 3 ? "high" : (completeFields === 2 ? "medium" : "low"),
      source_metadata: {
        extracted_at: new Date().toISOString(),
        extraction_method: structured ? "dom_and_json_ld" : "dom",
        extractor_version: readerVersion,
        field_lengths: {
          company_name: companyName.length,
          role_title: roleTitle.length,
          job_description: jobDescription.length,
        },
      },
    };
    const fingerprint = [externalJobId, roleTitle, companyName, jobDescription.length, jobDescription.slice(0, 80), jobDescription.slice(-80)].join("|");
    if (fingerprint === lastFingerprint) return;
    lastFingerprint = fingerprint;
    sendRuntimeMessage({ type: "JOB_CONTEXT", context });
  }

  function scheduleRead() {
    if (!runtimeAvailable()) {
      shutdown();
      return;
    }
    clearTimeout(timer);
    timer = setTimeout(readContext, 450);
  }

  function handleRuntimeMessage(message, _sender, sendResponse) {
    if (message?.type === "READ_JOB_CONTEXT") scheduleRead();
    if (message?.type === "TOGGLE_RESUME_PANEL") {
      const opened = togglePanel();
      scheduleRead();
      sendResponse({ success: true, opened });
    }
  }

  function shutdown() {
    if (stopped) return;
    stopped = true;
    clearTimeout(timer);
    clearInterval(contextWatchdog);
    observer?.disconnect();
    window.removeEventListener("popstate", scheduleRead);
    try {
      chrome.runtime.onMessage.removeListener(handleRuntimeMessage);
    } catch (_) {}
    closePanel();
    document.getElementById(panelTriggerId)?.remove();
  }

  globalThis.__resumeGeneratorDiceLifecycle = {
    version: readerVersion,
    runtimeId,
    instanceId,
    isActive: runtimeAvailable,
    shutdown,
  };
  chrome.runtime.onMessage.addListener(handleRuntimeMessage);
  window.addEventListener("popstate", scheduleRead);
  observer = new MutationObserver(scheduleRead);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  ensurePanelTrigger();
  contextWatchdog = setInterval(() => {
    if (!runtimeAvailable() || panelContextInvalid()) shutdown();
  }, 1000);
  scheduleRead();
})();

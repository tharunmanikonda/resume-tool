(() => {
  let readerVersion = "development";
  let runtimeId = "";
  try {
    readerVersion = chrome.runtime.getManifest?.().version || readerVersion;
    runtimeId = chrome.runtime.id || "";
  } catch (_) {
    return;
  }

  const previousLifecycle = globalThis.__resumeGeneratorHiringCafeLifecycle;
  if (
    previousLifecycle?.version === readerVersion
    && previousLifecycle?.runtimeId === runtimeId
    && previousLifecycle?.isActive?.()
  ) return;
  previousLifecycle?.shutdown?.();

  const panelHostId = "resume-generator-hiringcafe-panel";
  const panelTriggerId = "resume-generator-hiringcafe-trigger";
  const instanceId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  let lastFingerprint = "";
  let timer = null;
  let stopped = false;
  let observer = null;
  let contextWatchdog = null;
  let clearedForNonDetailPage = false;
  let observedJobId = "";
  let pendingFingerprint = "";
  let lastDescription = "";
  let lastPublishedJobId = "";

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
    for (const node of holder.querySelectorAll("br")) node.replaceWith("\n");
    for (const node of holder.querySelectorAll("p, div, li, h1, h2, h3, h4, section, ul, ol")) node.append("\n");
    return cleanText(holder.innerText || holder.textContent || "");
  }

  function selectedJob() {
    const dialog = [...document.querySelectorAll("[role='dialog']")].find(isVisible);
    const fullView = dialog?.querySelector("a[href^='/job/']")?.getAttribute("href");
    const dialogSlug = fullView?.match(/^\/job\/([^/?#]+)/)?.[1];
    if (dialogSlug) return { id: dialogSlug.split("-").pop(), url: `${location.origin}/job/${dialogSlug}` };
    const pathSlug = location.pathname.match(/^\/job\/([^/?#]+)/i)?.[1];
    const queryId = new URLSearchParams(location.search).get("v");
    if (pathSlug) return { id: pathSlug.split("-").pop(), url: `${location.origin}/job/${pathSlug}` };
    if (queryId) return { id: queryId, url: `${location.origin}/?v=${encodeURIComponent(queryId)}` };
    return null;
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

  function detailContext() {
    // The permalink uses stable section IDs; classic search uses a dialog.
    const dialog = [...document.querySelectorAll("[role='dialog']")].find(isVisible);
    const root = dialog || document;
    const title = [...root.querySelectorAll("h1")].find(isVisible);
    const description = [...root.querySelectorAll("#job-description article, #job-description, [class*='prose']")].find(isVisible);
    const companyHeading = root.querySelector("#company-info h2");
    const companyName = cleanText(companyHeading?.textContent).replace(/^About\s+/i, "")
      || cleanText(dialog ? title?.nextElementSibling?.querySelector("span")?.textContent : title?.nextElementSibling?.textContent);
    const normalizedCompany = companyName.replace(/^@\s*/, "");
    const locationNode = dialog
      ? [...(title?.parentElement?.children || [])].find(node => node.matches("div") && node.querySelector(":scope > svg") && node.querySelector(":scope > span"))
      : title?.parentElement?.querySelector("div.mt-2");
    return {
      title: cleanText(title?.textContent),
      companyName: normalizedCompany,
      location: cleanText(locationNode?.textContent),
      description: description ? stripHtml(description.innerHTML).replace(/^Job description\s*/i, "") : "",
    };
  }

  function matchingStructuredJob(selected) {
    const job = structuredJob();
    if (!job) return null;
    const identifier = String(job.identifier?.value || "");
    let urlId = "";
    try {
      const slug = new URL(job.url, location.href).pathname.match(/^\/job\/([^/]+)/)?.[1];
      urlId = slug?.split("-").pop() || "";
    } catch (_) {}
    // Next.js can leave the previous page's JSON-LD in place during navigation.
    return identifier === selected.id || urlId === selected.id ? job : null;
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
    if (!runtimeAvailable()) return shutdown();
    const selected = selectedJob();
    if (!selected) {
      if (!clearedForNonDetailPage) sendRuntimeMessage({ type: "JOB_CONTEXT_CLEARED" });
      clearedForNonDetailPage = true;
      observedJobId = "";
      lastFingerprint = "";
      pendingFingerprint = "";
      return;
    }
    if (selected.id !== observedJobId) {
      sendRuntimeMessage({ type: "JOB_CONTEXT_CLEARED" });
      observedJobId = selected.id;
      lastFingerprint = "";
      pendingFingerprint = "";
    }
    clearedForNonDetailPage = false;
    const structured = matchingStructuredJob(selected);
    const detail = detailContext();
    const roleTitle = cleanText(structured?.title || detail.title);
    const companyName = cleanText(structured?.hiringOrganization?.name || detail.companyName);
    const jobDescription = stripHtml(structured?.description) || detail.description;
    const jobLocation = detail.location || locationFromStructured(structured);
    // Never publish a listing summary or pair a newly selected job with old content.
    if (!roleTitle || !companyName || jobDescription.length < 120
      || (!structured && selected.id !== lastPublishedJobId && jobDescription === lastDescription)) return;
    const fingerprint = JSON.stringify([selected.id, roleTitle, companyName, jobLocation, jobDescription]);
    if (fingerprint === lastFingerprint) return;
    if (fingerprint !== pendingFingerprint) {
      pendingFingerprint = fingerprint;
      clearTimeout(timer);
      timer = setTimeout(readContext, 450);
      return;
    }
    lastFingerprint = fingerprint;
    lastDescription = jobDescription;
    lastPublishedJobId = selected.id;
    sendRuntimeMessage({ type: "JOB_CONTEXT", context: {
      source: "hiringcafe",
      external_job_id: selected.id,
      url: selected.url,
      company_name: companyName,
      role_title: roleTitle,
      location: jobLocation,
      job_description: jobDescription,
      extraction_confidence: "high",
      source_metadata: {
        extracted_at: new Date().toISOString(),
        extraction_method: structured ? "dom_and_json_ld" : "dom",
        extractor_version: readerVersion,
        field_lengths: { company_name: companyName.length, role_title: roleTitle.length, job_description: jobDescription.length },
      },
    } });
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

  globalThis.__resumeGeneratorHiringCafeLifecycle = {
    version: readerVersion,
    runtimeId,
    instanceId,
    isActive: runtimeAvailable,
    shutdown,
  };
  chrome.runtime.onMessage.addListener(handleRuntimeMessage);
  window.addEventListener("popstate", scheduleRead);
  observer = new MutationObserver(scheduleRead);
  observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
  ensurePanelTrigger();
  contextWatchdog = setInterval(() => {
    if (!runtimeAvailable() || panelContextInvalid()) return shutdown();
    // Also catches URL-only pushState changes, without patching the site's history.
    const currentId = selectedJob()?.id || "";
    if (currentId !== observedJobId) scheduleRead();
  }, 1000);
  scheduleRead();
})();

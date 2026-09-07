(() => {
  let readerVersion = "development";
  let runtimeId = "";
  try {
    readerVersion = chrome.runtime.getManifest?.().version || readerVersion;
    runtimeId = chrome.runtime.id || "";
  } catch (_) {
    return;
  }

  const previousLifecycle = globalThis.__resumeGeneratorAtsLifecycle;
  if (
    previousLifecycle?.version === readerVersion
    && previousLifecycle?.runtimeId === runtimeId
    && previousLifecycle?.isActive?.()
  ) return;
  previousLifecycle?.shutdown?.();

  const panelHostId = "resume-generator-ats-panel";
  const panelTriggerId = "resume-generator-ats-trigger";
  const instanceId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  let lastFingerprint = "";
  let timer = null;
  let stopped = false;
  let observer = null;
  let contextWatchdog = null;

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

  function atsSource() {
    const host = location.hostname.toLowerCase();
    if (host.includes("greenhouse.io")) return "greenhouse";
    if (host.includes("lever.co")) return "lever";
    if (host.includes("ashbyhq.com") || host.includes("ashby.com")) return "ashby";
    if (host.includes("rippling.com")) return "rippling";
    return "ats";
  }

  function externalJobId(source) {
    const parsed = new URL(location.href);
    if (source === "greenhouse") {
      return parsed.searchParams.get("gh_jid")
        || parsed.pathname.match(/\/jobs\/(\d+)/i)?.[1]
        || parsed.pathname.match(/\/job_app\?for=([^/?#]+)/i)?.[1]
        || "";
    }
    if (source === "lever") {
      const parts = parsed.pathname.split("/").filter(Boolean);
      return parts.length >= 2 ? parts[parts.length - 1] : "";
    }
    if (source === "ashby") {
      return parsed.pathname.match(/\/([^/?#]+)$/)?.[1] || parsed.searchParams.get("jobId") || "";
    }
    if (source === "rippling") {
      return parsed.pathname.match(/\/jobs\/([^/?#]+)/i)?.[1] || parsed.pathname.match(/\/job\/([^/?#]+)/i)?.[1] || "";
    }
    return parsed.pathname.split("/").filter(Boolean).pop() || "";
  }

  function companyFromUrl(source) {
    const parts = location.pathname.split("/").filter(Boolean);
    if (source === "greenhouse") {
      const hostLabel = location.hostname.split(".")[0];
      if (["boards", "job-boards", "job"].includes(hostLabel)) return parts[0] || "";
      return parts[0] || hostLabel;
    }
    if (source === "lever") return parts[0] || "";
    if (source === "ashby") return parts[0] || "";
    if (source === "rippling") return parts[0] || location.hostname.split(".")[0];
    return "";
  }

  function metadataContext() {
    const title = cleanText(document.querySelector("meta[property='og:title']")?.content || document.title);
    const description = cleanText(document.querySelector("meta[property='og:description']")?.content || document.querySelector("meta[name='description']")?.content);
    const parts = title.split(/\s+[|\-–]\s+/).map(cleanText).filter(Boolean);
    return { title, roleTitle: parts[0] || "", companyName: parts[1] || "", description };
  }

  function textFrom(selectors, minLength = 1) {
    for (const selector of selectors) {
      for (const element of document.querySelectorAll(selector)) {
        if (!isVisible(element)) continue;
        const value = cleanText(element.innerText || element.textContent);
        if (value.length >= minLength) return value;
      }
    }
    return "";
  }

  function descriptionNearHeadings() {
    const headings = [...document.querySelectorAll("h1, h2, h3, h4, [role='heading']")];
    const heading = headings.find((element) => /^(about the role|about this role|about the job|job description|description|what you'?ll do|responsibilities)$/i.test(cleanText(element.textContent)));
    const section = heading?.closest("section, main, article, div");
    const value = cleanText(section?.innerText || section?.textContent);
    return value.length >= 120 ? value : "";
  }

  function descriptionFromPage() {
    const main = [...document.querySelectorAll("main, article, [role='main'], body")]
      .map((element) => cleanText(element.innerText || element.textContent))
      .filter((value) => value.length >= 120)
      .sort((left, right) => right.length - left.length)[0] || "";
    return main.length > 20000 ? main.slice(0, 20000) : main;
  }

  function titleFromDom() {
    return textFrom([
      "[data-testid='job-title']",
      "[data-qa='posting-name']",
      ".posting-headline h2",
      "main h1",
      "article h1",
      "h1",
    ], 3);
  }

  function companyFromDom() {
    const textValue = textFrom([
      "[data-testid='company-name']",
      "[data-qa='company-name']",
      ".posting-company",
      "a[href*='/company/']",
      "header a",
    ], 2);
    if (textValue) return textValue;
    const imageValue = [...document.querySelectorAll("header img[alt], main img[alt], img[alt]")]
      .map((image) => cleanText(image.getAttribute("alt")))
      .find((value) => value && !/logo|icon|avatar|image|photo/i.test(value) && value.length <= 80);
    return imageValue || "";
  }

  function locationFromDom() {
    return textFrom([
      "[data-testid='job-location']",
      "[data-qa='job-location']",
      ".posting-categories .location",
      ".location",
      "[class*='location']",
    ], 2);
  }

  function prettyCompany(value) {
    return cleanText(value)
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
  }

  function companyFromDescription(value) {
    const text = cleanText(value);
    const welcomeMatch = text.match(/\bWelcome to ([A-Z][A-Za-z0-9&.' -]{1,80})(?:\.|\s+We\b|\s+is\b|\s+believes?\b)/);
    if (welcomeMatch) return cleanText(welcomeMatch[1]);
    const aboutMatch = text.match(/\bAbout ([A-Z][A-Za-z0-9&.' -]{1,80})(?:\n|\.|:)/);
    return aboutMatch ? cleanText(aboutMatch[1]) : "";
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
    const source = atsSource();
    const structured = structuredJob();
    const metadata = metadataContext();
    const sourceCompany = companyFromUrl(source);
    const id = externalJobId(source) || `${sourceCompany}:${metadata.roleTitle || titleFromDom()}`;
    const roleTitle = cleanText(structured?.title || titleFromDom() || metadata.roleTitle);
    const jobDescription = stripHtml(structured?.description)
      || textFrom(["[data-testid='job-description']", "[data-qa='job-description']", ".posting-page", ".job-description", "[class*='description']"], 120)
      || descriptionNearHeadings()
      || metadata.description
      || descriptionFromPage();
    const companyName = cleanText(
      structured?.hiringOrganization?.name
      || companyFromDom()
      || metadata.companyName
      || companyFromDescription(jobDescription)
      || prettyCompany(sourceCompany)
    );
    const jobLocation = locationFromStructured(structured) || locationFromDom();

    if (!roleTitle && !jobDescription) {
      sendRuntimeMessage({ type: "JOB_CONTEXT_CLEARED" });
      lastFingerprint = "";
      return;
    }

    const completeFields = [companyName, roleTitle, jobDescription.length >= 120].filter(Boolean).length;
    const context = {
      source,
      external_job_id: id,
      url: location.href,
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
    const fingerprint = [source, id, roleTitle, companyName, jobDescription.length, jobDescription.slice(0, 80), jobDescription.slice(-80)].join("|");
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
    timer = setTimeout(readContext, 550);
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

  globalThis.__resumeGeneratorAtsLifecycle = {
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
  contextWatchdog = setInterval(scheduleRead, 3000);
  ensurePanelTrigger();
  scheduleRead();
})();

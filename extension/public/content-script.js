(() => {
  let readerVersion = "development";
  let runtimeId = "";
  try {
    readerVersion = chrome.runtime.getManifest?.().version || readerVersion;
    runtimeId = chrome.runtime.id || "";
  } catch (_) {
    return;
  }
  const previousLifecycle = globalThis.__resumeGeneratorLinkedInLifecycle;
  if (
    previousLifecycle?.version === readerVersion
    && previousLifecycle?.runtimeId === runtimeId
    && previousLifecycle?.isActive?.()
  ) return;
  previousLifecycle?.shutdown?.();

  const selectors = {
    title: [
      ".job-details-jobs-unified-top-card__job-title h1",
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      ".jobs-details__main-content h1",
      ".jobs-search__job-details--container h1",
      "[class*='job-details'] h1",
      "h1 a[href*='/jobs/view/']",
      "main h1"
    ],
    company: [
      ".job-details-jobs-unified-top-card__company-name a",
      ".job-details-jobs-unified-top-card__company-name",
      ".jobs-unified-top-card__company-name a",
      ".jobs-unified-top-card__company-name",
      ".jobs-search__job-details--container a[href*='/company/']",
      "[class*='job-details'] a[href*='/company/']"
    ],
    location: [
      ".job-details-jobs-unified-top-card__primary-description-container",
      ".job-details-jobs-unified-top-card__bullet",
      ".jobs-unified-top-card__bullet"
    ],
    description: [
      "#job-details",
      ".jobs-description__content",
      ".jobs-box__html-content",
      ".jobs-description-content__text",
      ".jobs-search__job-details--container [class*='description']",
      "[class*='job-details'] [class*='description']"
    ],
    posted: [
      ".job-details-jobs-unified-top-card__primary-description-container",
      ".jobs-unified-top-card__posted-date"
    ]
  };

  let lastFingerprint = "";
  let timer = null;
  let stopped = false;
  let observer = null;
  let contextWatchdog = null;
  const panelHostId = "resume-generator-linkedin-panel";
  const panelTriggerId = "resume-generator-linkedin-trigger";
  const instanceId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const lifecycle = { version: readerVersion, runtimeId, instanceId, isActive: null, shutdown: null };
  globalThis.__resumeGeneratorLinkedInReaderVersion = readerVersion;
  globalThis.__resumeGeneratorLinkedInLifecycle = lifecycle;

  function cleanText(value) {
    return String(value || "").replace(/\u00a0/g, " ").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
  }

  function isVisible(element) {
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
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
      stopped = true;
      clearTimeout(timer);
      observer?.disconnect();
    }
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

  function panelContextInvalid() {
    const frame = document.querySelector(`#${panelHostId} iframe`);
    if (!frame) return false;
    return [frame.getAttribute("src"), frame.src]
      .filter(Boolean)
      .some((value) => String(value).startsWith("chrome-extension://invalid"));
  }

  function textFrom(selectorsList, minimumLength = 1, preferTextContent = false) {
    for (const selector of selectorsList) {
      for (const element of document.querySelectorAll(selector)) {
        if (!isVisible(element)) continue;
        const rawValue = preferTextContent ? element.textContent : (element.innerText || element.textContent);
        const value = cleanText(rawValue).replace(/\s+/g, " ");
        if (value.length >= minimumLength) return value;
      }
    }
    return "";
  }

  function jobIdFromUrl() {
    const pathMatch = location.pathname.match(/\/jobs\/view\/(\d+)/);
    if (pathMatch) return pathMatch[1];
    return new URL(location.href).searchParams.get("currentJobId") || "";
  }

  function structuredJob() {
    for (const node of document.querySelectorAll("script[type='application/ld+json']")) {
      try {
        const parsed = JSON.parse(node.textContent || "null");
        const values = Array.isArray(parsed) ? parsed : [parsed];
        const job = values.find((item) => item && (item["@type"] === "JobPosting" || item.mainEntity?.["@type"] === "JobPosting"));
        if (job) return job["@type"] === "JobPosting" ? job : job.mainEntity;
      } catch (_) {}
    }
    return null;
  }

  function stripHtml(value) {
    if (!value) return "";
    const holder = document.createElement("div");
    holder.innerHTML = String(value);
    return String(holder.innerText || holder.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
  }

  function locationFromStructured(job) {
    const locations = Array.isArray(job?.jobLocation) ? job.jobLocation : (job?.jobLocation ? [job.jobLocation] : []);
    return locations.map((item) => {
      const address = item?.address || {};
      return [address.addressLocality, address.addressRegion, address.addressCountry].filter(Boolean).join(", ");
    }).filter(Boolean).join(" / ");
  }

  function selectedJobCard(externalJobId) {
    const escapedJobId = globalThis.CSS?.escape ? CSS.escape(externalJobId) : externalJobId.replace(/[^a-zA-Z0-9_-]/g, "");
    const exactSelectors = [
      externalJobId ? `[data-job-id='${escapedJobId}']` : "",
      externalJobId ? `[data-occludable-job-id='${escapedJobId}']` : "",
      externalJobId ? `a[href*='/jobs/view/${escapedJobId}']` : "",
      externalJobId ? `a[href*='currentJobId=${escapedJobId}']` : "",
    ].filter(Boolean);
    for (const selector of exactSelectors) {
      const found = [...document.querySelectorAll(selector)].find(isVisible);
      if (found) return found.closest("li, [data-job-id], [data-occludable-job-id], .job-card-container") || found.parentElement || found;
    }
    const activeSelectors = [
      ".jobs-search-results__list-item--active",
      ".jobs-search-results-list [aria-selected='true']",
      ".jobs-search-results-list [data-selected='true']",
      "[class*='jobs-search-results'] [aria-selected='true']",
    ];
    for (const selector of activeSelectors) {
      const found = [...document.querySelectorAll(selector)].find(isVisible);
      if (found) return found.closest("li, [data-job-id], [data-occludable-job-id], .job-card-container") || found;
    }
    return null;
  }

  function cardContext(externalJobId) {
    const card = selectedJobCard(externalJobId);
    if (!card) return {};
    const titleElement = card.querySelector("a[href*='/jobs/view/'], a[href*='currentJobId='], .job-card-list__title, [class*='job-card'][class*='title'], h3");
    const companyElement = card.querySelector(".job-card-container__primary-description, .artdeco-entity-lockup__subtitle, [class*='primary-description'], h4");
    const locationElement = card.querySelector(".job-card-container__metadata-item, .artdeco-entity-lockup__caption, [class*='metadata-item']");
    const lines = cleanText(card.innerText || card.textContent).split("\n").map(cleanText).filter(Boolean);
    const roleTitle = cleanText(titleElement?.innerText || titleElement?.textContent) || lines[0] || "";
    const titleIndex = lines.findIndex((line) => line === roleTitle || line.includes(roleTitle));
    const followingLines = titleIndex >= 0 ? lines.slice(titleIndex + 1) : lines.slice(1);
    const genericCompany = followingLines.find((line) => !/^(viewed|promoted|easy apply|actively reviewing|\d+ benefits?)/i.test(line) && line.length <= 100) || "";
    const genericLocation = followingLines.find((line) => /\b(remote|hybrid|on-site|onsite)\b|,\s*[A-Z]{2}\b|united states/i.test(line)) || "";
    return {
      roleTitle,
      companyName: cleanText(companyElement?.innerText || companyElement?.textContent) || genericCompany,
      jobLocation: cleanText(locationElement?.innerText || locationElement?.textContent) || genericLocation,
    };
  }

  function metadataContext() {
    const titleValue = cleanText(document.querySelector("meta[property='og:title']")?.content || document.title);
    const descriptionValue = cleanText(document.querySelector("meta[property='og:description']")?.content);
    const titleParts = titleValue.split(/\s+[|\-]\s+/).filter(Boolean);
    const linkedInIndex = titleParts.findIndex((part) => /linkedin/i.test(part));
    const usefulParts = linkedInIndex >= 0 ? titleParts.slice(0, linkedInIndex) : titleParts;
    return {
      roleTitle: usefulParts[0] || "",
      companyName: usefulParts.length > 1 ? usefulParts[1] : "",
      description: descriptionValue,
    };
  }

  function plausibleRoleTitle(value) {
    const title = cleanText(value);
    if (title.length < 3 || title.length > 140 || title.includes("\n")) return false;
    const linkedinUiHeading = /^(jobs?|determine your fit|how to stand out|determine your fit and how to stand out|show match details|tailor my resume|create cover letter|people you can reach out to|meet the hiring team|about the job|featured benefits|job details|premium)/i;
    const nonTitleMetadata = /^(remote|hybrid|on[ -]?site|full[ -]?time|part[ -]?time|contract|temporary|internship|volunteer|united states)$/i;
    const locationOnly = /^(?:[A-Za-z .'-]+,\s*[A-Z]{2}|[A-Za-z .'-]+,\s*(?:United States|USA))(?:\s*\([^)]*\))?$/i;
    return !linkedinUiHeading.test(title) && !nonTitleMetadata.test(title) && !locationOnly.test(title);
  }

  function descriptionNearHeading() {
    const headings = [...document.querySelectorAll("h1, h2, h3, h4, [role='heading'], span, p, div")];
    const heading = headings.find((element) => /^about the job$/i.test(cleanText(element.textContent)));
    if (!heading) return "";
    let node = heading.closest("section") || heading.parentElement;
    let sectionText = "";
    while (node && node !== document.body) {
      const candidate = cleanText(node.textContent);
      if (candidate.length >= 120 && candidate.length <= 60000) {
        sectionText = candidate;
        break;
      }
      node = node.parentElement;
    }
    if (sectionText.length >= 120) return sectionText.replace(/^about the job\s*/i, "").trim();
    let sibling = heading.nextElementSibling;
    let combined = "";
    while (sibling && combined.length < 20000) {
      combined += `\n${cleanText(sibling.innerText || sibling.textContent)}`;
      sibling = sibling.nextElementSibling;
    }
    return cleanText(combined);
  }

  function detailHeadingElement() {
    const excluded = /^(about the job|featured benefits|people you can reach out to|meet the hiring team|determine your fit|how to stand out|determine your fit and how to stand out|show match details|tailor my resume|create cover letter|jobs where|job search|premium)/i;
    const candidates = [...document.querySelectorAll("h1, h2, h3, [role='heading']")].filter((element) => {
      if (!isVisible(element)) return false;
      const rect = element.getBoundingClientRect();
      const value = cleanText(element.textContent);
      return rect.top > 70 && rect.top < 700 && rect.left > window.innerWidth * 0.3 && value.length >= 3 && value.length <= 140 && !excluded.test(value);
    });
    candidates.sort((left, right) => {
      const leftSize = Number.parseFloat(getComputedStyle(left).fontSize) || 0;
      const rightSize = Number.parseFloat(getComputedStyle(right).fontSize) || 0;
      return rightSize - leftSize || left.getBoundingClientRect().top - right.getBoundingClientRect().top;
    });
    return candidates[0] || null;
  }

  function detailContext() {
    const titleElement = detailHeadingElement();
    if (!titleElement) return {};
    const roleTitle = cleanText(titleElement.textContent);
    let node = titleElement.parentElement;
    let lines = [];
    while (node && node !== document.body) {
      lines = cleanText(node.innerText || node.textContent).split("\n").map(cleanText).filter(Boolean);
      if (lines.length >= 3) break;
      node = node.parentElement;
    }
    const titleIndex = lines.findIndex((line) => line === roleTitle || line.includes(roleTitle));
    const before = titleIndex > 0 ? lines.slice(Math.max(0, titleIndex - 4), titleIndex).reverse() : [];
    const after = titleIndex >= 0 ? lines.slice(titleIndex + 1, titleIndex + 6) : [];
    const companyName = before.find((line) => line.length <= 100 && !/^(premium|promoted|jobs?)$/i.test(line)) || "";
    const locationLine = after.find((line) => /\b(remote|hybrid|on-site|onsite)\b|,\s*[A-Z]{2}\b|united states/i.test(line)) || "";
    return { roleTitle, companyName, jobLocation: locationLine.split(/\s*[·|]\s*/)[0] };
  }

  function descriptionFromPageText() {
    const pageText = cleanText(document.body.innerText || document.body.textContent);
    const lowerText = pageText.toLowerCase();
    const start = lowerText.indexOf("about the job");
    if (start < 0) return "";
    const contentStart = start + "about the job".length;
    const endLabels = ["featured benefits", "about the company", "job alerts", "similar jobs"];
    const endings = endLabels.map((label) => lowerText.indexOf(label, contentStart + 120)).filter((index) => index > contentStart);
    const end = endings.length ? Math.min(...endings) : Math.min(pageText.length, contentStart + 30000);
    return cleanText(pageText.slice(contentStart, end));
  }

  function normalizeLocation(value) {
    return cleanText(value).split(/\s*[·|]\s*/)[0];
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
    close.addEventListener("click", () => host.remove());
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
    const stalePanel = document.getElementById(panelHostId);
    if (stalePanel?.dataset.resumeGeneratorInstance !== instanceId) stalePanel?.remove();
    const trigger = document.createElement("button");
    trigger.id = panelTriggerId;
    trigger.type = "button";
    trigger.textContent = "Resume";
    trigger.dataset.resumeGeneratorVersion = readerVersion;
    trigger.dataset.resumeGeneratorInstance = instanceId;
    trigger.setAttribute("aria-label", "Open Resume Generator");
    Object.assign(trigger.style, {
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
    if (!location.pathname.startsWith("/jobs/")) return;
    const structured = structuredJob();
    const externalJobId = jobIdFromUrl() || String(structured?.identifier?.value || "");
    const card = cardContext(externalJobId);
    const detail = detailContext();
    const metadata = metadataContext();
    const roleCandidates = [
      { value: String(structured?.title || "").trim(), source: "structured_data" },
      { value: card.roleTitle, source: "selected_job_card" },
      { value: textFrom(selectors.title), source: "job_detail_selector" },
      { value: detail.roleTitle, source: "detail_heading" },
      { value: metadata.roleTitle, source: "page_metadata" },
    ];
    const selectedRole = roleCandidates.find((candidate) => plausibleRoleTitle(candidate.value)) || { value: "", source: "not_found" };
    const roleTitle = cleanText(selectedRole.value);
    const companyName = textFrom(selectors.company) || String(structured?.hiringOrganization?.name || "").trim() || detail.companyName || card.companyName || metadata.companyName;
    const jobDescription = textFrom(selectors.description, 120, true).replace(/\n{3,}/g, "\n\n").trim() || stripHtml(structured?.description) || descriptionNearHeading() || descriptionFromPageText() || metadata.description;
    const jobLocation = normalizeLocation(locationFromStructured(structured) || card.jobLocation || textFrom(selectors.location) || detail.jobLocation);
    const canonicalUrl = externalJobId ? `https://www.linkedin.com/jobs/view/${externalJobId}/` : location.href;
    const completeFields = [companyName, roleTitle, jobDescription.length >= 120].filter(Boolean).length;
    const context = {
      source: "linkedin",
      external_job_id: externalJobId,
      url: canonicalUrl,
      company_name: companyName,
      role_title: roleTitle,
      location: jobLocation,
      job_description: jobDescription,
      extraction_confidence: completeFields === 3 ? "high" : (completeFields === 2 ? "medium" : "low"),
      source_metadata: {
        posted_text: textFrom(selectors.posted),
        extracted_at: new Date().toISOString(),
        extraction_method: structured ? "dom_and_json_ld" : "dom",
        extractor_version: readerVersion,
        role_source: selectedRole.source,
        field_lengths: {
          company_name: companyName.length,
          role_title: roleTitle.length,
          job_description: jobDescription.length,
        }
      }
    };
    const fingerprint = [externalJobId, roleTitle, companyName, jobDescription.length, jobDescription.slice(0, 80), jobDescription.slice(-80)].join("|");
    if (fingerprint === lastFingerprint) return;
    lastFingerprint = fingerprint;
    sendRuntimeMessage({ type: "JOB_CONTEXT", context });
  }

  function scheduleRead() {
    if (!runtimeAvailable()) {
      stopped = true;
      clearTimeout(timer);
      observer?.disconnect();
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
    stopped = true;
    clearTimeout(timer);
    clearInterval(contextWatchdog);
    observer?.disconnect();
    window.removeEventListener("popstate", scheduleRead);
    try {
      chrome.runtime.onMessage.removeListener(handleRuntimeMessage);
    } catch (_) {}
    document.getElementById(panelHostId)?.remove();
    document.getElementById(panelTriggerId)?.remove();
  }

  lifecycle.shutdown = shutdown;
  lifecycle.isActive = runtimeAvailable;
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

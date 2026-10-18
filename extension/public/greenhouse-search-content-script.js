(() => {
  if (!location.hostname.toLowerCase().endsWith("greenhouse.io") || !location.pathname.startsWith("/jobs/search")) return;

  const cleanText = (value) => String(value || "").replace(/\u00a0/g, " ").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
  let lastFingerprint = "";

  function relativePostedAt(label) {
    const value = cleanText(label).toLowerCase();
    const match = value.match(/(\d+)\s+days?\s+ago/);
    const date = new Date();
    if (value.includes("today")) return date.toISOString();
    if (value.includes("yesterday")) date.setDate(date.getDate() - 1);
    else if (match) date.setDate(date.getDate() - Number(match[1]));
    else return "";
    return date.toISOString();
  }

  function firstText(element, selectors) {
    for (const selector of selectors) {
      const match = element.querySelector(selector);
      const value = cleanText(match?.innerText || match?.textContent);
      if (value) return value;
    }
    return "";
  }

  function readResults() {
    const results = [];
    for (const link of document.querySelectorAll("a[href*='/jobs/']")) {
      let parsed;
      try { parsed = new URL(link.href); } catch (_) { continue; }
      const match = parsed.pathname.match(/^\/jobs\/([^/]+)\/(\d+)(?:\/)?$/i);
      if (!match) continue;
      const cardText = cleanText(link.innerText || link.textContent);
      const title = firstText(link, ["h1", "h2", "h3", "h4", "[data-testid*='title']", "[class*='title']"])
        || cleanText(cardText.split("\n")[0]);
      const company = firstText(link, ["[data-testid*='company']", "[class*='company']"])
        || cleanText(cardText.split("\n")[1]);
      const postedLabel = (cardText.match(/Posted\s*[·•-]?\s*((?:today|yesterday|\d+\s+days?\s+ago))/i) || [])[1] || "";
      const location = firstText(link, ["[data-testid*='location']", "[class*='location']"]);
      const canonical = `https://job-boards.greenhouse.io/${match[1]}/jobs/${match[2]}`;
      results.push({
        external_job_id: match[2],
        company_key: match[1],
        company_name: company,
        role_title: title,
        location,
        job_url: canonical,
        apply_url: canonical,
        posted_at: relativePostedAt(postedLabel),
        posted_label: postedLabel,
        card_text: cardText,
      });
    }
    const unique = new Map(results.map((result) => [`${result.company_key}:${result.external_job_id}`, result]));
    return [...unique.values()];
  }

  function publish() {
    const results = readResults();
    const fingerprint = JSON.stringify(results);
    if (!results.length || fingerprint === lastFingerprint) return;
    lastFingerprint = fingerprint;
    chrome.runtime.sendMessage({ type: "GREENHOUSE_SEARCH_RESULTS", search_url: location.href, results }).catch(() => {});
  }

  publish();
  new MutationObserver(publish).observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("scroll", publish, { passive: true });
})();

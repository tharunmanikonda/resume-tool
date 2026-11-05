import "./launcher.css";

const status = document.querySelector("#launcher-status");
const retry = document.querySelector("#launcher-retry");

function isAtsJobUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    const host = parsed.hostname.toLowerCase();
    const path = parsed.pathname.toLowerCase();
    if (host === "jobs.dover.com") return /^\/[a-f0-9-]{36}\/[a-f0-9-]{36}\/?$/i.test(parsed.pathname);
    if (host === "jobs.lever.co" || host.endsWith(".lever.co")) return path.split("/").filter(Boolean).length >= 2;
    if (host === "boards.greenhouse.io" || host.endsWith(".greenhouse.io")) return path.includes("/jobs/") || parsed.searchParams.has("gh_jid");
    if (host === "jobs.ashbyhq.com" || host.endsWith(".ashbyhq.com") || host.endsWith(".ashby.com")) return path.split("/").filter(Boolean).length >= 2;
    if (host === "ats.rippling.com" || host.endsWith(".rippling.com")) return path.includes("/jobs/") || path.includes("/job/");
    return false;
  } catch (_) {
    return false;
  }
}

async function openResumePanel() {
  retry.hidden = true;
  status.textContent = "Opening...";
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    if (!tab?.id) {
      throw new Error("No active browser tab was found.");
    }
    if (!/^https?:\/\//i.test(String(tab.url || ""))) {
      if (chrome.sidePanel?.open) {
        await chrome.sidePanel.open({ windowId: tab.windowId });
        window.close();
        return;
      }
      throw new Error("Open a regular website first. Browser settings pages do not allow extension drawers.");
    }
    try {
      await chrome.tabs.sendMessage(tab.id, { type: "TOGGLE_RESUME_PANEL" });
    } catch (drawerError) {
      try {
        const currentUrl = String(tab.url || "");
        let script = "panel-host.js";
        if (currentUrl.startsWith("https://www.linkedin.com/jobs/")) script = "content-script.js";
        else if (/^https:\/\/(?:www\.)?dice\.com\//i.test(currentUrl)) script = "dice-content-script.js";
        else if (/^https:\/\/(?:www\.)?(?:hiring\.cafe|hiringcafe\.com)\//i.test(currentUrl)) script = "hiringcafe-content-script.js";
        else if (isAtsJobUrl(currentUrl)) script = "ats-content-script.js";
        const additional = globalThis.ResumeJobSites?.platform(currentUrl);
        const files = additional
          ? ["job-site-config.js", "job-board-content-script.js", "panel-host.js"]
          : [script];
        await chrome.scripting.executeScript({ target: { tabId: tab.id }, files });
        await chrome.tabs.sendMessage(tab.id, { type: "TOGGLE_RESUME_PANEL" });
      } catch (injectionError) {
        if (!chrome.sidePanel?.open) throw injectionError || drawerError;
        await chrome.sidePanel.open({ windowId: tab.windowId });
      }
    }
    window.close();
  } catch (error) {
    status.textContent = error?.message || "Could not open the resume window.";
    retry.hidden = false;
  }
}

retry.addEventListener("click", openResumePanel);
openResumePanel();

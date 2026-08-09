import "./launcher.css";

const status = document.querySelector("#launcher-status");
const retry = document.querySelector("#launcher-retry");

async function openResumePanel() {
  retry.hidden = true;
  status.textContent = "Opening...";
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    if (!tab?.id || !/^https?:\/\//i.test(String(tab.url || ""))) {
      throw new Error("Open a regular website first. Browser settings pages do not allow extension drawers.");
    }
    try {
      await chrome.tabs.sendMessage(tab.id, { type: "TOGGLE_RESUME_PANEL" });
    } catch (_) {
      const currentUrl = String(tab.url || "");
      let script = "panel-host.js";
      if (currentUrl.startsWith("https://www.linkedin.com/jobs/")) script = "content-script.js";
      else if (/^https:\/\/(?:www\.)?dice\.com\//i.test(currentUrl)) script = "dice-content-script.js";
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: [script] });
      await chrome.tabs.sendMessage(tab.id, { type: "TOGGLE_RESUME_PANEL" });
    }
    window.close();
  } catch (error) {
    status.textContent = error?.message || "Could not open the resume window.";
    retry.hidden = false;
  }
}

retry.addEventListener("click", openResumePanel);
openResumePanel();

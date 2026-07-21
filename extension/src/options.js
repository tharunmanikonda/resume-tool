import "./panel.css";

const input = document.querySelector("#server-url");
const status = document.querySelector("#status");

chrome.storage.local.get("resumeServerUrl").then((stored) => {
  input.value = stored.resumeServerUrl || "http://127.0.0.1:5001";
});

document.querySelector("#server-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = input.value.trim().replace(/\/$/, "");
  await chrome.storage.local.set({ resumeServerUrl: value });
  status.textContent = "Checking...";
  try {
    const response = await fetch(`${value}/api/extension/status`);
    const payload = await response.json();
    status.textContent = response.ok && payload.success ? "Saved and connected" : "Saved, but this is not the extension server";
  } catch (_) {
    status.textContent = "Saved, but the server is offline";
  }
});

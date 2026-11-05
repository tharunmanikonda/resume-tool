import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { chromium } from "playwright";

const root = path.resolve("extension/dist");
const server = http.createServer((request, response) => {
  const file = path.resolve(root, "." + new URL(request.url, "http://localhost").pathname);
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) {
    response.writeHead(404); response.end(); return;
  }
  response.setHeader("Content-Type", file.endsWith(".js") ? "application/javascript" : file.endsWith(".css") ? "text/css" : "text/html");
  response.end(fs.readFileSync(file));
});

let browser;
try {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.addInitScript(() => {
    window.sidePanelCalls = [];
    window.chrome = {
      tabs: {
        async query() { return [{ id: 7, windowId: 3, url: "chrome://extensions/" }]; },
        async sendMessage() { throw new Error("restricted page"); },
      },
      scripting: { async executeScript() { throw new Error("restricted page"); } },
      sidePanel: { async open(options) { window.sidePanelCalls.push(options); } },
    };
    window.close = () => { window.launcherClosed = true; };
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/launcher.html`);
  await page.waitForFunction(() => window.sidePanelCalls.length === 1);
  assert.deepEqual(await page.evaluate(() => window.sidePanelCalls[0]), { windowId: 3 });
  assert.equal(await page.evaluate(() => window.launcherClosed), true);
  console.log("Extension launcher native side-panel fallback passed.");
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}

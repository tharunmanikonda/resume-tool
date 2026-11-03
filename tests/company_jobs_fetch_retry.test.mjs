import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

process.env.JOB_MONITOR_RETRY_BASE_MS = "1";
const { fetchJson } = await import("../ops/company_jobs_fetch.mjs");

async function withServer(handler, callback) {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const { port } = server.address();
    await callback(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  }
}

test("fetchJson retries transient 502 responses", async () => {
  let requests = 0;
  await withServer((request, response) => {
    requests += 1;
    if (requests < 3) {
      response.writeHead(502).end("temporary failure");
      return;
    }
    response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify({ ok: true }));
  }, async (baseUrl) => {
    assert.deepEqual(await fetchJson(`${baseUrl}/jobs`), { ok: true });
  });
  assert.equal(requests, 3);
});

test("fetchJson does not retry permanent 400 responses", async () => {
  let requests = 0;
  await withServer((request, response) => {
    requests += 1;
    response.writeHead(400).end("bad request");
  }, async (baseUrl) => {
    await assert.rejects(fetchJson(`${baseUrl}/jobs`), /400 Bad Request/);
  });
  assert.equal(requests, 1);
});

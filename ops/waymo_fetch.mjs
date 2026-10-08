import { chromium } from "playwright";

const SEARCH_URL =
  "https://careers.withwaymo.com/jobs/search/?department=Software%20Engineering";

async function readStdin() {
  let value = "";
  for await (const chunk of process.stdin) value += chunk;
  return value.trim() ? JSON.parse(value) : {};
}

async function extractListings(page) {
  return page.locator("article.job-search-results-card-col").evaluateAll((cards) =>
    cards.map((card) => {
      const anchor = card.querySelector('a[id^="link_job_title"]');
      return {
        title: (anchor?.textContent || "").trim().replace(/\s+/g, " "),
        url: anchor?.href || "",
        metadata: [...card.querySelectorAll(".job-component-list li")].map((item) =>
          (item.textContent || "").trim().replace(/\s+/g, " "),
        ),
      };
    }),
  );
}

async function fetchListings(page) {
  await page.goto(SEARCH_URL, { waitUntil: "domcontentloaded" });
  await page.locator("article.job-search-results-card-col").first().waitFor();
  const resultText = await page.locator('[id^="jobs_search_results_"]').innerText();
  const total = Number(resultText.match(/of\s+(\d+)\s+in total/i)?.[1] || 30);
  const pageCount = Math.max(1, Math.ceil(total / 30));
  const listings = [];

  for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
    if (pageNumber > 1) {
      const url = new URL(page.url());
      url.searchParams.set("page", String(pageNumber));
      await page.goto(url.toString(), { waitUntil: "domcontentloaded" });
      await page.locator("article.job-search-results-card-col").first().waitFor();
    }
    listings.push(...(await extractListings(page)));
  }

  return [...new Map(listings.filter((job) => job.url).map((job) => [job.url, job])).values()];
}

async function fetchDetails(page, urls) {
  const details = [];
  for (const url of urls) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.locator("body").waitFor();
      details.push({
        url,
        final_url: page.url(),
        text: await page.locator("body").innerText(),
        error: null,
      });
    } catch (error) {
      details.push({ url, text: "", error: String(error?.message || error) });
    }
  }
  return details;
}

async function main() {
  const mode = process.argv[2] || "list";
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    page.setDefaultTimeout(30_000);
    if (mode === "list") {
      process.stdout.write(JSON.stringify({ jobs: await fetchListings(page) }));
      return;
    }
    if (mode === "details") {
      const payload = await readStdin();
      process.stdout.write(JSON.stringify({ details: await fetchDetails(page, payload.urls || []) }));
      return;
    }
    throw new Error(`Unsupported mode: ${mode}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});

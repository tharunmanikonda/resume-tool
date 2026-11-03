import { chromium } from "playwright";
import { pathToFileURL } from "node:url";

const CISCO_BASE = "https://cisco.wd5.myworkdayjobs.com";
const CISCO_SITE = "Cisco_Careers";
const NVIDIA_BASE = "https://nvidia.wd5.myworkdayjobs.com";
const NVIDIA_SITE = "NVIDIAExternalCareerSite";
const INTEPROS_URL = "https://inteprosrecruiting.my.site.com/careers/s/";
const RIVIAN_BASE = "https://careers.rivian.com";
const RIVIAN_CATEGORIES = [
  "Software Engineering",
  "Information Technology",
  "Autonomous Driving",
  "Business Intelligence",
  "Quality",
  "Test and Development",
].join("|");
const EBAY_SEARCH_BASE = "https://jobs.ebayinc.com/us/en/search-results";
const EBAY_SEARCH_TERMS = [
  "software engineer intern",
  "software engineering co-op",
  "software engineer",
  "software developer",
  "application developer",
  "systems support developer",
  "application support developer",
  "production support developer",
  "systems engineer",
  "business systems analyst",
  "automation engineer",
  "security engineer",
  "cloud engineer",
  "devops engineer",
  "production engineer",
  "operations engineer",
  "system verification engineer",
  "database",
  "systems analyst",
  "test engineer",
  "integration engineer",
  "release engineer",
  "debug technician",
];
const WORKDAY_COMPANIES = {
  occ: {
    base: "https://theocc.wd5.myworkdayjobs.com",
    tenant: "theocc",
    site: "careers",
    searchTexts: [""],
    knownPageLimit: 3,
  },
  cdk: {
    base: "https://cdk.wd1.myworkdayjobs.com",
    tenant: "cdk",
    site: "CDK",
    searchTexts: [""],
    knownPageLimit: 3,
  },
  iqvia: {
    base: "https://iqvia.wd1.myworkdayjobs.com",
    tenant: "iqvia",
    site: "IQVIA",
    searchTexts: [
      "software engineer intern",
      "software engineering co-op",
      "software engineer",
      "software developer",
      "application developer",
      "data engineer",
      "machine learning engineer",
      "platform engineer",
      "site reliability engineer",
      "systems support developer",
      "application support developer",
      "production support developer",
      "systems engineer",
      "business systems analyst",
      "automation engineer",
      "security engineer",
      "cloud engineer",
      "devops engineer",
      "production engineer",
      "operations engineer",
      "system verification engineer",
      "database",
      "systems analyst",
      "test engineer",
      "integration engineer",
      "release engineer",
      "debug technician",
    ],
    knownPageLimit: 3,
  },
};
const NBCU_API = "https://api.smartrecruiters.com/v1/companies/NBCUniversal3/postings";
const CBRE_SEARCH = "https://careers.cbre.com/en_US/careers/SearchJobs";
const CBRE_SEARCH_TERMS = [
  "software engineer intern",
  "software engineering co-op",
  "software engineer",
  "software developer",
  "application developer",
  "data engineer",
  "machine learning engineer",
  "platform engineer",
  "site reliability engineer",
  "systems support developer",
  "application support developer",
  "production support developer",
  "systems engineer",
  "business systems analyst",
  "automation engineer",
  "security engineer",
  "cloud engineer",
  "devops engineer",
  "production engineer",
  "operations engineer",
  "system verification engineer",
  "database",
  "systems analyst",
  "test engineer",
  "integration engineer",
  "release engineer",
  "debug technician",
];
const OCIENT_URL = "https://jobs.gem.com/ocient-inc-";
const CRUNCHYROLL_GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/crunchyroll";
const TIKTOK_API = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts";
const TIKTOK_SEARCH_TERMS = [
  "software engineer intern",
  "software engineering internship",
  "software engineer",
  "software developer",
  "backend engineer",
  "full stack engineer",
  "frontend engineer",
  "mobile engineer",
  "data engineer",
  "platform engineer",
  "site reliability engineer",
  "devops engineer",
  "cloud engineer",
  "security engineer",
  "test automation engineer",
  "systems engineer",
  "database engineer",
  "machine learning engineer",
];

async function readStdin() {
  let value = "";
  for await (const chunk of process.stdin) value += chunk;
  return value.trim() ? JSON.parse(value) : {};
}

function stripHtml(value) {
  return String(value || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>|<\/li>|<\/h\d>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&#43;/g, "+")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/\s+\n/g, "\n")
    .replace(/[ \t]+/g, " ")
    .trim();
}

function decodeHtmlEntities(value) {
  return String(value || "")
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&apos;|&#39;/gi, "'")
    .replace(/&amp;/gi, "&")
    .replace(/&nbsp;/gi, " ");
}

const FETCH_TIMEOUT_MS = 30_000;
const FETCH_MAX_ATTEMPTS = 4;
const FETCH_RETRY_BASE_MS = Number(process.env.JOB_MONITOR_RETRY_BASE_MS || 750);
const QUERY_CONCURRENCY = 4;
const DETAIL_CONCURRENCY = 6;

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function retryDelay(response, attempt) {
  const retryAfter = response?.headers?.get("retry-after");
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
    const date = Date.parse(retryAfter);
    if (Number.isFinite(date)) return Math.max(0, date - Date.now());
  }
  return FETCH_RETRY_BASE_MS * (2 ** (attempt - 1));
}

function isRetryableError(error) {
  return error?.name === "TimeoutError"
    || error?.name === "AbortError"
    || error instanceof TypeError;
}

async function mapWithConcurrency(values, limit, callback) {
  const results = new Array(values.length);
  let nextIndex = 0;
  async function worker() {
    while (nextIndex < values.length) {
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await callback(values[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, values.length) }, worker));
  return results;
}

export async function fetchJson(url, options = {}) {
  let lastError;
  for (let attempt = 1; attempt <= FETCH_MAX_ATTEMPTS; attempt += 1) {
    let response;
    try {
      response = await fetch(url, {
        ...options,
        signal: options.signal || AbortSignal.timeout(FETCH_TIMEOUT_MS),
      });
      if (response.ok) return response.json();

      const error = new Error(`${response.status} ${response.statusText}: ${url}`);
      if (response.status !== 429 && response.status < 500) throw error;
      lastError = error;
    } catch (error) {
      if (!isRetryableError(error) || options.signal) throw error;
      lastError = error;
    }

    if (attempt < FETCH_MAX_ATTEMPTS) await sleep(retryDelay(response, attempt));
  }
  throw lastError;
}

function tiktokLocation(cityInfo = {}) {
  const values = [];
  let current = cityInfo;
  while (current && typeof current === "object") {
    const name = current.name || current.en_name;
    if (name && !values.includes(name)) values.push(name);
    current = current.parent;
  }
  return values.join(", ");
}

async function tiktokListings() {
  const jobs = new Map();
  const limit = 100;
  const headers = {
    "accept-language": "en",
    "content-type": "application/json",
    origin: "https://lifeattiktok.com",
    "website-path": "tiktok",
  };
  for (const keyword of TIKTOK_SEARCH_TERMS) {
    let total = Infinity;
    for (let offset = 0; offset < total; offset += limit) {
      const payload = await fetchJson(TIKTOK_API, {
        method: "POST",
        headers,
        body: JSON.stringify({
          keyword,
          limit,
          offset,
          job_category_id_list: [],
          location_code_list: [],
          recruitment_id_list: [],
          subject_id_list: [],
          tag_id_list: [],
        }),
      });
      if (Number(payload.code) !== 0) throw new Error(`TikTok API error ${payload.code}: ${payload.message || "unknown error"}`);
      const data = payload.data || {};
      total = Number(data.count || 0);
      const pageJobs = data.job_post_list || [];
      for (const item of pageJobs) {
        const id = String(item.id || "");
        if (!id) continue;
        const description = [stripHtml(item.description), "Qualifications", stripHtml(item.requirement)]
          .filter(Boolean)
          .join("\n\n");
        jobs.set(id, {
          source: "tiktok",
          external_job_id: id,
          title: item.title || "",
          location: tiktokLocation(item.city_info),
          job_type: item.recruit_type?.en_name === "Regular" ? "Full time" : (item.recruit_type?.en_name || ""),
          posted_at: "",
          url: `https://lifeattiktok.com/search/${id}`,
          description_snapshot: description,
        });
      }
      if (!pageJobs.length || offset + pageJobs.length >= total) break;
    }
  }
  return [...jobs.values()];
}

async function tiktokDetails(jobs) {
  return jobs.map((job) => ({
    ...job,
    description: job.description_snapshot || "",
    error: job.description_snapshot ? null : "Empty TikTok description",
  }));
}

async function rivianListings(knownJobIds = []) {
  const jobs = [];
  const known = new Set(knownJobIds.map(String));
  let total = Infinity;
  let consecutiveKnownPages = 0;
  for (let page = 1; jobs.length < total; page += 1) {
    const params = new URLSearchParams({
      categories: RIVIAN_CATEGORIES,
      page: String(page),
      sortBy: "posted_date",
      descending: "true",
    });
    const payload = await fetchJson(`${RIVIAN_BASE}/api/jobs?${params}`);
    if (page === 1) total = Number(payload.totalCount || 0);
    const pageJobs = (payload.jobs || []).map(({ data = {} }) => ({
      source: "rivian",
      external_job_id: String(data.req_id || data.slug || ""),
      title: data.title || "",
      location: data.full_location || data.location_name || "",
      job_type: data.employment_type || data.tags1?.[0] || "",
      posted_at: data.posted_date || "",
      url: data.canonical_url || `${RIVIAN_BASE}/careers-home/jobs/${data.slug || data.req_id}`,
      description_snapshot: data.description || "",
    }));
    jobs.push(...pageJobs);
    consecutiveKnownPages = pageJobs.length > 0 && pageJobs.every((job) => known.has(job.external_job_id))
      ? consecutiveKnownPages + 1
      : 0;
    if (known.size && consecutiveKnownPages >= 3) break;
    if (!pageJobs.length || page > 100) break;
  }
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function rivianDetails(jobs) {
  return jobs.map((job) => ({
    external_job_id: job.external_job_id,
    title: job.title,
    location: job.location,
    posted_at: job.posted_at,
    description: stripHtml(job.description_snapshot),
    url: job.url,
    error: job.description_snapshot ? null : "Empty Rivian description",
  }));
}

async function loadEbay(page, searchTerm) {
  const params = new URLSearchParams({ keywords: searchTerm });
  await page.goto(`${EBAY_SEARCH_BASE}?${params}`, { waitUntil: "domcontentloaded", timeout: 90_000 });
  await page.locator('[data-ph-at-id="jobs-list-item"]').first().waitFor({ timeout: 60_000 });
  await page.locator("#sortselect").selectOption("Most recent");
  await page.waitForTimeout(1500);
}

async function ebayListings(page, knownJobIds = []) {
  const jobs = [];
  const known = new Set(knownJobIds.map(String));
  for (const searchTerm of EBAY_SEARCH_TERMS) {
    await loadEbay(page, searchTerm);
    let consecutiveKnownPages = 0;
    for (let pageNumber = 1; pageNumber <= 100; pageNumber += 1) {
      const pageJobs = await page.locator('a[data-ph-at-id="job-link"][data-ph-at-job-id-text]').evaluateAll((anchors) => anchors.map((anchor) => ({
        source: "ebay",
        external_job_id: anchor.getAttribute("data-ph-at-job-id-text") || "",
        title: anchor.getAttribute("data-ph-at-job-title-text") || anchor.textContent?.trim() || "",
        location: anchor.getAttribute("data-ph-at-job-location-area-text") || anchor.getAttribute("data-ph-at-job-location-text") || "",
        job_type: anchor.getAttribute("data-ph-at-job-type-text") || "",
        posted_at: anchor.getAttribute("data-ph-at-job-post-date-text") || "",
        url: anchor.href,
      })));
      jobs.push(...pageJobs);
      consecutiveKnownPages = pageJobs.length > 0 && pageJobs.every((job) => known.has(job.external_job_id))
        ? consecutiveKnownPages + 1
        : 0;
      if (known.size && consecutiveKnownPages >= 5) break;

      const next = page.locator('a[aria-label="Next"], a:has-text("Next")').filter({ visible: true }).first();
      if (!(await next.count()) || await next.getAttribute("aria-disabled") === "true") break;
      const firstId = pageJobs[0]?.external_job_id || "";
      await next.click();
      await page.waitForFunction((previous) => {
        const anchor = document.querySelector('a[data-ph-at-id="job-link"][data-ph-at-job-id-text]');
        return anchor && anchor.getAttribute("data-ph-at-job-id-text") !== previous;
      }, firstId, { timeout: 30_000 }).catch(() => {});
      await page.waitForTimeout(500);
    }
  }
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function ebayDetails(jobs) {
  const details = [];
  for (let offset = 0; offset < jobs.length; offset += 8) {
    const batch = await Promise.all(jobs.slice(offset, offset + 8).map(async (job) => {
      try {
        const response = await fetch(job.url);
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${job.url}`);
        const html = await response.text();
        const records = [...html.matchAll(/<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi)]
          .map((match) => match[1]);
        const posting = records.map((value) => {
          try { return JSON.parse(value); } catch { return null; }
        }).find((value) => value?.["@type"] === "JobPosting");
        if (!posting) throw new Error("eBay JobPosting metadata was not found.");
        const address = posting.jobLocation?.address || {};
        const location = [address.addressLocality, address.addressRegion, address.addressCountry].filter(Boolean).join(", ");
        return {
          external_job_id: job.external_job_id,
          title: posting.title || job.title,
          location: location || job.location,
          posted_at: posting.datePosted || job.posted_at,
          description: stripHtml(decodeHtmlEntities(posting.description)),
          url: job.url,
          error: null,
        };
      } catch (error) {
        return { external_job_id: job.external_job_id, description: "", error: String(error?.message || error) };
      }
    }));
    details.push(...batch);
  }
  return details;
}

async function ciscoListings(knownJobIds = []) {
  const endpoint = `${CISCO_BASE}/wday/cxs/cisco/${CISCO_SITE}/jobs`;
  const jobs = [];
  const known = new Set(knownJobIds.map(String));
  const limit = 20;
  let total = Infinity;
  let consecutiveKnownPages = 0;
  for (let offset = 0; offset < total; offset += limit) {
    const payload = await fetchJson(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ appliedFacets: {}, limit, offset, searchText: "" }),
    });
    if (offset === 0) total = Number(payload.total || 0);
    const pageJobs = (payload.jobPostings || []).map((job) => ({
      source: "cisco",
      external_job_id: String(job.bulletFields?.[0] || job.externalPath?.match(/_(\d+(?:-\d+)?)$/)?.[1] || ""),
      title: job.title || "",
      location: job.locationsText || "",
      job_type: job.timeType || "",
      posted_at: job.postedOn || "",
      external_path: job.externalPath || "",
      url: `${CISCO_BASE}${job.externalPath || ""}`,
    }));
    jobs.push(...pageJobs);
    consecutiveKnownPages = pageJobs.length > 0 && pageJobs.every((job) => known.has(job.external_job_id))
      ? consecutiveKnownPages + 1
      : 0;
    // Workday returns newest postings first. Three completely known pages give
    // a 60-job buffer around day boundaries while avoiding a full catalog pull.
    if (known.size && consecutiveKnownPages >= 3) break;
  }
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function ciscoDetails(jobs) {
  const details = [];
  for (const job of jobs) {
    try {
      const payload = await fetchJson(`${CISCO_BASE}/wday/cxs/cisco/${CISCO_SITE}${job.external_path}`);
      const info = payload.jobPostingInfo || {};
      details.push({
        external_job_id: job.external_job_id,
        title: info.title || job.title,
        location: [info.location, ...(info.additionalLocations || [])].filter(Boolean).join("; ") || job.location,
        posted_at: info.startDate || info.postedOn || job.posted_at,
        description: stripHtml(info.jobDescription),
        url: `${CISCO_BASE}${job.external_path}`,
        error: null,
      });
    } catch (error) {
      details.push({ external_job_id: job.external_job_id, description: "", error: String(error?.message || error) });
    }
  }
  return details;
}

async function nvidiaListings(knownJobIds = []) {
  const endpoint = `${NVIDIA_BASE}/wday/cxs/nvidia/${NVIDIA_SITE}/jobs`;
  const jobs = [];
  const known = new Set(knownJobIds.map(String));
  const limit = 20;
  let total = Infinity;
  let consecutiveKnownPages = 0;
  const appliedFacets = {
    jobFamilyGroup: ["0c40f6bd1d8f10ae43ffaefd46dc7e78", "0c40f6bd1d8f10ae43ffbd1459047e84"],
    locationHierarchy1: ["2fcb99c455831013ea52fb338f2932d8"],
  };
  for (let offset = 0; offset < total; offset += limit) {
    const payload = await fetchJson(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ appliedFacets, limit, offset, searchText: "" }),
    });
    if (offset === 0) total = Number(payload.total || 0);
    const pageJobs = (payload.jobPostings || []).map((job) => ({
      source: "nvidia",
      external_job_id: String(job.bulletFields?.[0] || job.externalPath?.match(/_(JR\d+(?:-\d+)?)$/i)?.[1] || ""),
      title: job.title || "",
      location: job.locationsText || "",
      job_type: job.timeType || "",
      posted_at: job.postedOn || "",
      external_path: job.externalPath || "",
      url: `${NVIDIA_BASE}${job.externalPath || ""}`,
    }));
    jobs.push(...pageJobs);
    consecutiveKnownPages = pageJobs.length > 0 && pageJobs.every((job) => known.has(job.external_job_id))
      ? consecutiveKnownPages + 1
      : 0;
    // NVIDIA can publish many roles on the same day, so keep a wider 100-job
    // buffer than Cisco before concluding the remaining newest-first rows are known.
    if (known.size && consecutiveKnownPages >= 5) break;
  }
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function nvidiaDetails(jobs) {
  const details = [];
  for (const job of jobs) {
    try {
      const payload = await fetchJson(`${NVIDIA_BASE}/wday/cxs/nvidia/${NVIDIA_SITE}${job.external_path}`);
      const info = payload.jobPostingInfo || {};
      details.push({
        external_job_id: job.external_job_id,
        title: info.title || job.title,
        location: [info.location, ...(info.additionalLocations || [])].filter(Boolean).join("; ") || job.location,
        posted_at: info.startDate || info.postedOn || job.posted_at,
        description: stripHtml(info.jobDescription),
        url: `${NVIDIA_BASE}${job.external_path}`,
        error: null,
      });
    } catch (error) {
      details.push({ external_job_id: job.external_job_id, description: "", error: String(error?.message || error) });
    }
  }
  return details;
}

async function loadIntepros(page) {
  await page.goto(INTEPROS_URL, { waitUntil: "domcontentloaded" });
  await page.locator("c-ats-external-job-card").first().waitFor({ timeout: 60_000 });
}

async function inteprosListings(page, knownJobIds = []) {
  await loadIntepros(page);
  const jobs = [];
  const known = new Set(knownJobIds.map(String));
  let pageNumber = 1;
  let consecutiveKnownPages = 0;
  while (true) {
    const pageJobs = await page.locator("c-ats-external-job-card").evaluateAll((cards) => cards.map((card) => {
      const anchor = card.closest("a") || card.querySelector("a");
      const cardText = (anchor?.innerText || card.textContent || "").trim();
      const title = cardText.split(/\n+/).map((value) => value.trim()).find(Boolean) || "";
      const url = anchor?.href || "";
      const externalId = new URL(url).searchParams.get("jobId")?.split("/")[0] || "";
      const text = cardText.replace(/\s+/g, " ");
      return { source: "intepros", external_job_id: externalId, title, location: "", job_type: "Contract", posted_at: text.match(/Posted (?:This Week|\w+ \d+,? \d{4})/i)?.[0] || "", url };
    }));
    jobs.push(...pageJobs);
    consecutiveKnownPages = pageJobs.length > 0 && pageJobs.every((job) => known.has(job.external_job_id))
      ? consecutiveKnownPages + 1
      : 0;
    if (known.size && consecutiveKnownPages >= 2) break;

    const next = page.locator("div.enable-icon.pagination-direction-element", { hasText: /^>$/ }).first();
    if (!(await next.count())) break;
    await next.click();
    pageNumber += 1;
    await page.locator(`div.pagination-element.active[data-id="${pageNumber}"]`).waitFor({ timeout: 30_000 }).catch(() => {});
    await page.waitForTimeout(500);
    if (pageNumber > 100) throw new Error("IntePros pagination exceeded safety limit.");
  }
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function inteprosDetails(page, jobs) {
  const details = [];
  for (const job of jobs) {
    try {
      await page.goto(job.url, { waitUntil: "domcontentloaded" });
      await page.locator("body").waitFor();
      await page.waitForTimeout(1200);
      const text = await page.locator("body").innerText();
      const location = [...text.matchAll(/City and State\s*\n+\s*([^\n]+,\s*[A-Z]{2})/gi)].at(-1)?.[1]?.trim() || job.location;
      const posted = text.match(/Posted Date\s+([^\n]+)/i)?.[1]?.trim() || job.posted_at;
      details.push({ external_job_id: job.external_job_id, title: job.title, location, posted_at: posted, description: text, url: job.url, error: null });
    } catch (error) {
      details.push({ external_job_id: job.external_job_id, description: "", error: String(error?.message || error) });
    }
  }
  return details;
}

async function workdayListings(company, config, knownJobIds = []) {
  const known = new Set(knownJobIds.map(String));
  const endpoint = `${config.base}/wday/cxs/${config.tenant}/${config.site}/jobs`;
  const queryResults = await mapWithConcurrency(config.searchTexts, QUERY_CONCURRENCY, async (searchText) => {
    const jobs = [];
    const limit = 20;
    let total = Infinity;
    let consecutiveKnownPages = 0;
    for (let offset = 0; offset < total; offset += limit) {
      const payload = await fetchJson(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ appliedFacets: {}, limit, offset, searchText }),
      });
      if (offset === 0) total = Number(payload.total || 0);
      const pageJobs = (payload.jobPostings || []).map((job) => ({
        source: company,
        external_job_id: String(job.bulletFields?.[0] || job.externalPath?.split("_").at(-1) || ""),
        title: job.title || "",
        location: job.locationsText || "",
        job_type: job.timeType || "",
        posted_at: job.postedOn || "",
        external_path: job.externalPath || "",
        url: `${config.base}${job.externalPath || ""}`,
      }));
      jobs.push(...pageJobs);
      consecutiveKnownPages = pageJobs.length > 0 && pageJobs.every((job) => known.has(job.external_job_id))
        ? consecutiveKnownPages + 1
        : 0;
      if (known.size && consecutiveKnownPages >= config.knownPageLimit) break;
      if (!pageJobs.length) break;
    }
    return jobs;
  });
  const jobs = queryResults.flat();
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function workdayDetails(config, jobs) {
  const details = [];
  for (let offset = 0; offset < jobs.length; offset += 8) {
    const batch = await Promise.all(jobs.slice(offset, offset + 8).map(async (job) => {
      try {
        const payload = await fetchJson(`${config.base}/wday/cxs/${config.tenant}/${config.site}${job.external_path}`);
        const info = payload.jobPostingInfo || {};
        return {
          external_job_id: job.external_job_id,
          title: info.title || job.title,
          location: [info.location, ...(info.additionalLocations || [])].filter(Boolean).join("; ") || job.location,
          posted_at: info.startDate || info.postedOn || job.posted_at,
          description: stripHtml(info.jobDescription),
          url: `${config.base}${job.external_path}`,
          error: null,
        };
      } catch (error) {
        return { external_job_id: job.external_job_id, description: "", error: String(error?.message || error) };
      }
    }));
    details.push(...batch);
  }
  return details;
}

function slugify(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

async function nbcuListings(knownJobIds = []) {
  const jobs = [];
  const known = new Set(knownJobIds.map(String));
  const limit = 100;
  let total = Infinity;
  let consecutiveKnownPages = 0;
  for (let offset = 0; offset < total; offset += limit) {
    const payload = await fetchJson(`${NBCU_API}?limit=${limit}&offset=${offset}`);
    if (offset === 0) total = Number(payload.totalFound || 0);
    const pageJobs = (payload.content || [])
      .filter((job) => String(job.location?.country || "").toLowerCase() === "us")
      .map((job) => ({
        source: "nbcu",
        external_job_id: String(job.id || job.refNumber || ""),
        title: job.name || "",
        location: job.location?.fullLocation || "",
        job_type: job.typeOfEmployment?.label || "Full-time",
        posted_at: job.releasedDate || "",
        url: `https://jobs.smartrecruiters.com/NBCUniversal3/${job.id}-${slugify(job.name)}`,
      }));
    jobs.push(...pageJobs);
    consecutiveKnownPages = pageJobs.length > 0 && pageJobs.every((job) => known.has(job.external_job_id))
      ? consecutiveKnownPages + 1
      : 0;
    if (known.size && consecutiveKnownPages >= 3) break;
    if (!(payload.content || []).length) break;
  }
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function nbcuDetails(jobs) {
  const details = [];
  for (let offset = 0; offset < jobs.length; offset += 8) {
    const batch = await Promise.all(jobs.slice(offset, offset + 8).map(async (job) => {
      try {
        const payload = await fetchJson(`${NBCU_API}/${job.external_job_id}`);
        const sections = payload.jobAd?.sections || {};
        const description = [
          sections.companyDescription?.text,
          sections.jobDescription?.text,
          sections.qualifications?.text,
          sections.additionalInformation?.text,
        ].filter(Boolean).map(stripHtml).join("\n\n");
        return {
          external_job_id: job.external_job_id,
          title: payload.name || job.title,
          location: payload.location?.fullLocation || job.location,
          posted_at: payload.releasedDate || job.posted_at,
          description,
          url: payload.postingUrl || job.url,
          error: description ? null : "Empty NBCUniversal description",
        };
      } catch (error) {
        return { external_job_id: job.external_job_id, description: "", error: String(error?.message || error) };
      }
    }));
    details.push(...batch);
  }
  return details;
}

async function crunchyrollListings() {
  const payload = await fetchJson(`${CRUNCHYROLL_GREENHOUSE_API}/jobs`);
  return (payload.jobs || []).map((job) => ({
    source: "crunchyroll",
    external_job_id: String(job.id || ""),
    title: job.title || "",
    location: job.location?.name || "",
    job_type: "",
    posted_at: "",
    source_updated_at: job.updated_at || "",
    url: job.absolute_url || `https://job-boards.greenhouse.io/crunchyroll/jobs/${job.id}`,
  })).filter((job) => job.external_job_id);
}

async function crunchyrollDetails(jobs) {
  const details = [];
  for (let offset = 0; offset < jobs.length; offset += 8) {
    const batch = await Promise.all(jobs.slice(offset, offset + 8).map(async (job) => {
      try {
        const payload = await fetchJson(`${CRUNCHYROLL_GREENHOUSE_API}/jobs/${job.external_job_id}`);
        const description = stripHtml(decodeHtmlEntities(payload.content));
        return {
          external_job_id: job.external_job_id,
          title: payload.title || job.title,
          location: payload.location?.name || job.location,
          posted_at: job.posted_at,
          source_updated_at: payload.updated_at || job.source_updated_at || "",
          description,
          url: payload.absolute_url || job.url,
          error: description ? null : "Empty Crunchyroll description",
        };
      } catch (error) {
        return { external_job_id: job.external_job_id, description: "", error: String(error?.message || error) };
      }
    }));
    details.push(...batch);
  }
  return details;
}

async function cbreSearchListings(page, search, known) {
  const jobs = [];
  let consecutiveKnownPages = 0;
  for (let offset = 0; offset < 2500; offset += 25) {
    const params = new URLSearchParams({
      search,
      jobRecordsPerPage: "25",
      jobOffset: String(offset),
      jobSort: "postedDate",
      jobSortDirection: "DESC",
    });
    const url = `${CBRE_SEARCH}?${params}`;
    let navigationError;
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45_000 });
        navigationError = null;
        break;
      } catch (error) {
        navigationError = error;
        if (attempt < 3) await page.waitForTimeout(attempt * 1_000);
      }
    }
    if (navigationError) throw navigationError;
    const firstCard = page.locator("article.article--result").first();
    const found = await firstCard.waitFor({ state: "attached", timeout: 12_000 }).then(() => true).catch(() => false);
    if (!found) break;
    const pageJobs = await page.locator("article.article--result").evaluateAll((cards) => cards.map((card) => {
      const anchor = card.querySelector('a[href*="/JobDetail/"]');
      const text = (card.innerText || "").replace(/\s+/g, " ").trim();
      return {
        source: "cbre",
        external_job_id: text.match(/Job ID:\s*(\d+)/i)?.[1] || anchor?.href.match(/\/(\d+)(?:\?.*)?$/)?.[1] || "",
        title: anchor?.textContent?.trim() || "",
        location: text.match(/Posted:\s*[^|]+\|\s*(.*?)(?:Apply now|Save Job|$)/i)?.[1]?.trim() || "",
        job_type: "Full time",
        posted_at: text.match(/Posted:\s*([^|]+)/i)?.[1]?.trim() || "",
        url: anchor?.href || "",
      };
    }));
    jobs.push(...pageJobs);
    consecutiveKnownPages = pageJobs.length > 0 && pageJobs.every((job) => known.has(job.external_job_id))
      ? consecutiveKnownPages + 1
      : 0;
    if (known.size && consecutiveKnownPages >= 3) break;
    if (pageJobs.length < 25) break;
  }
  return jobs;
}

async function cbreListings(browser, knownJobIds = []) {
  const known = new Set(knownJobIds.map(String));
  const runQueries = (concurrency) => mapWithConcurrency(CBRE_SEARCH_TERMS, concurrency, async (search) => {
    const page = await browser.newPage();
    page.setDefaultTimeout(15_000);
    await page.route("**/*", (route) => {
      const type = route.request().resourceType();
      return ["image", "font", "media", "stylesheet"].includes(type) ? route.abort() : route.continue();
    });
    try {
      return await cbreSearchListings(page, search, known);
    } finally {
      await page.close();
    }
  });
  let jobs = (await runQueries(QUERY_CONCURRENCY)).flat();
  if (!jobs.length) {
    await new Promise((resolve) => setTimeout(resolve, 5_000));
    jobs = (await runQueries(QUERY_CONCURRENCY)).flat();
  }
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function browserTextDetails(browser, jobs, company) {
  return mapWithConcurrency(jobs, DETAIL_CONCURRENCY, async (job) => {
    const page = await browser.newPage();
    page.setDefaultTimeout(20_000);
    await page.route("**/*", (route) => {
      const type = route.request().resourceType();
      return ["image", "font", "media", "stylesheet"].includes(type) ? route.abort() : route.continue();
    });
    try {
      await page.goto(job.url, { waitUntil: "domcontentloaded", timeout: 45_000 });
      await page.locator("body").waitFor();
      await page.waitForTimeout(500);
      const description = await page.locator("body").innerText();
      return { ...job, description, error: description ? null : `Empty ${company} description` };
    } catch (error) {
      return { external_job_id: job.external_job_id, description: "", error: String(error?.message || error) };
    } finally {
      await page.close();
    }
  });
}

async function ocientListings(page) {
  await page.goto(OCIENT_URL, { waitUntil: "domcontentloaded", timeout: 90_000 });
  const links = page.locator('a[href*="/ocient-inc-/"]');
  await links.first().waitFor({ state: "attached", timeout: 60_000 });
  const jobs = await links.evaluateAll((anchors) => anchors.map((anchor) => {
    const lines = (anchor.innerText || "").split(/\n+/).map((value) => value.trim()).filter(Boolean);
    const url = anchor.href;
    return {
      source: "ocient",
      external_job_id: new URL(url).pathname.split("/").filter(Boolean).at(-1) || "",
      title: lines[0] || "",
      location: lines.slice(1).filter((value) => value !== "•").join(", "),
      job_type: "Full time",
      posted_at: "",
      url,
    };
  }));
  return [...new Map(jobs.filter((job) => job.external_job_id).map((job) => [job.external_job_id, job])).values()];
}

async function main() {
  const company = process.argv[2];
  const mode = process.argv[3] || "list";
  const payload = await readStdin();
  if (WORKDAY_COMPANIES[company]) {
    const config = WORKDAY_COMPANIES[company];
    process.stdout.write(JSON.stringify(mode === "list"
      ? { jobs: await workdayListings(company, config, payload.known_job_ids || []) }
      : { details: await workdayDetails(config, payload.jobs || []) }));
    return;
  }
  if (company === "nbcu") {
    process.stdout.write(JSON.stringify(mode === "list"
      ? { jobs: await nbcuListings(payload.known_job_ids || []) }
      : { details: await nbcuDetails(payload.jobs || []) }));
    return;
  }
  if (company === "crunchyroll") {
    process.stdout.write(JSON.stringify(mode === "list"
      ? { jobs: await crunchyrollListings() }
      : { details: await crunchyrollDetails(payload.jobs || []) }));
    return;
  }
  if (company === "cisco") {
    process.stdout.write(JSON.stringify(mode === "list" ? { jobs: await ciscoListings(payload.known_job_ids || []) } : { details: await ciscoDetails(payload.jobs || []) }));
    return;
  }
  if (company === "nvidia") {
    process.stdout.write(JSON.stringify(mode === "list" ? { jobs: await nvidiaListings(payload.known_job_ids || []) } : { details: await nvidiaDetails(payload.jobs || []) }));
    return;
  }
  if (company === "rivian") {
    process.stdout.write(JSON.stringify(mode === "list" ? { jobs: await rivianListings(payload.known_job_ids || []) } : { details: await rivianDetails(payload.jobs || []) }));
    return;
  }
  if (company === "tiktok") {
    process.stdout.write(JSON.stringify(mode === "list"
      ? { jobs: await tiktokListings() }
      : { details: await tiktokDetails(payload.jobs || []) }));
    return;
  }
  if (company === "ebay") {
    if (mode === "details") {
      process.stdout.write(JSON.stringify({ details: await ebayDetails(payload.jobs || []) }));
      return;
    }
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage();
      page.setDefaultTimeout(30_000);
      process.stdout.write(JSON.stringify({ jobs: await ebayListings(page, payload.known_job_ids || []) }));
    } finally {
      await browser.close();
    }
    return;
  }
  if (company === "intepros") {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage();
      page.setDefaultTimeout(30_000);
      process.stdout.write(JSON.stringify(mode === "list" ? { jobs: await inteprosListings(page, payload.known_job_ids || []) } : { details: await inteprosDetails(page, payload.jobs || []) }));
    } finally {
      await browser.close();
    }
    return;
  }
  if (company === "cbre" || company === "ocient") {
    const browser = await chromium.launch({ headless: true });
    try {
      if (mode === "list") {
        const jobs = company === "cbre"
          ? await cbreListings(browser, payload.known_job_ids || [])
          : await ocientListings(await browser.newPage());
        process.stdout.write(JSON.stringify({ jobs }));
      } else {
        process.stdout.write(JSON.stringify({ details: await browserTextDetails(browser, payload.jobs || [], company) }));
      }
    } finally {
      await browser.close();
    }
    return;
  }
  throw new Error(`Unsupported company: ${company}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error?.stack || error}\n`);
    process.exitCode = 1;
  });
}


import React, { useEffect, useMemo, useRef, useState } from "react";

const emptyProfile = {
  name: "",
  contact: { location: "", phone: "", email: "" },
  certifications: [],
  projects: [],
  experience_history: [],
};

const experienceKeys = ["mckinsey", "uber", "kpmg", "trigent"];

const resumeModes = [
  { value: "professional", label: "Professional" },
  { value: "internship", label: "Intern / Co-op" },
];

function normalizeResumeMode(value) {
  return value === "internship" ? "internship" : "professional";
}

const outreachStatuses = [
  "Researching",
  "Ready to contact",
  "Strong outreach lead",
  "Needs contact research",
  "Weak fit",
  "Blocked",
  "Contacted",
  "Follow-up",
  "Responded",
  "Closed",
];

const outreachSourceTypes = [
  "VC/Funding",
  "Founder post",
  "Product launch",
  "Engineering signal",
  "Hiring signal",
  "Manual research",
  "Other",
];

function createEmptyOutreachDraft() {
  return {
    company_name: "",
    website: "",
    source_type: "Manual research",
    source_url: "",
    signal_text: "",
    product_summary: "",
    inferred_engineering_need: "",
    target_role_type: "",
    contact_name: "",
    contact_role: "",
    contact_email: "",
    contact_url: "",
    fit_score: "",
    fit_reasons: "",
    resume_angle: "",
    message_subject: "",
    message_body: "",
    blocked_reason: "",
    status: "",
    notes: "",
    last_contacted_at: "",
    follow_up_at: "",
  };
}

async function copyTextToClipboard(text) {
  const value = String(text || "");
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const element = document.createElement("textarea");
  element.value = value;
  element.setAttribute("readonly", "");
  element.style.position = "fixed";
  element.style.opacity = "0";
  document.body.appendChild(element);
  element.select();
  document.execCommand("copy");
  document.body.removeChild(element);
}

function fetchJson(url, options = {}) {
  return fetch(url, options).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error || data.message || "Request failed");
      error.data = data;
      throw error;
    }
    return data;
  });
}

function applyBold(text) {
  return (text || "").split(/(\*\*.*?\*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

function looksLikeJobDescription(text) {
  const value = (text || "").trim();
  if (!value) return false;

  const lower = value.toLowerCase();
  const jdSignals = [
    "about the job",
    "role description",
    "company description",
    "qualifications",
    "responsibilities",
    "preferred qualifications",
    "basic qualifications",
    "essential qualifications",
    "about the role",
    "what you'll do",
    "what you will do",
    "job description",
  ];

  if (value.length > 600) return true;
  return jdSignals.some((signal) => lower.includes(signal));
}

function ThreadCard({ entry }) {
  return (
    <div className={`thread-card ${entry.kind}`}>
      <div className="thread-card-header">{entry.kind === "user" ? "You" : "Resume Engine"}</div>
      {entry.title ? <div className="thread-card-title">{entry.title}</div> : null}
      <div className="thread-card-body">
        {entry.lines?.map((line, index) => (
          <p key={index}>{line}</p>
        ))}
        {entry.list?.length ? (
          <ul className="thread-card-list">
            {entry.list.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function CptStatusBand({ cpt }) {
  if (!cpt) return null;
  const passed = cpt.status === "green";
  const state = passed ? "passed" : cpt.status === "red" ? "red" : "review";
  return (
    <div className={`cpt-status-band ${state}`}>
      <strong>{passed ? "CPT check passed" : cpt.status === "red" ? "CPT check not accepting" : "CPT check needs review"}</strong>
      <span>{cpt.message}</span>
      <div className="cpt-status-meta">
        {cpt.matched_company_name ? <small>Matched: {cpt.matched_company_name}</small> : null}
        {cpt.cpt_agreement ? <small>Agreement: {cpt.cpt_agreement}</small> : null}
        {cpt.warning ? <small>{cpt.warning}</small> : null}
      </div>
    </div>
  );
}

const jobSourceTypes = [
  { value: "linkedin_search", label: "LinkedIn search" },
  { value: "greenhouse", label: "Greenhouse" },
  { value: "lever", label: "Lever" },
  { value: "ashby", label: "Ashby" },
  { value: "rippling", label: "Rippling" },
];

function cptLabel(status) {
  if (status === "green") return "CPT green";
  if (status === "red") return "CPT red";
  return "CPT review";
}

function sourceLabel(value) {
  return jobSourceTypes.find((item) => item.value === value)?.label || value || "Source";
}

function JobInbox() {
  const [tab, setTab] = useState("fresh");
  const [sources, setSources] = useState([]);
  const [leads, setLeads] = useState([]);
  const [selectedLeadId, setSelectedLeadId] = useState("");
  const [selectedLead, setSelectedLead] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [scanResult, setScanResult] = useState(null);
  const [filters, setFilters] = useState({ q: "", source: "", cpt_status: "", location: "" });
  const [sourceDraft, setSourceDraft] = useState({
    source_type: "greenhouse",
    name: "",
    company_name: "",
    source_key: "",
    url: "",
    enabled: true,
  });
  const enabledSourceCount = sources.filter((source) => source.enabled).length;

  function loadSources() {
    return fetchJson("/api/job-sources")
      .then((data) => setSources(data.sources || []))
      .catch((err) => setError(err.message || "Could not load sources."));
  }

  function leadQueryParams(nextTab = tab) {
    const params = new URLSearchParams();
    params.set("limit", "75");
    if (nextTab === "fresh") params.set("fresh", "true");
    if (nextTab === "review") params.set("relevance_status", "needs_review");
    if (nextTab === "saved") params.set("status", "saved");
    if (nextTab === "hidden") params.set("status", "hidden");
    if (filters.q.trim()) params.set("q", filters.q.trim());
    if (filters.source) params.set("source", filters.source);
    if (filters.cpt_status) params.set("cpt_status", filters.cpt_status);
    if (filters.location.trim()) params.set("location", filters.location.trim());
    return params.toString();
  }

  function loadLeads(nextTab = tab) {
    if (nextTab === "sources") return Promise.resolve();
    setLoading(true);
    setError("");
    return fetchJson(`/api/job-leads?${leadQueryParams(nextTab)}`)
      .then((data) => {
        setLeads(data.leads || []);
        setSelectedLeadId(data.leads?.[0]?.id || "");
        setSelectedLead(null);
      })
      .catch((err) => setError(err.message || "Could not load job leads."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadSources();
    loadLeads("fresh");
  }, []);

  useEffect(() => {
    loadLeads(tab);
  }, [tab, filters.q, filters.source, filters.cpt_status, filters.location]);

  useEffect(() => {
    if (!selectedLeadId) {
      setSelectedLead(null);
      return;
    }
    fetchJson(`/api/job-leads/${encodeURIComponent(selectedLeadId)}`)
      .then((data) => setSelectedLead(data.lead || null))
      .catch(() => setSelectedLead(null));
  }, [selectedLeadId]);

  async function saveSource() {
    setError("");
    setMessage("");
    try {
      const data = await fetchJson("/api/job-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sourceDraft),
      });
      setSources((current) => [data.source, ...current]);
      setSourceDraft({ source_type: "greenhouse", name: "", company_name: "", source_key: "", url: "", enabled: true });
      setMessage("Source saved.");
    } catch (err) {
      setError(err.message || "Source could not be saved.");
    }
  }

  async function toggleSource(source) {
    try {
      const data = await fetchJson(`/api/job-sources/${encodeURIComponent(source.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...source, enabled: !source.enabled }),
      });
      setSources((current) => current.map((item) => item.id === source.id ? data.source : item));
    } catch (err) {
      setError(err.message || "Source could not be updated.");
    }
  }

  async function scanSource(source) {
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const data = await fetchJson(`/api/job-sources/${encodeURIComponent(source.id)}/scan`, { method: "POST" });
      setScanResult(data.result || null);
      await loadSources();
      await loadLeads(tab);
      setMessage(`${source.name} scan finished.`);
    } catch (err) {
      setError(err.message || "Scan failed.");
    } finally {
      setLoading(false);
    }
  }

  async function scanAll() {
    if (!enabledSourceCount) {
      setMessage("");
      setError("Add and enable at least one ATS source before scanning.");
      setTab("sources");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const data = await fetchJson("/api/job-sources/scan-all", { method: "POST" });
      setScanResult(data.totals || null);
      await loadSources();
      await loadLeads(tab);
      setMessage("Scan all finished.");
    } catch (err) {
      setError(err.message || "Scan all failed.");
    } finally {
      setLoading(false);
    }
  }

  async function updateLeadStatus(lead, status) {
    if (!lead?.id) return;
    try {
      const data = await fetchJson(`/api/job-leads/${encodeURIComponent(lead.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      setSelectedLead(data.lead || null);
      await loadLeads(tab);
    } catch (err) {
      setError(err.message || "Job could not be updated.");
    }
  }

  async function promoteLead(lead) {
    if (!lead?.id) return;
    setLoading(true);
    setError("");
    try {
      const data = await fetchJson(`/api/job-leads/${encodeURIComponent(lead.id)}/promote-to-draft`, { method: "POST" });
      if (data.draft?.id) {
        window.location.href = `/?draft=${encodeURIComponent(data.draft.id)}`;
      }
    } catch (err) {
      setError(err.message || "Could not create a resume draft.");
    } finally {
      setLoading(false);
    }
  }

  const currentLead = selectedLead || leads.find((lead) => lead.id === selectedLeadId) || null;

  return (
    <main className="workspace job-workspace-shell">
      <div className="job-workspace">
        <div className="job-workspace-header">
          <div>
            <h1>Job Inbox</h1>
            <div className="muted-text">Scan ATS boards, keep fresh jobs visible, and turn good leads into resume drafts.</div>
          </div>
          <div className="job-header-actions">
            <button className="secondary-button" disabled={loading} onClick={() => loadLeads(tab)}>Refresh</button>
            <button className="primary-button" disabled={loading || !enabledSourceCount} onClick={scanAll}>{loading ? "Scanning..." : "Scan all"}</button>
          </div>
        </div>

        <div className="job-tabs">
          {["fresh", "review", "saved", "hidden", "sources"].map((item) => (
            <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>
              {item === "fresh" ? "Fresh Jobs" : item === "review" ? "Needs Review" : item[0].toUpperCase() + item.slice(1)}
            </button>
          ))}
        </div>

        {message ? <div className="job-notice">{message}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}
        {scanResult ? (
          <div className="job-summary-strip">
            <div><strong>{scanResult.fetched ?? 0}</strong><span>Fetched</span></div>
            <div><strong>{scanResult.new ?? 0}</strong><span>New</span></div>
            <div><strong>{scanResult.updated ?? 0}</strong><span>Updated</span></div>
            <div><strong>{scanResult.errors ?? 0}</strong><span>Errors</span></div>
          </div>
        ) : null}

        {tab === "sources" ? (
          <div className="job-settings-layout">
            <section className="job-panel">
              <div className="job-panel-heading">
                <h2>Sources</h2>
                <button className="secondary-button compact-button" onClick={loadSources}>Refresh</button>
              </div>
              {sources.length ? sources.map((source) => (
                <div key={source.id} className="source-row">
                  <div>
                    <strong>{source.name}</strong>
                    <div className="muted-text">{sourceLabel(source.source_type)} · {source.source_key}</div>
                    {source.last_scan_status ? <div className="muted-text">Last scan: {source.last_scan_status}{source.last_scan_error ? ` · ${source.last_scan_error}` : ""}</div> : null}
                  </div>
                  <div className="source-row-actions">
                    {source.url ? <a className="secondary-button link-button" href={source.url} target="_blank" rel="noreferrer">Open</a> : null}
                    <button className="secondary-button compact-button" onClick={() => toggleSource(source)}>{source.enabled ? "Disable" : "Enable"}</button>
                    <button className="primary-button compact-button" disabled={loading || !source.enabled} onClick={() => scanSource(source)}>Scan</button>
                  </div>
                </div>
              )) : <div className="blank-state compact">No sources yet. Add an ATS source with its board token or slug, then scan.</div>}
            </section>
            <section className="job-panel source-form">
              <h2>Add Source</h2>
              <p className="muted-text">For ATS scans, use the exact company board token or slug, for example a Greenhouse board token like stripe or an Ashby slug like ramp.</p>
              <select value={sourceDraft.source_type} onChange={(e) => setSourceDraft((current) => ({ ...current, source_type: e.target.value }))}>
                {jobSourceTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <input value={sourceDraft.name} onChange={(e) => setSourceDraft((current) => ({ ...current, name: e.target.value }))} placeholder="Source name" />
              <input value={sourceDraft.company_name} onChange={(e) => setSourceDraft((current) => ({ ...current, company_name: e.target.value }))} placeholder="Company name" />
              <input value={sourceDraft.source_key} onChange={(e) => setSourceDraft((current) => ({ ...current, source_key: e.target.value }))} placeholder="Board token, slug, or search key" />
              <input value={sourceDraft.url} onChange={(e) => setSourceDraft((current) => ({ ...current, url: e.target.value }))} placeholder="Optional URL" />
              <button className="primary-button" onClick={saveSource}>Save source</button>
            </section>
          </div>
        ) : (
          <>
            <div className="job-filters">
              <input value={filters.q} onChange={(e) => setFilters((current) => ({ ...current, q: e.target.value }))} placeholder="Search title or company" />
              <select value={filters.source} onChange={(e) => setFilters((current) => ({ ...current, source: e.target.value }))}>
                <option value="">All sources</option>
                {jobSourceTypes.filter((item) => item.value !== "linkedin_search").map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                <option value="linkedin">LinkedIn</option>
              </select>
              <select value={filters.cpt_status} onChange={(e) => setFilters((current) => ({ ...current, cpt_status: e.target.value }))}>
                <option value="">Any CPT</option>
                <option value="green">Green</option>
                <option value="red">Red</option>
                <option value="review">Review</option>
                <option value="not_found">Not found</option>
              </select>
              <input value={filters.location} onChange={(e) => setFilters((current) => ({ ...current, location: e.target.value }))} placeholder="Location" />
              <button className="secondary-button" onClick={() => setFilters({ q: "", source: "", cpt_status: "", location: "" })}>Clear</button>
            </div>
            <div className="job-content">
              <section className="job-list">
                {leads.length ? leads.map((lead) => (
                  <button key={lead.id} className={`job-row ${lead.id === currentLead?.id ? "selected" : ""}`} onClick={() => setSelectedLeadId(lead.id)}>
                    <span className="job-row-main">
                      <strong>{lead.role_title}</strong>
                      <span>{lead.company_name} · {lead.location || "Location unknown"}</span>
                      <small>{lead.relevance_reason}</small>
                    </span>
                    <span className="job-row-meta">
                      <span>{sourceLabel(lead.source)}</span>
                      <span className="job-date-line"><b>Posted</b>{lead.posted_at ? formatDateShort(lead.posted_at) : "Unknown"}</span>
                      <span className="job-date-line"><b>Seen</b>{formatDateShort(lead.first_seen_at)}</span>
                      <span>{cptLabel(lead.cpt_status)}</span>
                    </span>
                  </button>
                )) : <div className="blank-state compact">{loading ? "Loading jobs..." : "No jobs in this view."}</div>}
              </section>
              <section className="job-detail">
                {currentLead ? (
                  <>
                    <div className="job-detail-top">
                      <div className="panel-eyebrow">{sourceLabel(currentLead.source)}</div>
                      <h2>{currentLead.role_title}</h2>
                      <div className="muted-text">{currentLead.company_name} · {currentLead.location || "Location unknown"}</div>
                      <div className="job-chip-row">
                        <span className="badge">{currentLead.status}</span>
                        <span className="badge">{currentLead.relevance_status}</span>
                        <span className={`badge ${currentLead.cpt_status === "green" ? "status-ok" : currentLead.cpt_status === "red" ? "status-error" : ""}`}>{cptLabel(currentLead.cpt_status)}</span>
                      </div>
                      <div className="job-date-grid">
                        <div>
                          <span>Posted</span>
                          <strong>{currentLead.posted_at ? formatDateTimeShort(currentLead.posted_at) : "Unknown"}</strong>
                        </div>
                        <div>
                          <span>First seen</span>
                          <strong>{formatDateTimeShort(currentLead.first_seen_at)}</strong>
                        </div>
                        <div>
                          <span>Last changed</span>
                          <strong>{formatDateTimeShort(currentLead.last_changed_at)}</strong>
                        </div>
                      </div>
                    </div>
                    <div className="job-detail-actions">
                      {currentLead.job_url ? <a className="secondary-button link-button" href={currentLead.job_url} target="_blank" rel="noreferrer">Open job</a> : null}
                      {currentLead.apply_url ? <a className="secondary-button link-button" href={currentLead.apply_url} target="_blank" rel="noreferrer">Apply page</a> : null}
                      <button className="secondary-button" onClick={() => updateLeadStatus(currentLead, "saved")}>Save</button>
                      <button className="secondary-button" onClick={() => updateLeadStatus(currentLead, "hidden")}>Hide</button>
                      <button className="primary-button" disabled={loading} onClick={() => promoteLead(currentLead)}>Create resume</button>
                    </div>
                    <div className="job-detail-scroll">
                      <div className="job-copy">{currentLead.job_description || "No full description was available from this source. Open the job page and use the extension reader."}</div>
                    </div>
                  </>
                ) : <div className="blank-state compact">Select a job to inspect it.</div>}
              </section>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

function ParsedPreview({ preview, loadingExperience }) {
  if (!preview) {
    return <div className="blank-state">Generate content to see the parsed preview.</div>;
  }

  const contactLine = [preview.contact?.location, preview.contact?.phone, preview.contact?.email]
    .filter(Boolean)
    .join(" | ");

  return (
    <div className="preview-scroll">
      <section className="preview-section">
        <div className="preview-title">{preview.title || ""}</div>
        {contactLine ? <div className="preview-contact">{contactLine}</div> : null}
      </section>

      {preview.summary ? (
        <section className="preview-section">
          <h3 className="section-label">Summary</h3>
          <p className="preview-copy">{preview.summary || ""}</p>
        </section>
      ) : null}

      {preview.technical_skills?.length ? (
        <section className="preview-section">
          <h3 className="section-label">Technical Skills</h3>
          <div className="skill-list">
            {preview.technical_skills.map((skill) => (
              <div key={skill.category} className="skill-row editable-row">
                <strong>{skill.category}:</strong>
                <span className="skill-row-text">{skill.items || ""}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {loadingExperience ? (
        <section className="preview-section">
          <h3 className="section-label">Professional Experience</h3>
          <div className="preview-loading-state">Professional experience is still generating...</div>
        </section>
      ) : preview.experience?.length ? (
        <section className="preview-section">
          <h3 className="section-label">Professional Experience</h3>
          <div className="experience-list">
            {preview.experience.map((item) => (
              <article key={`${item.company}-${item.dates}`} className="experience-card">
                <div className="experience-company">{item.company} | {item.dates}</div>
                <div className="experience-title-text">{item.title || ""}</div>
                <div className="experience-bullets">
                  {(item.bullets || []).map((bullet, index) => (
                    <div key={index} className="experience-bullet editable-row">
                      <span>•</span>
                      <span className="experience-bullet-text">{bullet}</span>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function normalizeExperienceHistory(history = []) {
  return Array.isArray(history)
    ? history.map((item) => ({
        key: item?.key || "",
        company: item?.company || "",
        location: item?.location || "",
        title: item?.title || "",
        dates: item?.dates || "",
        enabled: item?.enabled !== false,
      }))
    : [];
}

function normalizeInlineExperienceHistory(history = []) {
  return Array.isArray(history)
    ? history.map((item, index) => ({
        key: item?.key || experienceKeys[index] || `role-${index + 1}`,
        company: item?.company || "",
        location: item?.location || "",
        title: item?.title || "",
        dates: item?.dates || "",
        enabled: item?.enabled !== false,
      }))
    : [];
}

function isExperienceHistoryComplete(item) {
  const entry = item || {};
  return ["company", "location", "title", "dates"].every((field) => String(entry[field] || "").trim());
}

function isExperienceHistoryEnabled(item) {
  return !!(item?.enabled !== false && isExperienceHistoryComplete(item));
}

function locationMentionsIndia(value = "") {
  return /\b(india|karnataka|bangalore|bengaluru|hyderabad|chennai|pune|mumbai|delhi|gurugram|gurgaon|noida)\b/i.test(String(value || ""));
}

function locationMentionsUnitedStates(value = "") {
  const location = String(value || "");
  return /\b(united states|usa|u\.s\.a\.|u\.s\.|us)\b/i.test(location)
    || /\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|IA|ID|IL|IN|KS|KY|LA|MA|MD|ME|MI|MN|MO|MS|MT|NC|ND|NE|NH|NJ|NM|NV|NY|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VA|VT|WA|WI|WV|WY)\b/.test(location);
}

function allEnabledExperienceKeys(history = [], resumeModeValue = "professional") {
  let entries = normalizeInlineExperienceHistory(history)
    .filter((item) => isExperienceHistoryEnabled(item));
  if (normalizeResumeMode(resumeModeValue) === "internship") {
    entries = entries
      .filter((item) => !locationMentionsIndia(item.location) && locationMentionsUnitedStates(item.location))
      .slice(0, 2);
  }
  return entries
    .map((item) => item.key)
    .filter(Boolean);
}

function sanitizeEnabledExperienceKeys(history = [], selectedKeys = [], resumeModeValue = "professional") {
  const orderedEnabledKeys = allEnabledExperienceKeys(history, resumeModeValue);
  if (!orderedEnabledKeys.length) return [];

  const selectedSet = new Set((selectedKeys || []).filter(Boolean));
  const filteredKeys = orderedEnabledKeys.filter((key) => selectedSet.has(key));
  return filteredKeys.length ? filteredKeys : orderedEnabledKeys;
}

function selectedExperienceHistory(history = [], enabledKeys = []) {
  const normalized = normalizeInlineExperienceHistory(history);
  if (!Array.isArray(enabledKeys) || !enabledKeys.length) return normalized;
  const byKey = new Map(normalized.map((item) => [item.key, item]));
  return enabledKeys.map((key) => byKey.get(key)).filter(Boolean);
}

function experienceHistoryForContent(content, history = [], enabledKeys = []) {
  const normalized = normalizeInlineExperienceHistory(history);
  const selected = selectedExperienceHistory(normalized, enabledKeys);
  const lines = String(content || "").split("\n");
  const headers = lines
    .map((line) => line.trim())
    .filter((line, index) => {
      if (!line || line.startsWith("•") || !line.includes("|")) return false;
      let nextIndex = index + 1;
      while (nextIndex < lines.length && !lines[nextIndex].trim()) nextIndex += 1;
      const nextLine = lines[nextIndex]?.trim() || "";
      return !!nextLine && !nextLine.startsWith("•") && nextLine.includes("|");
    });
  if (!headers.length) return selected;

  const normalizeCompany = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
  const byCompany = new Map(
    normalized
      .map((role) => [normalizeCompany(role.company), role])
      .filter(([company]) => company),
  );
  const fallback = headers.length > selected.length ? normalized : selected;
  const usedKeys = new Set();

  return headers.map((header) => {
    const company = normalizeCompany(header.split("|", 1)[0]);
    let role = byCompany.get(company);
    if (role && usedKeys.has(role.key)) role = null;
    if (!role) role = fallback.find((item) => !usedKeys.has(item.key));
    if (role) usedKeys.add(role.key);
    return role;
  }).filter(Boolean);
}

function deriveExperienceHistoryFromContent(content, history = [], enabledKeys = []) {
  const normalizedHistory = normalizeInlineExperienceHistory(history);
  const text = String(content || "");
  if (!text.trim() || !normalizedHistory.length) return normalizedHistory;

  const lines = text.split("\n");
  const experienceIndex = lines.findIndex((line) => {
    const trimmed = line.trim().toLowerCase();
    return trimmed === "professional experience" || trimmed === "modified experience";
  });
  if (experienceIndex === -1) return normalizedHistory;

  const nextHistory = normalizedHistory.map((item) => ({ ...item }));
  const selectedHistory = experienceHistoryForContent(text, normalizedHistory, enabledKeys);
  let roleCursor = 0;

  for (let index = experienceIndex + 1; index < lines.length && roleCursor < selectedHistory.length; index += 1) {
    const companyLine = lines[index]?.trim() || "";
    if (!companyLine || companyLine.startsWith("•")) continue;
    if (!companyLine.includes("|")) continue;

    let titleIndex = index + 1;
    while (titleIndex < lines.length && !(lines[titleIndex] || "").trim()) {
      titleIndex += 1;
    }
    if (titleIndex >= lines.length) break;

    const titleLine = lines[titleIndex].trim();
    if (!titleLine || titleLine.startsWith("•") || !titleLine.includes("|")) continue;

    const [companyPart, ...locationParts] = companyLine.split("|");
    const [titlePart, ...dateParts] = titleLine.split("|");
    const selectedRole = selectedHistory[roleCursor];
    const role = nextHistory.find((item) => item.key === selectedRole.key);
    if (!role) continue;
    role.company = companyPart.trim() || role.company;
    role.location = locationParts.join("|").trim() || role.location;
    role.title = titlePart.trim() || role.title;
    role.dates = dateParts.join("|").trim() || role.dates;

    roleCursor += 1;
    index = titleIndex;
  }

  return nextHistory;
}

function experienceHistoryEquals(left = [], right = []) {
  const a = normalizeInlineExperienceHistory(left);
  const b = normalizeInlineExperienceHistory(right);
  if (a.length !== b.length) return false;
  return a.every((item, index) => {
    const other = b[index] || {};
    return ["key", "company", "location", "title", "dates", "enabled"].every(
      (field) => String(item[field] ?? "") === String(other[field] ?? ""),
    );
  });
}

function applyExperienceHistoryToGeneratedContent(content, history = [], enabledKeys = []) {
  const text = String(content || "");
  const normalizedHistory = normalizeInlineExperienceHistory(history);
  if (!text.trim() || !normalizedHistory.length) return text;

  const lines = text.split("\n");
  const experienceIndex = lines.findIndex((line) => line.trim().toLowerCase() === "professional experience");
  if (experienceIndex === -1) return text;

  const updatedLines = [...lines];
  const selectedHistory = experienceHistoryForContent(text, normalizedHistory, enabledKeys);
  let roleCursor = 0;

  for (let index = experienceIndex + 1; index < updatedLines.length && roleCursor < selectedHistory.length; index += 1) {
    const currentLine = updatedLines[index];
    const trimmed = currentLine.trim();
    if (!trimmed || trimmed.startsWith("•")) continue;

    let nextIndex = index + 1;
    while (nextIndex < updatedLines.length && !updatedLines[nextIndex].trim()) {
      nextIndex += 1;
    }
    if (nextIndex >= updatedLines.length) break;

    const nextTrimmed = updatedLines[nextIndex].trim();
    if (!trimmed.includes("|") || !nextTrimmed.includes("|") || nextTrimmed.startsWith("•")) {
      continue;
    }

    const role = selectedHistory[roleCursor];
    const currentParts = currentLine.split("|");
    const existingLocation = currentParts.slice(1).join("|").trim();
    const nextParts = updatedLines[nextIndex].split("|");
    const existingTitle = nextParts[0].trim();
    const existingDates = nextParts.slice(1).join("|").trim();

    updatedLines[index] = `${(role.company || currentParts[0].trim()).trim()} | ${(role.location || existingLocation).trim()}`;
    updatedLines[nextIndex] = `${(role.title || existingTitle).trim()} | ${(role.dates || existingDates).trim()}`;

    roleCursor += 1;
    index = nextIndex;
  }

  return updatedLines.join("\n");
}

function normalizeIdentityProfiles(identities = []) {
  return Array.isArray(identities)
    ? identities.map((item, index) => ({
        id: item?.id || `identity-${index + 1}`,
        label: item?.label || `Identity ${index + 1}`,
        location: item?.location || "",
        phone: item?.phone || "",
        email: item?.email || "",
        format_profile: item?.format_profile || "outlook",
      }))
    : [];
}

function defaultIdentityId(settingsLike = {}, identities = []) {
  const configured = String(settingsLike.default_identity_id || "").trim();
  return identities.some((item) => item.id === configured) ? configured : (identities[0]?.id || "");
}

function createEmptyIdentity() {
  return {
    id: `identity-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    label: "New identity",
    location: "",
    phone: "",
    email: "",
    format_profile: "outlook",
  };
}

function Modal({ open, title, onClose, children, footer }) {
  if (!open) return null;
  return (
    <div className="modal-shell" role="dialog" aria-modal="true">
      <button className="modal-backdrop" onClick={onClose} aria-label="Close modal" />
      <div className="modal-card">
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
}

function formatProjects(projects) {
  return (projects || [])
    .map((project) => {
      const bullets = (project.bullets || []).map((bullet) => `- ${bullet}`).join("\n");
      return [project.name || "", bullets].filter(Boolean).join("\n");
    })
    .filter(Boolean)
    .join("\n\n");
}

function parseProjects(text) {
  return text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => {
      const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
      const name = lines.shift() || "";
      const bullets = lines.map((line) => line.replace(/^[-•●]\s*/, "").trim()).filter(Boolean);
      return { name, bullets };
    })
    .filter((project) => project.name);
}

const initialAuditState = {
  status: "not_started",
  result: null,
  proposal: null,
  baseHash: "",
  baseRevision: null,
  error: "",
};

const emptyResumeVersions = {
  original: null,
  luna_reviewed: null,
  manual: null,
};

function normalizeResumeVersionEntry(entry) {
  if (!entry || typeof entry !== "object") return null;
  const resume = entry.resume && typeof entry.resume === "object"
    ? entry.resume
    : (entry.canonical && typeof entry.canonical === "object" ? entry.canonical : null);
  const resumeContent = String(entry.resume_content || entry.content || "");
  const resumeSnapshot = entry.resume_snapshot && typeof entry.resume_snapshot === "object"
    ? entry.resume_snapshot
    : (entry.snapshot && typeof entry.snapshot === "object" ? entry.snapshot : null);
  if (!resume && !resumeContent.trim() && !resumeSnapshot) return null;
  return {
    ...entry,
    resume,
    resume_content: resumeContent,
    resume_snapshot: resumeSnapshot,
  };
}

function resumeVersionStateFromPayload(payload = {}) {
  const source = payload.resume_versions && typeof payload.resume_versions === "object"
    ? payload.resume_versions
    : {};
  const versions = {
    original: normalizeResumeVersionEntry(source.original),
    luna_reviewed: normalizeResumeVersionEntry(source.luna_reviewed),
    manual: normalizeResumeVersionEntry(source.manual),
  };
  const requestedActive = String(payload.active_resume_version || "");
  const active = versions[requestedActive]
    ? requestedActive
    : (versions.manual ? "manual" : (versions.luna_reviewed ? "luna_reviewed" : (versions.original ? "original" : "")));
  return { versions, active };
}

function resumeVersionPreview(entry, experienceHistory = [], contact = {}) {
  if (!entry) return null;
  const snapshot = entry.resume_snapshot;
  if (snapshot && (snapshot.title || snapshot.summary || snapshot.experience || snapshot.technical_skills)) {
    return snapshot;
  }

  const resume = entry.resume || {};
  const experience = resume.experience && typeof resume.experience === "object"
    ? resume.experience
    : {};
  const history = normalizeInlineExperienceHistory(experienceHistory);
  return {
    title: resume.updated_title || resume.title || "",
    summary: resume.updated_summary || resume.summary || "",
    contact,
    technical_skills: (resume.updated_skills || resume.technical_skills || []).map((skill) => ({
      category: skill.category || "Skills",
      items: Array.isArray(skill.items) ? skill.items.join(", ") : String(skill.items || ""),
    })),
    experience: history
      .filter((role) => experience[role.key])
      .map((role) => ({
        company: role.company || role.key,
        location: role.location || "",
        dates: role.dates || "",
        title: experience[role.key]?.title || role.title || "",
        bullets: Array.isArray(experience[role.key]?.bullets) ? experience[role.key].bullets : [],
      })),
  };
}

const staleableAuditStatuses = new Set([
  "approved",
  "applied",
  "kept_current",
  "changes_suggested",
  "manual_attention",
  "technical_failed",
]);

const unresolvedAuditStatuses = new Set([
  "running",
  "reviewing",
  "changes_suggested",
  "manual_attention",
  "technical_failed",
  "stale",
]);

const reviewGuidanceStatuses = new Set([
  "manual_attention",
  "technical_failed",
  "stale",
]);

function auditStateFromPayload(payload = {}, fallbackStatus = "not_started") {
  const result = payload.audit_result || payload.audit || null;
  const status = payload.audit_status || result?.decision || fallbackStatus;
  return {
    status,
    result,
    proposal: payload.audit_proposal || result?.changes || null,
    baseHash: payload.audit_base_hash || result?.base_hash || "",
    baseRevision: payload.audit_base_revision ?? payload.resume_revision ?? null,
    error: status === "technical_failed" ? (result?.error || payload.error || "Quality review failed.") : "",
  };
}

function formatAuditSkills(skills = []) {
  return (Array.isArray(skills) ? skills : [])
    .map((item) => {
      const items = Array.isArray(item?.items) ? item.items.join(", ") : String(item?.items || "");
      return `${item?.category || "Skills"}: ${items}`;
    })
    .join("\n");
}

function auditStatusCopy(audit) {
  const count = Array.isArray(audit.result?.review_groups) ? audit.result.review_groups.length : 0;
  const copy = {
    running: ["Reviewing", "Checking resume quality..."],
    reviewing: ["Reviewing", "Checking resume quality..."],
    approved: ["Passed", "Quality review passed."],
    changes_suggested: ["Review ready", `${count} ${count === 1 ? "change" : "changes"} recorded by Luna.`],
    manual_attention: ["Manual attention", "A blocking issue needs an editor change."],
    technical_failed: ["Review failed", audit.error || "The review service could not finish."],
    stale: ["Review stale", "The resume changed. Run the review again."],
    kept_current: ["Kept current", "Current resume kept after review."],
    applied: ["Luna reviewed", "Validated quality changes were applied automatically."],
  };
  return copy[audit.status] || ["Not reviewed", "Quality review has not run."];
}

function formatAuditFindingPath(path, history = []) {
  const normalizedPath = String(path || "").trim();
  const topLevelLabels = {
    updated_title: "Top resume title",
    updated_summary: "Summary",
    updated_skills: "Technical skills",
  };
  if (topLevelLabels[normalizedPath]) return topLevelLabels[normalizedPath];

  const match = normalizedPath.match(/^experience\.([^.]+)\.(title|bullets(?:\[(\d+)\])?)$/);
  if (!match) {
    return normalizedPath
      .replace(/\[(\d+)\]/g, (_, index) => ` ${Number(index) + 1}`)
      .replace(/[._-]+/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Resume";
  }

  const role = normalizeInlineExperienceHistory(history).find((item) => item.key === match[1]);
  const company = role?.company || match[1];
  if (match[2] === "title") return `${company} role title`;
  return `${company} bullet ${Number(match[3] || 0) + 1}`;
}

function AuditChangeReview({ audit, loading, onOpenEditor, onRetry }) {
  const result = audit.result || {};
  const reviewGroups = Array.isArray(result.review_groups) ? result.review_groups : [];
  const findings = Array.isArray(result.manual_findings) ? result.manual_findings : [];
  const reviewBasis = result.review_basis && typeof result.review_basis === "object"
    ? result.review_basis
    : {};
  const nonBlockingGaps = Array.isArray(result.non_blocking_gaps)
    ? result.non_blocking_gaps
    : [];
  const resumeEvidenceGaps = nonBlockingGaps.filter((gap) => ![
    "domain_context", "application_condition", "credential_or_duration",
  ].includes(String(gap?.kind || "")));
  const valueText = (value) => {
    if (Array.isArray(value)) {
      return value.map((item) => (
        item && typeof item === "object"
          ? (item.skill || item.new_bullet || JSON.stringify(item))
          : String(item)
      )).join("\n");
    }
    if (value && typeof value === "object") {
      if (value.skill) return value.category ? `${value.category}: ${value.skill}` : String(value.skill);
      if (Array.isArray(value.skills)) {
        return value.category ? `${value.category}: ${value.skills.join(", ")}` : value.skills.join(", ");
      }
      return Object.values(value).filter(Boolean).join(": ");
    }
    return String(value || "");
  };
  const labelFor = (group) => {
    if (group.section === "top_title") return "Top title";
    if (group.section === "summary") return "Summary";
    if (group.section === "experience_title") return `${group.company || group.role_key} title`;
    if (group.section === "experience") return `${group.company || group.role_key} experience`;
    if (group.section?.startsWith("skills.")) return `Skills · ${String(group.section).split(".").pop().replaceAll("_", " ")}`;
    return "Resume change";
  };

  return (
    <div className="audit-review-content">
      {result.review_summary ? <p className="audit-review-summary">{result.review_summary}</p> : null}
      {reviewBasis.normalized_market_title ? (
        <div className="audit-review-basis">
          <strong>Review target: {reviewBasis.normalized_market_title}</strong>
          {reviewBasis.advertised_job_title ? <span>Posted as {reviewBasis.advertised_job_title}</span> : null}
          {reviewBasis.title_rationale ? <p><b>Title review</b>{reviewBasis.title_rationale}</p> : null}
          <p><b>Recruiter</b>{(reviewBasis.technical_recruiter_priorities || []).join(" · ")}</p>
          <p><b>Hiring manager</b>{(reviewBasis.hiring_manager_priorities || []).join(" · ")}</p>
          <p><b>Principal engineer</b>{(reviewBasis.principal_engineer_priorities || []).join(" · ")}</p>
        </div>
      ) : null}
      {audit.status === "manual_attention" ? (
        <div className="audit-guidance-message">
          <strong>A safe automatic repair was not available.</strong>
          <p>Review the findings, update the affected content, and run the review again.</p>
          <button className="primary-button compact-button" onClick={onOpenEditor}>Open Editor</button>
        </div>
      ) : null}
      {audit.status === "technical_failed" ? (
        <div className="audit-guidance-message">
          <strong>{audit.error || "The quality review could not finish."}</strong>
          <button className="secondary-button compact-button" disabled={loading} onClick={onRetry}>{loading ? "Reviewing..." : "Retry Review"}</button>
        </div>
      ) : null}
      {audit.status === "stale" ? (
        <div className="audit-guidance-message">
          <strong>This review is out of date.</strong>
          <p>The resume changed after the review. Review your edits, then run the quality review again.</p>
        </div>
      ) : null}
      {findings.length ? (
        <div className="audit-findings">
          {findings.map((finding, index) => (
            <div key={finding.id || index} className="audit-finding">
              <span className="audit-finding-path">
                {formatAuditFindingPath(finding.path, audit.history || [])}
                {finding.path ? <code>{finding.path}</code> : null}
              </span>
              <strong>{finding.problem || "Review finding"}</strong>
              {finding.recommendation ? <span>{finding.recommendation}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
      {reviewGroups.length ? reviewGroups.map((group) => (
        <section className="audit-change" key={group.change_id} data-change-id={group.change_id}>
          <div className="audit-change-heading">
            <h3>{labelFor(group)}</h3>
          </div>
          <div className="audit-change-grid">
            <div>
              <span className="audit-change-label">Remove</span>
              <p>{valueText(group.current) || "Not present"}</p>
            </div>
            <div>
              <span className="audit-change-label">Add</span>
              <p>{valueText(group.proposed) || "Not present"}</p>
            </div>
          </div>
          <p className="audit-change-reason">{group.reason}</p>
          {Array.isArray(group.supported_by) && group.supported_by.length ? (
            <div className="audit-reviewer-support">
              {group.supported_by.map((reviewer) => (
                <span key={reviewer}>{reviewer.replaceAll("_", " ")}</span>
              ))}
            </div>
          ) : null}
        </section>
      )) : audit.status === "changes_suggested" ? (
        <div className="blank-state compact">No section-level changes were returned.</div>
      ) : null}
      {resumeEvidenceGaps.length ? (
        <div className="audit-non-blocking-gaps">
          <strong>Requirements not supported by profile evidence</strong>
          {resumeEvidenceGaps.map((gap, index) => (
            <p key={gap.id || index}>
              <b>{gap.gap || "Unsupported requirement"}</b>
              {gap.impact ? ` ${gap.impact}` : ""}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatDateShort(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatDateTimeShort(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function daysSince(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
}

function dateValueForCompare(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString().slice(0, 10);
}

function TrackerBoard({ applications, statuses, onStatusChange, onPreview, onOpenFile }) {
  return (
    <div className="tracker-board">
      {statuses.map((status) => {
        const items = applications.filter((item) => item.status === status);
        return (
          <section key={status} className="tracker-column">
            <div className="tracker-column-header">
              <span>{status}</span>
              <span className="badge">{items.length}</span>
            </div>
            <div className="tracker-card-list">
              {items.length ? items.map((item) => (
                <article key={item.id} className="tracker-card">
                  <div className="tracker-card-top">
                    <div>
                      <div className="tracker-card-company">{item.company_name}</div>
                      <div className="tracker-card-role">{item.role_title}</div>
                    </div>
                    {item.role_family ? <span className="badge">{item.role_family}</span> : null}
                  </div>
                  <div className="tracker-card-meta">
                    <span>Applied {formatDateShort(item.applied_date)}</span>
                    <span>Updated {formatDateShort(item.status_updated_date || item.last_updated_date)}</span>
                  </div>
                  {item.folder_group ? (
                    <div className="tracker-card-meta">
                      <span>Folder group: {item.folder_group}</span>
                    </div>
                  ) : null}
                  <div className="tracker-card-meta">
                    <span>{daysSince(item.applied_date) ?? 0}d since apply</span>
                    <span>{daysSince(item.status_updated_date || item.last_updated_date) ?? 0}d since update</span>
                  </div>
                  <div className="tracker-card-actions">
                    <select value={item.status} onChange={(e) => onStatusChange(item.id, e.target.value)}>
                      {statuses.map((option) => <option key={option} value={option}>{option}</option>)}
                    </select>
                    <button className="secondary-button tracker-action-button" onClick={() => onPreview(item)}>Resume Preview</button>
                    <button className="secondary-button tracker-action-button" onClick={() => onOpenFile(item)}>Go to File</button>
                  </div>
                </article>
              )) : (
                <div className="tracker-empty-column">No applications</div>
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function TrackerTable({ applications, statuses, onStatusChange, onPreview, onOpenFile }) {
  return (
    <div className="tracker-table-shell">
      <table className="tracker-table">
        <thead>
          <tr>
            <th>Company</th>
            <th>Role</th>
            <th>Status</th>
            <th>Applied</th>
            <th>Last Update</th>
            <th>Since Apply</th>
            <th>Since Update</th>
            <th>Resume</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {applications.length ? applications.map((item) => (
            <tr key={item.id}>
              <td>
                <div className="tracker-table-company">{item.company_name}</div>
                {item.role_family ? <div className="tracker-table-subtle">{item.role_family}</div> : null}
                {item.folder_group ? <div className="tracker-table-subtle">Folder group: {item.folder_group}</div> : null}
              </td>
              <td>{item.role_title}</td>
              <td>
                <select value={item.status} onChange={(e) => onStatusChange(item.id, e.target.value)}>
                  {statuses.map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              </td>
              <td>{formatDateShort(item.applied_date)}</td>
              <td>{formatDateShort(item.status_updated_date || item.last_updated_date)}</td>
              <td>{daysSince(item.applied_date) ?? "—"}d</td>
              <td>{daysSince(item.status_updated_date || item.last_updated_date) ?? "—"}d</td>
              <td>{item.resume_snapshot?.title || item.target_role || "Locked"}</td>
              <td>
                <div className="tracker-table-actions">
                  <button className="secondary-button tracker-action-button" onClick={() => onPreview(item)}>Preview</button>
                  <button className="secondary-button tracker-action-button" onClick={() => onOpenFile(item)}>File</button>
                </div>
              </td>
            </tr>
          )) : (
            <tr>
              <td colSpan={9} className="tracker-empty-row">No applications tracked yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function PriorApplicationsList({ history }) {
  const applications = Array.isArray(history?.applications) ? history.applications : [];
  if (!applications.length) return null;
  return (
    <div className="prior-applications-list">
      {applications.map((item) => (
        <article key={item.id || `${item.company_name}-${item.applied_date}-${item.resume_title}`} className="prior-application-card">
          <div className="prior-application-title">{item.resume_title || item.role_title || "Resume"}</div>
          <div className="prior-application-meta">Applied: {item.applied_date || "Unknown date"}</div>
          <div className="prior-application-meta">Status: {item.status || "Applied"}</div>
          {item.folder_group ? <div className="prior-application-meta">Folder group: {item.folder_group}</div> : null}
        </article>
      ))}
    </div>
  );
}

export default function App() {
  const jobInboxMode = window.location.pathname.startsWith("/jobs");
  const [extensionDraftId] = useState(() => new URLSearchParams(window.location.search).get("draft") || "");
  const [extensionReviewRequested] = useState(() => new URLSearchParams(window.location.search).get("review") === "1");
  const [extensionDraftLocked, setExtensionDraftLocked] = useState(false);
  const [extensionDraftSaveState, setExtensionDraftSaveState] = useState("");
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [profile, setProfile] = useState(emptyProfile);
  const [profileDraft, setProfileDraft] = useState(emptyProfile);
  const [onboardingRequired, setOnboardingRequired] = useState(false);
  const [sessionProfileActive, setSessionProfileActive] = useState(false);
  const [settings, setSettings] = useState({ output_directory: "", identities: [], default_identity_id: "", allow_security_clearance_jobs: false });
  const [settingsDraft, setSettingsDraft] = useState({ output_directory: "", identities: [], default_identity_id: "", allow_security_clearance_jobs: false });
  const [pdfStatus, setPdfStatus] = useState({ ready: false, message: "Checking..." });
  const [aiStatus, setAiStatus] = useState({ ready: false, message: "Checking...", model: "gpt-5-mini", memory_limit: 2 });
  const [identity, setIdentity] = useState("");
  const [resumeMode, setResumeMode] = useState("professional");
  const [contact, setContact] = useState({ location: "", phone: "", email: "" });
  const [editableExperienceHistory, setEditableExperienceHistory] = useState([]);
  const [enabledExperienceKeys, setEnabledExperienceKeys] = useState([]);
  const [companyName, setCompanyName] = useState("");
  const [composerInput, setComposerInput] = useState("");
  const [resumeJobContext, setResumeJobContext] = useState(null);
  const [generatedContent, setGeneratedContent] = useState("");
  const [audit, setAudit] = useState(initialAuditState);
  const [auditActionLoading, setAuditActionLoading] = useState(false);
  const [resumeVersions, setResumeVersions] = useState(emptyResumeVersions);
  const [activeResumeVersion, setActiveResumeVersion] = useState("");
  const [resumeVersionView, setResumeVersionView] = useState("");
  const [preview, setPreview] = useState(null);
  const [validation, setValidation] = useState({ valid: false, errors: [] });
  const [tab, setTab] = useState("parsed");
  const [aiSessionId, setAiSessionId] = useState(null);
  const [lastGeneratedJd, setLastGeneratedJd] = useState("");
  const [memoryCount, setMemoryCount] = useState(0);
  const [aiThread, setAiThread] = useState([]);
  const [aiError, setAiError] = useState("");
  const [aiPreflight, setAiPreflight] = useState(null);
  const [showGeneratedArea, setShowGeneratedArea] = useState(false);
  const [latestAnalysis, setLatestAnalysis] = useState(null);
  const [generatingAi, setGeneratingAi] = useState(false);
  const [reachoutLoading, setReachoutLoading] = useState(false);
  const [followupLoading, setFollowupLoading] = useState(false);
  const [aiStage, setAiStage] = useState("");
  const [previewEditMode, setPreviewEditMode] = useState(false);
  const [pdfState, setPdfState] = useState({
    mode: "idle",
    error: "",
    statusPath: "",
    pdfPath: "",
    outputDir: "",
    statusLabel: "",
  });
  const [modals, setModals] = useState({
    instructions: false,
    settings: false,
    profile: false,
    tracker: false,
    trackApply: false,
    qualityReview: false,
    outreach: false,
  });
  const [trackerData, setTrackerData] = useState({ applications: [], summary: { counts: {}, total: 0 }, statuses: ["Applied", "Updated", "Converted", "Ghosted", "Rejected"] });
  const [trackerLoading, setTrackerLoading] = useState(false);
  const [trackerError, setTrackerError] = useState("");
  const [trackerView, setTrackerView] = useState("board");
  const [trackerFilters, setTrackerFilters] = useState({
    query: "",
    applied_from: "",
    applied_to: "",
  });
  const [trackerPreview, setTrackerPreview] = useState({ open: false, application: null });
  const [trackApplyDraft, setTrackApplyDraft] = useState({
    applied_date: new Date().toISOString().slice(0, 10),
    source: "",
    job_url: "",
    notes: "",
    status: "Applied",
  });
  const [companyHistoryDecision, setCompanyHistoryDecision] = useState({
    open: false,
    history: null,
    pending: null,
  });
  const [outreachData, setOutreachData] = useState({
    leads: [],
    summary: { counts: {}, total: 0 },
    statuses: outreachStatuses,
    source_types: outreachSourceTypes,
  });
  const [outreachLoading, setOutreachLoading] = useState(false);
  const [outreachError, setOutreachError] = useState("");
  const [outreachFilters, setOutreachFilters] = useState({ query: "", status: "" });
  const [outreachDraft, setOutreachDraft] = useState(createEmptyOutreachDraft);
  const [editingOutreachId, setEditingOutreachId] = useState("");
  const [outreachMessage, setOutreachMessage] = useState(null);
  const [outreachImportText, setOutreachImportText] = useState("");

  const mediaRecorderRef = useRef(null);
  const mediaChunksRef = useRef([]);
  const streamRef = useRef(null);
  const previewRequestSeqRef = useRef(0);
  const extensionDraftHydratedRef = useRef(false);
  const extensionDraftLastSavedRef = useRef("");
  const extensionReviewAutoOpenedRef = useRef(false);
  const auditStaleSuppressionRef = useRef(false);
  const previewEditorRef = useRef(null);
  const focusPreviewEditorRef = useRef(false);
  const [recordingTarget, setRecordingTarget] = useState("");

  function invalidatePdfState() {
    setPdfState({ mode: "idle", error: "", statusPath: "", pdfPath: "", outputDir: "", statusLabel: "" });
  }

  function runWithoutAuditStale(callback) {
    auditStaleSuppressionRef.current = true;
    try {
      callback();
    } finally {
      auditStaleSuppressionRef.current = false;
    }
  }

  function setGeneratedContentProgrammatically(content) {
    if (typeof content !== "string" || !content.trim()) return false;
    runWithoutAuditStale(() => setGeneratedContent(content));
    return true;
  }

  function resetAuditState() {
    runWithoutAuditStale(() => setAudit(initialAuditState));
  }

  function resetResumeVersionState() {
    setResumeVersions(emptyResumeVersions);
    setActiveResumeVersion("");
    setResumeVersionView("");
  }

  function hydrateResumeVersionState(payload, { syncCurrent = true } = {}) {
    const next = resumeVersionStateFromPayload(payload);
    if (!next.active) return false;
    const activeEntry = next.versions[next.active];
    setResumeVersions(next.versions);
    setActiveResumeVersion(next.active);
    setResumeVersionView(next.active);
    if (syncCurrent && activeEntry?.resume_content?.trim()) {
      setGeneratedContentProgrammatically(activeEntry.resume_content);
    }
    if (activeEntry?.resume_snapshot) {
      setPreview(activeEntry.resume_snapshot);
    }
    return true;
  }

  function markCurrentResumeAsManual() {
    if (!generatedContent.trim()) return;
    setResumeVersions((current) => {
      const base = current.manual || current.luna_reviewed || current.original || {};
      return {
        ...current,
        manual: {
          ...base,
          resume_content: generatedContent,
          resume_snapshot: preview,
        },
      };
    });
    setActiveResumeVersion("manual");
    setResumeVersionView("manual");
  }

  function hydrateAuditState(payload, fallbackStatus = "not_started") {
    runWithoutAuditStale(() => setAudit(auditStateFromPayload(payload, fallbackStatus)));
    hydrateResumeVersionState(payload);
  }

  function keepCurrentResumeAfterUserEdit() {
    if (auditStaleSuppressionRef.current || !generatedContent.trim()) {
      return;
    }
    invalidatePdfState();
    markCurrentResumeAsManual();
    if (!staleableAuditStatuses.has(audit.status)) return;
    setAudit((current) => ({
      ...current,
      status: "kept_current",
      proposal: null,
      error: "",
    }));
  }

  function hydrateExtensionEditorData(data, { announce = true } = {}) {
    const draft = data.draft || {};
    const history = normalizeExperienceHistory(draft.experience_history_snapshot || []);
    const nextAudit = auditStateFromPayload(draft);
    const nextVersions = resumeVersionStateFromPayload(draft);
    const activeVersion = nextVersions.versions[nextVersions.active];
    const activeContent = activeVersion?.resume_content || draft.resume_content || "";
    runWithoutAuditStale(() => {
      setAiSessionId(data.session_id || null);
      setLastGeneratedJd(draft.job_description || "");
      setLatestAnalysis(draft.analysis || null);
      setAiPreflight(null);
      setGeneratedContent(activeContent);
      setCompanyName(draft.company_name || "");
      setIdentity(draft.identity_id || "");
      setResumeMode(normalizeResumeMode(draft.resume_mode));
      setContact({
        location: draft.contact_snapshot?.location || "",
        phone: draft.contact_snapshot?.phone || "",
        email: draft.contact_snapshot?.email || "",
      });
      setEditableExperienceHistory(history);
      setEnabledExperienceKeys(draft.enabled_experience_keys || allEnabledExperienceKeys(history, normalizeResumeMode(draft.resume_mode)));
      setAudit(nextAudit);
      setResumeVersions(nextVersions.versions);
      setActiveResumeVersion(nextVersions.active);
      setResumeVersionView(nextVersions.active);
    });
    setResumeJobContext({
      id: "",
      draft_id: draft.id,
      title: draft.role_title || "",
      company_name: draft.company_name || "",
      job_url: draft.canonical_url || "",
    });
    setPreview(activeVersion?.resume_snapshot || draft.preview || draft.resume_snapshot || null);
    setShowGeneratedArea(!!activeContent);
    setExtensionDraftLocked(!!draft.locked);
    setTab(draft.status === "pdf_ready" ? "pdf" : "parsed");
    setPdfState(draft.pdf_path ? {
      mode: draft.status === "pdf_ready" ? "ready" : (draft.status === "pdf_generating" ? "polling" : "idle"),
      error: "",
      statusPath: draft.pdf_status_path || "",
      pdfPath: draft.pdf_path || "",
      outputDir: draft.output_dir || "",
      statusLabel: draft.status === "pdf_ready" ? "PDF ready" : "Generating PDF...",
    } : {
      mode: "idle", error: "", statusPath: "", pdfPath: "", outputDir: "", statusLabel: "",
    });
    if (announce) {
      setAiThread([{
        kind: "assistant",
        title: draft.locked ? "Applied Resume" : "LinkedIn Draft Loaded",
        lines: [draft.locked ? "This applied resume is locked." : "Edits in this page save back to the LinkedIn side-panel draft."],
      }]);
    }
    extensionDraftLastSavedRef.current = JSON.stringify({
      content: activeContent,
      company: draft.company_name || "",
      identity: draft.identity_id || "",
      resume_mode: normalizeResumeMode(draft.resume_mode),
      enabled: draft.enabled_experience_keys || [],
      history,
    });
    if (
      extensionReviewRequested
      && !extensionReviewAutoOpenedRef.current
      && reviewGuidanceStatuses.has(nextAudit.status)
    ) {
      extensionReviewAutoOpenedRef.current = true;
      setModals((current) => ({ ...current, qualityReview: true }));
    }
  }

  useEffect(() => {
    fetchJson("/api/settings")
      .then((data) => {
        const identities = normalizeIdentityProfiles(data.identities || []);
        const default_identity_id = defaultIdentityId(data, identities);
        setSettings({ ...data, identities });
        setSettingsDraft({
          output_directory: data.output_directory || "",
          identities,
          default_identity_id,
          allow_security_clearance_jobs: !!data.allow_security_clearance_jobs,
        });
        setPdfStatus({
          ready: !!data.pdf_conversion_ready,
          message: data.pdf_conversion_status || "Unknown",
        });
      })
      .catch(() => {});

    fetchJson("/api/profile")
      .then((data) => {
        const profileData = data.profile || emptyProfile;
        setOnboardingRequired(!!data.onboarding_required);
        setSessionProfileActive(!!data.session_active);
        setProfile(profileData);
        const history = normalizeExperienceHistory(profileData.experience_history || []);
        setEditableExperienceHistory(history);
        setEnabledExperienceKeys(allEnabledExperienceKeys(history, resumeMode));
        setProfileDraft({
          ...profileData,
          contact: { ...(profileData.contact || emptyProfile.contact) },
          experience_history: history,
        });
        setContact(profileData.contact || emptyProfile.contact);
        if (data.onboarding_required) {
          setModals((current) => ({ ...current, profile: true }));
        }
      })
      .catch(() => {})
      .finally(() => setProfileLoaded(true));

    fetchJson("/api/ai/status")
      .then((data) => setAiStatus(data))
      .catch((error) => {
        setAiStatus((current) => ({ ...current, ready: false, message: error.message }));
      });

    loadTracker();
    loadOutreach();
  }, []);

  useEffect(() => {
    if (!extensionDraftId || !profileLoaded || extensionDraftHydratedRef.current) return;
    extensionDraftHydratedRef.current = true;
    fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}/editor-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then((data) => hydrateExtensionEditorData(data))
      .catch((error) => {
        extensionDraftHydratedRef.current = false;
        setAiError(error.message || "Could not load the LinkedIn resume draft.");
      });
  }, [extensionDraftId, extensionReviewRequested, profileLoaded]);

  useEffect(() => {
    if (!previewEditMode || tab !== "parsed" || !focusPreviewEditorRef.current) return;
    focusPreviewEditorRef.current = false;
    previewEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    previewEditorRef.current?.focus({ preventScroll: true });
  }, [previewEditMode, tab]);

  useEffect(() => {
    const identities = normalizeIdentityProfiles(settings.identities || []);
    if (!identities.length) {
      setIdentity("");
      setContact(emptyProfile.contact);
      return;
    }

    const preferredIdentity = defaultIdentityId(settings, identities);
    const activeIdentity = identities.find((item) => item.id === identity)
      || identities.find((item) => item.id === preferredIdentity)
      || identities[0];
    if (activeIdentity.id !== identity) {
      setIdentity(activeIdentity.id);
    }
    setContact({
      location: activeIdentity.location || "",
      phone: activeIdentity.phone || "",
      email: activeIdentity.email || "",
    });
  }, [settings.identities, settings.default_identity_id]);

  function requestPreview(nextContent = generatedContent) {
    const content = String(nextContent || "");
    if (!content.trim()) {
      setPreview(null);
      setValidation({ valid: false, errors: [] });
      return Promise.resolve(null);
    }

    const draftExperienceHistory = deriveExperienceHistoryFromContent(
      content,
      editableExperienceHistory,
      sanitizedEnabledExperienceKeys,
    );
    const requestSeq = ++previewRequestSeqRef.current;
    return fetchJson("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        contact_override: contact,
        identity,
        experience_history_override: draftExperienceHistory,
        enabled_experience_keys: sanitizedEnabledExperienceKeys,
        resume_mode: resumeMode,
      }),
    })
      .then((data) => {
        if (requestSeq !== previewRequestSeqRef.current) return data;
        setEditableExperienceHistory((current) => (
          experienceHistoryEquals(current, draftExperienceHistory) ? current : draftExperienceHistory
        ));
        setPreview(data.preview);
        setValidation({ valid: !!data.valid, errors: data.errors || [] });
        return data;
      })
      .catch((error) => {
        if (requestSeq !== previewRequestSeqRef.current) throw error;
        setValidation({ valid: false, errors: [error.message] });
        throw error;
      });
  }

  useEffect(() => {
    if (!generatedContent.trim()) {
      setPreview(null);
      setValidation({ valid: false, errors: [] });
      return;
    }

    const timeoutId = window.setTimeout(() => {
      requestPreview(generatedContent).catch(() => {});
    }, 250);

    return () => window.clearTimeout(timeoutId);
  }, [generatedContent, contact, identity, profile, editableExperienceHistory, enabledExperienceKeys, resumeMode]);

  useEffect(() => {
    if (!generatedContent.trim()) return;
    const derivedHistory = deriveExperienceHistoryFromContent(
      generatedContent,
      editableExperienceHistory,
      sanitizedEnabledExperienceKeys,
    );
    if (!experienceHistoryEquals(derivedHistory, editableExperienceHistory)) {
      setEditableExperienceHistory(derivedHistory);
    }
  }, [generatedContent]);

  useEffect(() => {
    if (activeResumeVersion !== "manual" || !generatedContent.trim()) return;
    setResumeVersions((current) => ({
      ...current,
      manual: {
        ...(current.manual || current.luna_reviewed || current.original || {}),
        resume_content: generatedContent,
        resume_snapshot: preview,
      },
    }));
  }, [activeResumeVersion, generatedContent, preview]);

  useEffect(() => {
    if (!extensionDraftId || !extensionDraftHydratedRef.current || extensionDraftLocked || !generatedContent.trim() || generatingAi) return undefined;
    const fingerprint = JSON.stringify({
      content: generatedContent,
      company: companyName,
      identity,
      resume_mode: resumeMode,
      enabled: sanitizedEnabledExperienceKeys,
      history: editableExperienceHistory,
    });
    if (fingerprint === extensionDraftLastSavedRef.current) return undefined;
    setExtensionDraftSaveState("Saving draft...");
    const timer = window.setTimeout(() => {
      extensionDraftLastSavedRef.current = fingerprint;
      fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_content: generatedContent,
          company_name: companyName,
          identity_id: identity,
          resume_mode: resumeMode,
          enabled_experience_keys: sanitizedEnabledExperienceKeys,
          experience_history: editableExperienceHistory,
        }),
      })
        .then((data) => {
          setPreview(data.draft?.preview || preview);
          if (data.draft) hydrateAuditState(data.draft, audit.status);
          setExtensionDraftSaveState("Draft saved");
          if (data.draft?.pdf_stale) {
            invalidatePdfState();
          }
        })
        .catch((error) => {
          extensionDraftLastSavedRef.current = "";
          setExtensionDraftSaveState(error.message || "Draft save failed");
        });
    }, 800);
    return () => window.clearTimeout(timer);
  }, [extensionDraftId, extensionDraftLocked, generatedContent, companyName, identity, resumeMode, enabledExperienceKeys, editableExperienceHistory, generatingAi]);

  useEffect(() => {
    if (pdfState.mode !== "polling" || !pdfState.statusPath) return undefined;

    const timer = window.setInterval(() => {
      const url = `/api/status?path=${encodeURIComponent(pdfState.statusPath)}`;
      fetchJson(url)
        .then((data) => {
          if (data.state === "completed" || data.state === "success") {
            setPdfState((current) => ({
              ...current,
              mode: "ready",
              pdfPath: data.pdf || current.pdfPath,
              statusLabel: "PDF ready",
            }));
          } else if (data.state === "failed" || data.state === "error") {
            setPdfState((current) => ({
              ...current,
              mode: "error",
              error: data.error || "PDF generation failed",
            }));
          } else {
            setPdfState((current) => ({
              ...current,
              statusLabel: data.message || "Generating PDF...",
            }));
          }
        })
        .catch((error) => {
          setPdfState((current) => ({
            ...current,
            mode: "error",
            error: error.message,
          }));
        });
    }, 1500);

    return () => window.clearInterval(timer);
  }, [pdfState.mode, pdfState.statusPath]);

  const pdfPreviewUrl = pdfState.pdfPath
    ? `/api/download?path=${encodeURIComponent(pdfState.pdfPath)}&preview=true`
    : "";

  const profileReady = !onboardingRequired;
  const reviewBlocksPdf = unresolvedAuditStatuses.has(audit.status);
  const [auditStatusLabel, auditStatusMessage] = auditStatusCopy(audit);
  const orderedDraftExperience = normalizeInlineExperienceHistory(editableExperienceHistory);
  const selectableExperienceKeys = allEnabledExperienceKeys(orderedDraftExperience, resumeMode);
  const selectableDraftExperience = orderedDraftExperience.filter((item) => selectableExperienceKeys.includes(item.key));
  const sanitizedEnabledExperienceKeys = sanitizeEnabledExperienceKeys(orderedDraftExperience, enabledExperienceKeys, resumeMode);
  function effectiveEnabledExperienceKeys(selectedKeys = enabledExperienceKeys) {
    const draftKeys = sanitizeEnabledExperienceKeys(editableExperienceHistory, selectedKeys, resumeMode);
    if (draftKeys.length) return draftKeys;
    return sanitizeEnabledExperienceKeys(profile?.experience_history || [], selectedKeys, resumeMode);
  }
  const visibleDraftExperience = selectableDraftExperience.filter((item) => sanitizedEnabledExperienceKeys.includes(item.key));
  const reviewGroups = Array.isArray(audit.result?.review_groups) ? audit.result.review_groups : [];
  const reviewFindings = Array.isArray(audit.result?.manual_findings) ? audit.result.manual_findings : [];
  const reviewGaps = Array.isArray(audit.result?.non_blocking_gaps) ? audit.result.non_blocking_gaps : [];
  const hasChangesView = !!(reviewGroups.length || reviewFindings.length || reviewGaps.length);
  const currentResumeVersionKey = resumeVersions[activeResumeVersion]
    ? activeResumeVersion
    : (resumeVersions.manual ? "manual" : (resumeVersions.luna_reviewed ? "luna_reviewed" : (resumeVersions.original ? "original" : "")));
  const viewingChanges = resumeVersionView === "changes";
  const viewingCurrentResume = !currentResumeVersionKey || resumeVersionView === currentResumeVersionKey;
  const viewingEditableResume = viewingCurrentResume && resumeVersionView !== "original" && !viewingChanges;
  const selectedResumeVersion = resumeVersions[resumeVersionView] || null;
  const selectedVersionPreview = useMemo(
    () => resumeVersionPreview(selectedResumeVersion, orderedDraftExperience, contact),
    [selectedResumeVersion, editableExperienceHistory, contact],
  );
  const displayedPreview = viewingCurrentResume ? preview : selectedVersionPreview;
  const hasVersionViews = !!(
    resumeVersions.original
    || resumeVersions.luna_reviewed
    || resumeVersions.manual
    || hasChangesView
  );
  const canGeneratePdf = validation.valid
    && generatedContent.trim().length > 0
    && !reviewBlocksPdf
    && viewingEditableResume;
  const filteredTrackerApplications = useMemo(() => {
    const query = trackerFilters.query.trim().toLowerCase();
    const from = trackerFilters.applied_from;
    const to = trackerFilters.applied_to;
    return (trackerData.applications || []).filter((item) => {
      const company = String(item.company_name || "").toLowerCase();
      const role = String(item.role_title || "").toLowerCase();
      if (query && !company.includes(query) && !role.includes(query)) {
        return false;
      }
      const applied = dateValueForCompare(item.applied_date);
      if (from && applied && applied < from) return false;
      if (to && applied && applied > to) return false;
      if ((from || to) && !applied) return false;
      return true;
    });
  }, [trackerData.applications, trackerFilters]);

  const filteredOutreachLeads = useMemo(() => {
    const query = outreachFilters.query.trim().toLowerCase();
    const status = outreachFilters.status;
    return (outreachData.leads || []).filter((item) => {
      if (status && item.status !== status) return false;
      if (!query) return true;
      return [
        item.company_name,
        item.target_role_type,
        item.contact_name,
        item.contact_role,
        item.contact_email,
        item.signal_text,
        item.product_summary,
        item.inferred_engineering_need,
        item.resume_angle,
        item.message_subject,
        item.message_body,
        item.blocked_reason,
        ...(Array.isArray(item.fit_reasons) ? item.fit_reasons : []),
      ].some((value) => String(value || "").toLowerCase().includes(query));
    });
  }, [outreachData.leads, outreachFilters]);

  useEffect(() => {
    const nextKeys = sanitizeEnabledExperienceKeys(editableExperienceHistory, enabledExperienceKeys, resumeMode);
    if (nextKeys.length === enabledExperienceKeys.length && nextKeys.every((key, index) => key === enabledExperienceKeys[index])) {
      return;
    }
    setEnabledExperienceKeys(nextKeys);
  }, [editableExperienceHistory, enabledExperienceKeys, resumeMode]);

  function openModal(name) {
    if (name === "settings") {
      fetchJson("/api/settings").then((data) => {
        const identities = normalizeIdentityProfiles(data.identities || []);
        const default_identity_id = defaultIdentityId(data, identities);
        setSettings({ ...data, identities });
        setSettingsDraft({
          output_directory: data.output_directory || "",
          identities,
          default_identity_id,
          allow_security_clearance_jobs: !!data.allow_security_clearance_jobs,
        });
      }).catch(() => {});
    }
    if (name === "profile") {
      fetchJson("/api/profile").then((data) => {
        const profileData = data.profile || emptyProfile;
        const history = normalizeExperienceHistory(profileData.experience_history || []);
        setOnboardingRequired(!!data.onboarding_required);
        setSessionProfileActive(!!data.session_active);
        setProfileDraft({
          ...profileData,
          contact: { ...(profileData.contact || emptyProfile.contact) },
          experience_history: history,
          certificationsText: (profileData.certifications || []).join("\n"),
          projectsText: formatProjects(profileData.projects || []),
        });
      }).catch(() => {});
    }
    if (name === "tracker") {
      loadTracker();
    }
    if (name === "outreach") {
      loadOutreach();
    }
    setModals((current) => ({ ...current, [name]: true }));
  }

  function closeModal(name) {
    setModals((current) => ({ ...current, [name]: false }));
  }

  function resetAiSession(clearJd = true) {
    const sessionId = aiSessionId;
    setAiSessionId(null);
    setLastGeneratedJd("");
    setMemoryCount(0);
    setAiThread([]);
    setAiError("");
    setAiPreflight(null);
    setShowGeneratedArea(false);
    setLatestAnalysis(null);
    setGeneratedContent("");
    resetAuditState();
    resetResumeVersionState();
    setAiStage("");
    setResumeJobContext(null);
    invalidatePdfState();
    setEnabledExperienceKeys(allEnabledExperienceKeys(editableExperienceHistory, resumeMode));
    if (clearJd) setComposerInput("");

    if (sessionId) {
      fetchJson("/api/ai/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      }).catch(() => {});
    }
  }

  function changeResumeMode(nextValue) {
    const nextMode = normalizeResumeMode(nextValue);
    if (nextMode === resumeMode) return;
    setResumeMode(nextMode);
    setEnabledExperienceKeys(allEnabledExperienceKeys(editableExperienceHistory, nextMode));
    if (!generatedContent.trim()) return;
    invalidatePdfState();
    if (extensionDraftId && !extensionDraftLocked) {
      setExtensionDraftSaveState("Saving draft...");
      fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_mode: nextMode }),
      })
        .then((data) => {
          if (data.draft) {
            hydrateExtensionEditorData({ draft: data.draft, session_id: aiSessionId }, { announce: false });
          }
          setExtensionDraftSaveState("Draft saved");
        })
        .catch((error) => setExtensionDraftSaveState(error.message || "Draft save failed"));
    }
  }

  function loadTracker() {
    setTrackerLoading(true);
    setTrackerError("");
    fetchJson("/api/tracker")
      .then((data) => setTrackerData({
        applications: data.applications || [],
        summary: data.summary || { counts: {}, total: 0 },
        statuses: data.statuses || ["Applied", "Updated", "Converted", "Ghosted", "Rejected"],
      }))
      .catch((error) => setTrackerError(error.message))
      .finally(() => setTrackerLoading(false));
  }

  async function submitTrackApplication() {
    if (!generatedContent.trim()) {
      setAiError("Generate a resume first before tracking an application.");
      return;
    }
    if (!companyName.trim() && !(latestAnalysis?.company_name || "").trim()) {
      setAiError("Add the company name before tracking the application.");
      return;
    }

    try {
      const data = await fetchJson("/api/tracker/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: companyName,
          job_description: lastGeneratedJd,
          resume_content: generatedContent,
          analysis: latestAnalysis || {},
          applied_date: trackApplyDraft.applied_date,
          status: trackApplyDraft.status,
          source: trackApplyDraft.source,
          job_url: trackApplyDraft.job_url,
          notes: trackApplyDraft.notes,
          job_id: resumeJobContext?.id || "",
          pdf_path: pdfState.pdfPath,
          output_dir: pdfState.outputDir,
          contact_override: contact,
          identity,
          experience_history_override: editableExperienceHistory,
          enabled_experience_keys: sanitizedEnabledExperienceKeys,
          resume_mode: resumeMode,
          resume_snapshot_override: preview,
        }),
      });
      setTrackerData((current) => ({
        applications: [data.application, ...(current.applications || [])],
        summary: data.summary || current.summary,
        statuses: current.statuses,
      }));
      closeModal("trackApply");
      setTrackApplyDraft((current) => ({ ...current, notes: "", source: "", job_url: "" }));
      openModal("tracker");
    } catch (error) {
      setAiError(error.message || "Failed to track the application.");
    }
  }

  async function updateTrackedStatus(applicationId, nextStatus) {
    try {
      const data = await fetchJson(`/api/tracker/applications/${applicationId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus, effective_date: new Date().toISOString().slice(0, 10) }),
      });
      setTrackerData((current) => ({
        applications: (current.applications || []).map((item) => item.id === applicationId ? data.application : item),
        summary: data.summary || current.summary,
        statuses: current.statuses,
      }));
    } catch (error) {
      setTrackerError(error.message || "Failed to update status.");
    }
  }

  function openTrackerPreview(application) {
    setTrackerPreview({ open: true, application });
  }

  function closeTrackerPreview() {
    setTrackerPreview({ open: false, application: null });
  }

  async function openTrackerFile(application) {
    try {
      await fetchJson(`/api/tracker/applications/${application.id}/open-file`, {
        method: "POST",
      });
    } catch (error) {
      setTrackerError(error.message || "Failed to open saved file.");
    }
  }

  function loadOutreach() {
    setOutreachLoading(true);
    setOutreachError("");
    fetchJson("/api/outreach/leads")
      .then((data) => setOutreachData({
        leads: data.leads || [],
        summary: data.summary || { counts: {}, total: 0 },
        statuses: data.statuses || outreachStatuses,
        source_types: data.source_types || outreachSourceTypes,
      }))
      .catch((error) => setOutreachError(error.message || "Failed to load outreach leads."))
      .finally(() => setOutreachLoading(false));
  }

  function updateOutreachDraft(field, value) {
    setOutreachDraft((current) => ({ ...current, [field]: value }));
  }

  function startNewOutreachLead() {
    setEditingOutreachId("");
    setOutreachDraft(createEmptyOutreachDraft());
    setOutreachMessage(null);
    setOutreachError("");
  }

  function editOutreachLead(lead) {
    setEditingOutreachId(lead.id || "");
    setOutreachDraft({
      ...createEmptyOutreachDraft(),
      ...lead,
      status: lead.status || "",
      source_type: lead.source_type || "Manual research",
      fit_score: lead.fit_score ?? "",
      fit_reasons: Array.isArray(lead.fit_reasons) ? lead.fit_reasons.join("\n") : (lead.fit_reasons || ""),
    });
    setOutreachMessage(null);
    setOutreachError("");
  }

  async function saveOutreachLead() {
    if (!outreachDraft.company_name.trim()) {
      setOutreachError("Company name is required.");
      return;
    }
    setOutreachError("");
    const isEditing = !!editingOutreachId;
    try {
      const data = await fetchJson(isEditing
        ? `/api/outreach/leads/${encodeURIComponent(editingOutreachId)}`
        : "/api/outreach/leads", {
        method: isEditing ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(outreachDraft),
      });
      setOutreachData({
        leads: data.leads || [],
        summary: data.summary || { counts: {}, total: 0 },
        statuses: data.statuses || outreachStatuses,
        source_types: data.source_types || outreachSourceTypes,
      });
      setEditingOutreachId(data.lead?.id || "");
      if (data.lead) editOutreachLead(data.lead);
    } catch (error) {
      setOutreachError(error.message || "Failed to save outreach lead.");
    }
  }

  async function importOutreachLeads() {
    const raw = outreachImportText.trim();
    if (!raw) {
      setOutreachError("Paste a JSON array or an object with a leads array.");
      return;
    }
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch (error) {
      setOutreachError("Import JSON is not valid.");
      return;
    }
    try {
      const data = await fetchJson("/api/outreach/leads/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Array.isArray(payload) ? { leads: payload } : payload),
      });
      setOutreachData({
        leads: data.leads || [],
        summary: data.summary || { counts: {}, total: 0 },
        statuses: data.statuses || outreachStatuses,
        source_types: data.source_types || outreachSourceTypes,
      });
      setOutreachImportText("");
      setOutreachError((data.errors || []).length ? `Imported ${data.created_count || 0} leads. ${data.errors.join(" ")}` : "");
    } catch (error) {
      setOutreachError(error.message || "Failed to import outreach leads.");
    }
  }

  async function deleteOutreachLead(lead) {
    if (!lead?.id) return;
    if (!window.confirm(`Remove ${lead.company_name || "this lead"} from outreach leads?`)) return;
    try {
      const data = await fetchJson(`/api/outreach/leads/${encodeURIComponent(lead.id)}`, {
        method: "DELETE",
      });
      setOutreachData({
        leads: data.leads || [],
        summary: data.summary || { counts: {}, total: 0 },
        statuses: data.statuses || outreachStatuses,
        source_types: data.source_types || outreachSourceTypes,
      });
      if (editingOutreachId === lead.id) startNewOutreachLead();
    } catch (error) {
      setOutreachError(error.message || "Failed to delete outreach lead.");
    }
  }

  async function useOutreachLeadForResume(lead) {
    if (!lead?.id) return;
    setOutreachError("");
    try {
      const data = await fetchJson(`/api/outreach/leads/${encodeURIComponent(lead.id)}/prepare-resume-context`, {
        method: "POST",
      });
      resetAiSession(false);
      updateCompanyName(data.company_name || lead.company_name || "");
      setComposerInput(data.resume_context || "");
      setResumeJobContext({
        id: lead.id,
        title: data.target_role_type || lead.target_role_type || "Startup outreach",
        company_name: data.company_name || lead.company_name || "",
        job_url: lead.source_url || lead.website || "",
        source: "startup_outreach",
      });
      setAiThread([{
        kind: "user",
        title: "Startup Outreach Lead",
        lines: [
          `Company: ${data.company_name || lead.company_name || ""}`,
          `Target: ${data.target_role_type || lead.target_role_type || "Startup outreach"}`,
          "Resume context is loaded in the input box. Send it to generate a tailored resume.",
        ],
      }]);
      setShowGeneratedArea(true);
      closeModal("outreach");
    } catch (error) {
      setOutreachError(error.message || "This lead cannot be used for resume generation.");
    }
  }

  async function loadOutreachMessage(lead) {
    if (!lead?.id) return;
    setOutreachError("");
    try {
      const data = await fetchJson(`/api/outreach/leads/${encodeURIComponent(lead.id)}/draft-message`, {
        method: "POST",
      });
      setOutreachMessage(data.message || null);
    } catch (error) {
      setOutreachError(error.message || "No stored message is available for this lead.");
    }
  }

  async function copyOutreachMessage() {
    if (!outreachMessage) return;
    try {
      await copyTextToClipboard(`Subject: ${outreachMessage.subject || ""}\n\n${outreachMessage.body || ""}`.trim());
    } catch (error) {
      setOutreachError("Could not copy the message.");
    }
  }

  async function stopRecorder() {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
  }

  async function startVoiceInput(target, setter) {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setAiError("Local voice recording is not supported in this browser.");
      return;
    }

    if (recordingTarget === target) {
      stopRecorder();
      return;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      mediaChunksRef.current = [];

      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = recorder;
      setRecordingTarget(target);
      setAiError("");

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          mediaChunksRef.current.push(event.data);
        }
      };

      recorder.onerror = () => {
        setAiError("Voice recording failed. Try again.");
        setRecordingTarget("");
      };

      recorder.onstop = async () => {
        const blob = new Blob(mediaChunksRef.current, { type: "audio/webm" });
        mediaRecorderRef.current = null;
        mediaChunksRef.current = [];
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
        }
        setRecordingTarget("");

        if (!blob.size) {
          return;
        }

        const formData = new FormData();
        formData.append("audio", blob, "speech.webm");
        formData.append("target", target);

        try {
          const data = await fetchJson("/api/transcribe", {
            method: "POST",
            body: formData,
          });
          setter((current) => (current ? `${current} ${data.text}` : data.text));
        } catch (error) {
          setAiError(error.message || "Voice transcription failed.");
        }
      };

      recorder.start();
    } catch (error) {
      setRecordingTarget("");
      setAiError("Microphone access failed.");
    }
  }

  function soulThreadEntry(analysis) {
    const keySignals = (analysis.skills_mentioned || []).slice(0, 6);
    const highlights = (analysis.responsibilities || []).slice(0, 3);
    return {
      kind: "assistant",
      title: analysis.target_role || "Role summary",
      lines: [
        `Role family: ${analysis.role_family || ""}`,
        `Soul of the role: ${analysis.core_problem || ""}`,
        `System focus: ${analysis.system_description || ""}`,
        `Key signals: ${keySignals.join(", ")}`,
      ],
      list: highlights,
    };
  }

  async function continueAiGenerationFromAnalysis({
    sessionId,
    baseThread,
    enabledKeys,
    advertisedJobTitle = "",
  }) {
    const activeEnabledKeys = effectiveEnabledExperienceKeys(enabledKeys);
    if (!activeEnabledKeys.length) {
      throw new Error("Keep at least one complete experience role enabled.");
    }
    resetAuditState();
    resetResumeVersionState();
    invalidatePdfState();
    setAiStage("skills");
    const skillsData = await fetchJson("/api/ai/generate-skills", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, enabled_experience_keys: activeEnabledKeys, resume_mode: resumeMode }),
    });
    const sessionAfterSkills = skillsData.session_id || sessionId;
    setAiSessionId(sessionAfterSkills);

    setAiStage("experience");
    await Promise.all([
      fetchJson("/api/ai/generate-experience-recent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionAfterSkills, enabled_experience_keys: activeEnabledKeys, resume_mode: resumeMode }),
      }),
      fetchJson("/api/ai/generate-experience-older", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionAfterSkills, enabled_experience_keys: activeEnabledKeys, resume_mode: resumeMode }),
      }),
    ]);

    setAiStage("final_synthesis");
    const synthesisData = await fetchJson("/api/ai/final-synthesis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionAfterSkills, enabled_experience_keys: activeEnabledKeys, resume_mode: resumeMode }),
    });
    const synthesizedSessionId = synthesisData.session_id || sessionAfterSkills;
    setAiSessionId(synthesizedSessionId);
    if (!hydrateResumeVersionState(synthesisData)) {
      setGeneratedContentProgrammatically(synthesisData.content);
    }
    setShowGeneratedArea(true);
    setComposerInput("");
    setTab("parsed");
    setPreviewEditMode(false);

    setAiStage("quality_review");
    setAudit({ ...initialAuditState, status: "reviewing" });
    let auditData = null;
    try {
      auditData = await fetchJson("/api/ai/quality-audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: synthesizedSessionId,
          enabled_experience_keys: activeEnabledKeys,
          resume_mode: resumeMode,
          advertised_job_title:
            advertisedJobTitle || resumeJobContext?.title || latestAnalysis?.target_role || "",
        }),
      });
      hydrateAuditState(auditData);
      hydrateResumeVersionState(auditData);
    } catch (error) {
      setAudit({
        ...initialAuditState,
        status: "technical_failed",
        error: error.message || "Quality review failed.",
        result: error.data?.audit_result || { error: error.message || "Quality review failed." },
      });
    }

    setAiThread((current) => {
      const next = [
        ...(current?.length ? current : baseThread),
        {
          kind: "assistant",
          title: "Resume Complete",
          lines: [auditData?.audit_status === "approved"
            ? "The resume is ready and passed quality review."
            : "The resume is ready. Check the quality review beside the preview tabs."],
        },
      ];
      if (synthesisData.title_warnings?.length) {
        next.push({
          kind: "assistant",
          title: "Experience Titles Adjusted",
          lines: ["A few historical job titles were normalized to fit the detected role family."],
          list: synthesisData.title_warnings,
        });
      }
      return next;
    });
  }

  async function submitAiGeneration() {
    const promptText = composerInput.trim();
    if (!promptText) {
      setAiError(aiSessionId ? "Enter the changes you want." : "Paste a job description first.");
      return;
    }

    const autoDetectedNewJd = !!aiSessionId && looksLikeJobDescription(promptText);
    const isNewJd = !aiSessionId || autoDetectedNewJd;
    const jd = isNewJd ? promptText : lastGeneratedJd;
    const revisionRequest = isNewJd ? "" : promptText;
    const userEntry = isNewJd
      ? { kind: "user", title: "", lines: [promptText.slice(0, 1200)] }
      : { kind: "user", title: "Changes", lines: [promptText] };
    const baseThread = isNewJd
      ? (userEntry ? [userEntry] : [])
      : [...aiThread, ...(userEntry ? [userEntry] : [])];

    setComposerInput("");
    setAiThread(baseThread);

    setGeneratingAi(true);
    setAiError("");
    setAiStage("analyzing");
    if (isNewJd) {
      resetAuditState();
      resetResumeVersionState();
      invalidatePdfState();
      if (autoDetectedNewJd) {
        setAiSessionId(null);
        setMemoryCount(0);
        setGeneratedContent("");
        setPreview(null);
        setValidation({ valid: false, errors: [] });
      }
      setCompanyName("");
      if (!resumeJobContext?.id) setResumeJobContext(null);
      setEnabledExperienceKeys(allEnabledExperienceKeys(editableExperienceHistory, resumeMode));
    }
    const activeEnabledKeys = isNewJd
      ? effectiveEnabledExperienceKeys(allEnabledExperienceKeys(editableExperienceHistory, resumeMode))
      : effectiveEnabledExperienceKeys(enabledExperienceKeys);
    if (!activeEnabledKeys.length) {
      setGeneratingAi(false);
      setAiStage("");
      setAiError("Keep at least one complete experience role enabled.");
      return;
    }

    try {
      const analyzeData = await fetchJson("/api/ai/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_description: jd,
          company_name: companyName,
          enforce_cpt_company: true,
          revision_request: revisionRequest,
          current_resume_content: generatedContent,
          session_id: aiSessionId,
          reset_memory: isNewJd,
          enabled_experience_keys: activeEnabledKeys,
          resume_mode: resumeMode,
        }),
      });

      const nextSessionId = analyzeData.session_id || aiSessionId || null;
      setAiSessionId(nextSessionId);
      setLastGeneratedJd(jd);
      setLatestAnalysis(analyzeData.analysis || null);
      setAiPreflight(analyzeData.preflight || null);
      setMemoryCount(analyzeData.memory_count || 0);
      if ((analyzeData.analysis?.company_name || "").trim()) {
        setCompanyName((current) => current.trim() || analyzeData.analysis.company_name.trim());
      }
      setAiThread([...baseThread, soulThreadEntry(analyzeData.analysis)]);
      setShowGeneratedArea(true);
      setPreviewEditMode(false);
      setTab("parsed");
      const detectedCompany = String(analyzeData.analysis?.company_name || "").trim();
      if (isNewJd && detectedCompany) {
        const historyData = await fetchJson(`/api/tracker/company-history?company=${encodeURIComponent(detectedCompany)}`);
        if ((historyData.count || 0) > 0) {
          setCompanyHistoryDecision({
            open: true,
            history: historyData,
            pending: {
              sessionId: nextSessionId,
              baseThread: [...baseThread, soulThreadEntry(analyzeData.analysis)],
              enabledKeys: activeEnabledKeys,
              advertisedJobTitle:
                resumeJobContext?.title || analyzeData.analysis?.target_role || "",
            },
          });
          setGeneratingAi(false);
          setAiStage("");
          return;
        }
      }

      await continueAiGenerationFromAnalysis({
        sessionId: nextSessionId,
        baseThread: [...baseThread, soulThreadEntry(analyzeData.analysis)],
        enabledKeys: activeEnabledKeys,
        advertisedJobTitle:
          resumeJobContext?.title || analyzeData.analysis?.target_role || "",
      });
    } catch (error) {
      const payload = error.data || {};
      if (payload.preflight) {
        setAiPreflight(payload.preflight);
      }
      if (payload.analysis) {
        setAiSessionId(payload.session_id || aiSessionId || null);
        setMemoryCount(payload.memory_count || 0);
        setAiThread([...baseThread, soulThreadEntry(payload.analysis)]);
        setShowGeneratedArea(true);
      }
      if (payload.content) {
        setGeneratedContentProgrammatically(payload.content);
        setShowGeneratedArea(true);
        setTab("parsed");
      }

      const stageNames = {
        analysis: "JD analysis failed",
        skills_generation: "Skills generation failed",
        experience_generation: "Experience generation failed",
        final_synthesis: "Final synthesis failed",
        quality_audit: "Quality review failed",
      };
      const stageLabel = stageNames[payload.stage] || "";
      const totalMs = payload.timing?.total_ms || payload.timing?.analysis_ms || payload.timing?.core_ms || payload.timing?.experience_ms;
      const timingLabel = totalMs ? ` (${Math.round(totalMs / 100) / 10}s)` : "";
      setAiError(stageLabel ? `${stageLabel}${timingLabel}: ${error.message}` : error.message);
    } finally {
      setGeneratingAi(false);
      setAiStage("");
    }
  }

  async function continueAfterCompanyHistoryDecision() {
    const pending = companyHistoryDecision.pending;
    if (!pending?.sessionId) return;
    setCompanyHistoryDecision({ open: false, history: null, pending: null });
    setGeneratingAi(true);
    setAiError("");
    try {
      await continueAiGenerationFromAnalysis(pending);
    } catch (error) {
      const payload = error.data || {};
      if (payload.content) {
        setGeneratedContentProgrammatically(payload.content);
        setShowGeneratedArea(true);
        setTab("parsed");
      }
      const stageNames = {
        analysis: "JD analysis failed",
        skills_generation: "Skills generation failed",
        experience_generation: "Experience generation failed",
        final_synthesis: "Final synthesis failed",
        quality_audit: "Quality review failed",
      };
      const stageLabel = stageNames[payload.stage] || "";
      const totalMs = payload.timing?.total_ms || payload.timing?.analysis_ms || payload.timing?.core_ms || payload.timing?.experience_ms;
      const timingLabel = totalMs ? ` (${Math.round(totalMs / 100) / 10}s)` : "";
      setAiError(stageLabel ? `${stageLabel}${timingLabel}: ${error.message}` : error.message);
    } finally {
      setGeneratingAi(false);
      setAiStage("");
    }
  }

  function cancelAfterCompanyHistoryDecision() {
    setCompanyHistoryDecision({ open: false, history: null, pending: null });
    setGeneratingAi(false);
    setAiStage("");
    setAiError("Generation paused because this company already has tracked applications.");
  }

  function markAuditActionError(error) {
    const message = error.message?.toLowerCase() || "";
    if (error.data?.audit_status === "stale" || message.includes("stale") || message.includes("changed after")) {
      setAudit((current) => ({ ...current, status: "stale", proposal: null, error: "" }));
      return;
    }
    setAudit((current) => ({
      ...current,
      status: "technical_failed",
      proposal: null,
      error: error.message || "Quality review failed.",
    }));
  }

  async function retryAudit() {
    if (!generatedContent.trim() || auditActionLoading) return;
    setAuditActionLoading(true);
    setAiError("");
    setAudit((current) => ({ ...current, status: "reviewing", proposal: null, error: "" }));
    try {
      let data;
      if (extensionDraftId) {
        const latestHistory = deriveExperienceHistoryFromContent(
          generatedContent,
          editableExperienceHistory,
          sanitizedEnabledExperienceKeys,
        );
        const saved = await fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resume_content: generatedContent,
            company_name: companyName,
            identity_id: identity,
            resume_mode: resumeMode,
            enabled_experience_keys: sanitizedEnabledExperienceKeys,
            experience_history: latestHistory,
          }),
        });
        extensionDraftLastSavedRef.current = JSON.stringify({
          content: generatedContent,
          company: companyName,
          identity,
          resume_mode: resumeMode,
          enabled: sanitizedEnabledExperienceKeys,
          history: latestHistory,
        });
        setPreview(saved.draft?.preview || saved.draft?.resume_snapshot || preview);
        data = await fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}/audit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
      } else {
        data = await fetchJson("/api/ai/quality-audit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: aiSessionId,
            enabled_experience_keys: sanitizedEnabledExperienceKeys,
            current_resume_content: generatedContent,
            resume_mode: resumeMode,
          }),
        });
      }
      const payload = data.draft || data;
      hydrateAuditState(payload);
      hydrateResumeVersionState(payload);
    } catch (error) {
      markAuditActionError(error);
    } finally {
      setAuditActionLoading(false);
    }
  }

  function openAuditEditor() {
    closeModal("qualityReview");
    if (currentResumeVersionKey === "original") {
      markCurrentResumeAsManual();
    }
    focusPreviewEditorRef.current = true;
    setTab("parsed");
    setResumeVersionView(currentResumeVersionKey === "original" ? "manual" : currentResumeVersionKey);
    setPreviewEditMode(true);
  }

  function selectResumeVersionView(versionKey) {
    setPreviewEditMode(false);
    setTab("parsed");
    setResumeVersionView(versionKey);
  }

  async function pollRegeneratedExtensionDraft(draftId) {
    const terminalStatuses = new Set(["ready", "pdf_ready", "failed"]);
    for (let attempt = 0; attempt < 60; attempt += 1) {
      if (attempt > 0) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
      }
      const data = await fetchJson(`/api/extension/drafts/${encodeURIComponent(draftId)}`);
      const draft = data.draft || {};
      if (draft.stage === "audit") setAiStage("quality_review");
      else if (draft.stage === "synthesis") setAiStage("final_synthesis");
      else if (draft.status === "generating_experience") setAiStage("experience");
      else setAiStage("skills");
      if (!terminalStatuses.has(draft.status)) continue;
      if (draft.status === "failed") {
        throw new Error(draft.error_message || "Extension draft regeneration failed.");
      }
      return draft;
    }
    throw new Error("Regeneration is still running. Reload this draft shortly to continue.");
  }

  async function regenerateResume() {
    if (!generatedContent.trim() || generatingAi) return;
    if (!window.confirm("Regenerate this resume? The current generated resume and PDF will be discarded.")) return;

    setGeneratingAi(true);
    setAiError("");
    setAiStage("skills");
    resetAuditState();
    resetResumeVersionState();
    invalidatePdfState();
    setPreviewEditMode(false);
    runWithoutAuditStale(() => setGeneratedContent(""));
    setPreview(null);
    setValidation({ valid: false, errors: [] });
    setShowGeneratedArea(true);

    try {
      if (extensionDraftId) {
        const queued = await fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}/regenerate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ resume_mode: resumeMode }),
        });
        const queuedDraft = queued.draft || {};
        if (queuedDraft.id && queuedDraft.id !== extensionDraftId) {
          throw new Error("Applied drafts regenerate as a new draft. Open the new draft from the extension.");
        }
        await pollRegeneratedExtensionDraft(extensionDraftId);
        const editorData = await fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}/editor-session`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        hydrateExtensionEditorData(editorData, { announce: false });
        setAiThread((current) => [...current, {
          kind: "assistant",
          title: "Resume Regenerated",
          lines: ["The extension draft and quality review are ready."],
        }]);
        return;
      }

      const data = await fetchJson("/api/ai/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: aiSessionId }),
      });
      const sessionId = data.session_id || aiSessionId;
      setAiSessionId(sessionId);
      setLatestAnalysis(data.analysis || latestAnalysis);
      await continueAiGenerationFromAnalysis({
        sessionId,
        baseThread: aiThread,
        enabledKeys: sanitizedEnabledExperienceKeys,
        advertisedJobTitle:
          resumeJobContext?.title || data.analysis?.target_role || latestAnalysis?.target_role || "",
      });
    } catch (error) {
      setAiError(error.message || "Could not regenerate the resume.");
    } finally {
      setGeneratingAi(false);
      setAiStage("");
    }
  }

  async function submitPdfGeneration() {
    if (!canGeneratePdf) return;

    setPdfState({
      mode: "loading",
      error: "",
      statusPath: "",
      pdfPath: "",
      outputDir: "",
      statusLabel: "Submitting...",
    });
    setTab("pdf");

    try {
      if (extensionDraftId) {
        const latestHistory = deriveExperienceHistoryFromContent(
          generatedContent,
          editableExperienceHistory,
          sanitizedEnabledExperienceKeys,
        );
        await fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resume_content: generatedContent,
            company_name: companyName,
            identity_id: identity,
            resume_mode: resumeMode,
            enabled_experience_keys: sanitizedEnabledExperienceKeys,
            experience_history: latestHistory,
          }),
        });
        const result = await fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}/pdf`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        const savedDraft = result.draft;
        setPdfState({
          mode: "polling",
          error: "",
          statusPath: savedDraft.pdf_status_path,
          pdfPath: savedDraft.pdf_path,
          outputDir: savedDraft.output_dir,
          statusLabel: "Generating PDF...",
        });
        return;
      }
      const previewData = await requestPreview(generatedContent);
      const latestPreview = previewData?.preview || preview;
      const latestHistory = deriveExperienceHistoryFromContent(
        generatedContent,
        editableExperienceHistory,
        sanitizedEnabledExperienceKeys,
      );

      const data = await fetchJson("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: generatedContent,
          ai_session_id: aiSessionId,
          company_name: companyName,
          job_id: resumeJobContext?.id || "",
          contact_override: contact,
          identity,
          experience_history_override: latestHistory,
          enabled_experience_keys: sanitizedEnabledExperienceKeys,
          resume_mode: resumeMode,
          resume_override: latestPreview,
        }),
      });

      setPdfState({
        mode: "polling",
        error: "",
        statusPath: data.status_path,
        pdfPath: data.pdf,
        outputDir: data.output_dir,
        statusLabel: "Generating PDF...",
      });
    } catch (error) {
      setPdfState({
        mode: "error",
        error: error.message,
        statusPath: "",
        pdfPath: "",
        outputDir: "",
        statusLabel: "",
      });
    }
  }

  function saveSettings() {
    const identities = normalizeIdentityProfiles(settingsDraft.identities || []);
    const default_identity_id = defaultIdentityId(settingsDraft, identities);
    fetchJson("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_directory: settingsDraft.output_directory,
        allow_security_clearance_jobs: !!settingsDraft.allow_security_clearance_jobs,
        default_identity_id,
        identities,
      }),
    })
      .then((data) => {
        const identities = normalizeIdentityProfiles(data.identities || []);
        const default_identity_id = defaultIdentityId(data, identities);
        setSettings((current) => ({
          ...current,
          output_directory: data.output_directory,
          identities,
          default_identity_id,
          allow_security_clearance_jobs: !!data.allow_security_clearance_jobs,
        }));
        setSettingsDraft({
          output_directory: data.output_directory || "",
          identities,
          default_identity_id,
          allow_security_clearance_jobs: !!data.allow_security_clearance_jobs,
        });
        closeModal("settings");
      })
      .catch((error) => window.alert(error.message));
  }

  function saveProfile(saveTarget = "session") {
    const payload = {
      name: profileDraft.name || "",
      contact: profileDraft.contact || emptyProfile.contact,
      certifications: (profileDraft.certificationsText || "")
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      projects: parseProjects(profileDraft.projectsText || ""),
      experience_history: normalizeExperienceHistory(profileDraft.experience_history || []),
    };

    fetchJson("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, save_target: saveTarget }),
    })
      .then((data) => {
        const profileData = data.profile || emptyProfile;
        setOnboardingRequired(!!data.onboarding_required);
        setSessionProfileActive(!!data.session_active);
        setProfile(profileData);
        const history = normalizeExperienceHistory(profileData.experience_history || []);
        setEditableExperienceHistory(history);
        setEnabledExperienceKeys(allEnabledExperienceKeys(history, resumeMode));
        const selected = normalizeIdentityProfiles(settings.identities || []).find((item) => item.id === identity);
        setContact(selected ? {
          location: selected.location || "",
          phone: selected.phone || "",
          email: selected.email || "",
        } : (profileData.contact || emptyProfile.contact));
        keepCurrentResumeAfterUserEdit();
        closeModal("profile");
      })
      .catch((error) => window.alert((error.data?.issues || [error.message]).join("\n")));
  }

  function updateExperienceHistory(index, field, value) {
    setProfileDraft((current) => {
      const history = normalizeExperienceHistory(current.experience_history || []);
      const nextHistory = history.map((item, itemIndex) => (
        itemIndex === index ? { ...item, [field]: value } : item
      ));
      return { ...current, experience_history: nextHistory };
    });
  }

  function toggleProfileExperienceEnabled(index) {
    setProfileDraft((current) => {
      const history = normalizeExperienceHistory(current.experience_history || []);
      const nextHistory = history.map((item, itemIndex) => (
        itemIndex === index ? { ...item, enabled: !(item.enabled !== false) } : item
      ));
      return { ...current, experience_history: nextHistory };
    });
  }

  function updateEditableExperienceHistory(index, field, value) {
    keepCurrentResumeAfterUserEdit();
    setEditableExperienceHistory((current) => {
      const nextHistory = normalizeInlineExperienceHistory(current).map((item, itemIndex) => (
        itemIndex === index ? { ...item, [field]: value } : item
      ));
      setGeneratedContent((currentContent) => applyExperienceHistoryToGeneratedContent(
        currentContent,
        nextHistory,
        sanitizedEnabledExperienceKeys,
      ));
      return nextHistory;
    });
  }

  async function togglePreviewEditMode() {
    if (previewEditMode) {
      try {
        await requestPreview(generatedContent);
      } catch (_) {
        // Validation state is already updated in requestPreview.
      }
      setPreviewEditMode(false);
      setTab("parsed");
      return;
    }
    setPreviewEditMode(true);
  }

  function toggleExperienceKey(key) {
    keepCurrentResumeAfterUserEdit();
    setEnabledExperienceKeys((current) => {
      const allowedKeys = allEnabledExperienceKeys(editableExperienceHistory, resumeMode);
      if (!allowedKeys.includes(key)) {
        return current;
      }
      const exists = current.includes(key);
      if (exists) {
        const next = current.filter((item) => item !== key);
        return next.length ? next : current;
      }
      const nextSet = new Set([...current, key]);
      return allowedKeys.filter((item) => nextSet.has(item));
    });
  }

  function selectIdentity(nextIdentity) {
    const selected = normalizeIdentityProfiles(settings.identities || []).find((item) => item.id === nextIdentity);
    keepCurrentResumeAfterUserEdit();
    setIdentity(nextIdentity);
    setContact(selected ? {
      location: selected.location || "",
      phone: selected.phone || "",
      email: selected.email || "",
    } : emptyProfile.contact);
  }

  function updateCompanyName(value) {
    keepCurrentResumeAfterUserEdit();
    setCompanyName(value);
  }

  function updateGeneratedContent(value) {
    keepCurrentResumeAfterUserEdit();
    setGeneratedContent(value);
  }

  function updateSettingsIdentity(index, field, value) {
    setSettingsDraft((current) => ({
      ...current,
      identities: normalizeIdentityProfiles(current.identities || []).map((item, itemIndex) => (
        itemIndex === index ? { ...item, [field]: value } : item
      )),
    }));
  }

  function addSettingsIdentity() {
    setSettingsDraft((current) => ({
      ...current,
      identities: [...normalizeIdentityProfiles(current.identities || []), createEmptyIdentity()],
      default_identity_id: current.default_identity_id || normalizeIdentityProfiles(current.identities || [])[0]?.id || "",
    }));
  }

  function removeSettingsIdentity(index) {
    setSettingsDraft((current) => {
      const identities = normalizeIdentityProfiles(current.identities || []);
      if (identities.length <= 1) return current;
      const nextIdentities = identities.filter((_, itemIndex) => itemIndex !== index);
      return {
        ...current,
        identities: nextIdentities,
        default_identity_id: nextIdentities.some((item) => item.id === current.default_identity_id)
          ? current.default_identity_id
          : (nextIdentities[0]?.id || ""),
      };
    });
  }


  function handleComposerKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!generatingAi && !reachoutLoading && !followupLoading) {
        submitAiGeneration();
      }
    }
  }

  async function submitReachoutMessage() {
    if (!lastGeneratedJd.trim() || !generatedContent.trim() || !aiSessionId) {
      setAiError("Generate a resume first before creating a reachout message.");
      return;
    }

    setReachoutLoading(true);
    setAiError("");

    try {
      const data = await fetchJson("/api/ai/generate-reachout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_description: lastGeneratedJd,
          current_resume_content: generatedContent,
          session_id: aiSessionId,
        }),
      });

      const reachout = data.reachout || {};
      const message = (reachout.message || "").trim();
      const charCount = Number.isFinite(reachout.char_count) ? reachout.char_count : message.length;

      setAiThread((current) => [
        ...current,
        {
          kind: "assistant",
          title: "LinkedIn Reachout",
          lines: [message, `${charCount} characters`],
        },
      ]);
    } catch (error) {
      setAiError(error.message || "Reachout generation failed.");
    } finally {
      setReachoutLoading(false);
    }
  }

  async function submitFollowupAnswer() {
    const question = composerInput.trim();
    if (!question) {
      setAiError("Type the follow-up question first.");
      return;
    }

    if (!lastGeneratedJd.trim() || !aiSessionId) {
      setAiError("Generate a resume first before answering follow-up questions.");
      return;
    }

    if (!pdfState.pdfPath) {
      setAiError("Generate the final PDF first before answering follow-up questions.");
      return;
    }

    setFollowupLoading(true);
    setAiError("");

    try {
      const data = await fetchJson("/api/ai/generate-followup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_description: lastGeneratedJd,
          question,
          pdf_path: pdfState.pdfPath,
          session_id: aiSessionId,
        }),
      });

      const answer = (data.followup?.answer || "").trim();
      setComposerInput("");
      setAiThread((current) => [
        ...current,
        {
          kind: "user",
          title: "Follow-up Question",
          lines: [question],
        },
        {
          kind: "assistant",
          title: "Follow-up Answer",
          lines: [answer],
        },
      ]);
    } catch (error) {
      setAiError(error.message || "Follow-up answer generation failed.");
    } finally {
      setFollowupLoading(false);
    }
  }

  if (jobInboxMode) {
    return (
      <div className="app-shell">
        <header className="topbar">
          <div className="brand-wrap">
            <div className="brand-dot" />
            <div className="brand">Resume Generator</div>
          </div>
          <div className="topbar-actions">
            <a className="icon-button link-button" href="/">Resume</a>
            <button className="toggle-button active">Jobs</button>
            <span className={pdfStatus.ready ? "badge status-ok" : "badge status-error"}>
              {pdfStatus.ready ? "Ready" : "PDF Error"}
            </span>
          </div>
        </header>
        <JobInbox />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-wrap">
          <div className="brand-dot" />
          <div className="brand">Resume Generator</div>
        </div>
        <div className="topbar-actions">
          <a className="icon-button link-button" href="/jobs">Jobs</a>
          <button className="icon-button" onClick={() => openModal("profile")}>{onboardingRequired ? "Setup Profile" : "Profile"}</button>
          <button className="icon-button" onClick={() => openModal("outreach")}>Outreach</button>
          <button className="icon-button" onClick={() => openModal("tracker")}>Tracker</button>
          <button className="icon-button" onClick={() => openModal("instructions")}>?</button>
          <button className="icon-button" onClick={() => openModal("settings")}>⚙</button>
          <span className={pdfStatus.ready ? "badge status-ok" : "badge status-error"}>
            {pdfStatus.ready ? "Ready" : "PDF Error"}
          </span>
        </div>
      </header>

      <div className="identity-strip">
        <div className="identity-strip-label">Contact identities</div>
        <div className="identity-pill-list">
          {normalizeIdentityProfiles(settings.identities || []).map((item) => (
            <button
              key={item.id}
              className={`toggle-button identity-pill ${identity === item.id ? "active" : ""}`}
              disabled={extensionDraftLocked}
              onClick={() => selectIdentity(item.id)}
            >
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      </div>

      <main className="workspace chatgpt-shell">
        <section className="chat-surface">
          <div className="chat-surface-header">
            <div>
              <div className="panel-eyebrow">Conversation</div>
              <div className="panel-title">JD to Resume</div>
            </div>
          </div>
          <div className="chat-scroll">
            {!showGeneratedArea ? (
              <div className="chat-intro">
                <div className="intro-card">
                  <h2>Paste a job description to start.</h2>
                  <p>We automatically treat the first message as a new JD. After the draft is created, the same input becomes your change box for that JD until you start a new one.</p>
                  {onboardingRequired ? <p>Complete profile setup first. Resume generation stays locked until the permanent profile is saved.</p> : null}
                </div>
              </div>
            ) : null}

            {aiError ? <div className="error-banner">{aiError}</div> : null}
            <CptStatusBand cpt={aiPreflight?.cpt} />

            {aiThread.map((entry, index) => (
              <ThreadCard key={`${entry.kind}-${index}`} entry={entry} />
            ))}

            {generatingAi ? (
              <div className="loading-card" aria-live="polite">
                <div className="loading-card-header">Resume Engine</div>
                <div className="loading-card-body">
                  <div className="loading-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                  <div className="loading-copy">
                    {aiStage === "analyzing"
                      ? "Analyzing the JD..."
                      : aiStage === "skills"
                        ? "Generating skills..."
                        : aiStage === "experience"
                          ? "Generating experience..."
                          : aiStage === "final_synthesis"
                            ? "Running final synthesis..."
                            : aiStage === "quality_review"
                              ? "Running quality review..."
                              : "Updating the resume..."}
                  </div>
                </div>
              </div>
            ) : null}

            {reachoutLoading ? (
              <div className="loading-card" aria-live="polite">
                <div className="loading-card-header">Resume Engine</div>
                <div className="loading-card-body">
                  <div className="loading-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                  <div className="loading-copy">Writing a short LinkedIn reachout...</div>
                </div>
              </div>
            ) : null}

            {followupLoading ? (
              <div className="loading-card" aria-live="polite">
                <div className="loading-card-header">Resume Engine</div>
                <div className="loading-card-body">
                  <div className="loading-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                  <div className="loading-copy">Writing a follow-up answer from the final PDF...</div>
                </div>
              </div>
            ) : null}

                {showGeneratedArea ? (
                  <div className="chat-block">
                    <div className="message-label">Generated Resume</div>
                  </div>
                ) : null}
          </div>
          <div className="chat-composer-shell">
            <div className="composer-card">
              <textarea
                className="composer-textarea"
                value={composerInput}
                disabled={extensionDraftLocked}
                onChange={(e) => {
                  setComposerInput(e.target.value);
                  setResumeJobContext(null);
                }}
                onKeyDown={handleComposerKeyDown}
                placeholder={showGeneratedArea ? "Ask for changes for this JD only" : "Paste the full job description here"}
              />
              {!showGeneratedArea ? (
                <div className="composer-inline-controls">
                  <input
                    className="composer-company-input"
                    value={companyName}
                    disabled={extensionDraftLocked || generatingAi}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="Company name for CPT check"
                  />
                  <select
                    className="resume-mode-select"
                    value={resumeMode}
                    disabled={extensionDraftLocked || generatingAi}
                    onChange={(e) => changeResumeMode(e.target.value)}
                    aria-label="Resume mode"
                  >
                    {resumeModes.map((mode) => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
                  </select>
                </div>
              ) : null}
              <div className="composer-toolbar">
                <div className="composer-toolbar-left">
                  <button className="composer-pill" onClick={() => resetAiSession(true)}>New JD</button>
                  <button
                    className="composer-pill"
                    disabled={!profileReady || !showGeneratedArea || !generatedContent.trim() || generatingAi || reachoutLoading || followupLoading}
                    onClick={submitReachoutMessage}
                  >
                    {reachoutLoading ? "Writing..." : "Reachout"}
                  </button>
                  <button
                    className="composer-pill"
                    disabled={!profileReady || !showGeneratedArea || !pdfState.pdfPath || generatingAi || reachoutLoading || followupLoading}
                    onClick={submitFollowupAnswer}
                  >
                    {followupLoading ? "Writing..." : "Follow-up"}
                  </button>
                </div>
                <div className="composer-toolbar-right">
                  <span className="composer-state">
                    {showGeneratedArea ? "Editing current JD" : "Ready for new JD"}
                  </span>
                  <button
                    className={`composer-icon-button ${recordingTarget === (showGeneratedArea ? "refinement" : "jd") ? "recording" : ""}`}
                    disabled={generatingAi || reachoutLoading || followupLoading}
                    onClick={() => startVoiceInput(showGeneratedArea ? "refinement" : "jd", setComposerInput)}
                    aria-label={recordingTarget === (showGeneratedArea ? "refinement" : "jd") ? "Stop voice input" : "Start voice input"}
                  >
                    {recordingTarget === (showGeneratedArea ? "refinement" : "jd") ? "Stop" : "Mic"}
                  </button>
                  <button
                    className="composer-send-button"
                    disabled={!profileReady || extensionDraftLocked || generatingAi || reachoutLoading || followupLoading}
                    onClick={submitAiGeneration}
                    aria-label={showGeneratedArea ? "Update draft" : "Generate content"}
                  >
                    {generatingAi ? "..." : "Send"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="panel preview-surface">
          <div className="preview-toolbar">
            <div className="preview-toolbar-left">
              <div className="panel-eyebrow">Output</div>
              {extensionDraftId && extensionDraftSaveState ? <div className="extension-draft-save-state">{extensionDraftSaveState}</div> : null}
              <div className="preview-toolbar-actions">
                <input
                  className="preview-company-input"
                  value={companyName}
                  disabled={extensionDraftLocked || !viewingEditableResume}
                  onChange={(e) => updateCompanyName(e.target.value)}
                  placeholder="Company name (required)"
                />
                <select
                  className="resume-mode-select compact"
                  value={resumeMode}
                  disabled={extensionDraftLocked || generatingAi || !viewingEditableResume}
                  onChange={(e) => changeResumeMode(e.target.value)}
                  aria-label="Resume mode"
                >
                  {resumeModes.map((mode) => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
                </select>
                {generatedContent.trim() ? (
                  <button
                    className="secondary-button compact-button"
                    disabled={extensionDraftLocked || generatingAi || auditActionLoading || !viewingEditableResume}
                    onClick={regenerateResume}
                  >
                    Regenerate
                  </button>
                ) : null}
                <button
                  className="primary-button"
                  disabled={!profileReady || extensionDraftLocked || generatingAi || !canGeneratePdf || !companyName.trim() || pdfState.mode === "loading" || pdfState.mode === "polling"}
                  onClick={submitPdfGeneration}
                >
                  Generate PDF
                </button>
              </div>
            </div>
            <div className="preview-toolbar-right">
              {tab === "parsed" && preview && !extensionDraftLocked && viewingEditableResume ? (
                <button
                  className="secondary-button"
                  onClick={togglePreviewEditMode}
                >
                  {previewEditMode ? "Done" : "Edit"}
                </button>
              ) : null}
            </div>
          </div>
          <div className="tabs">
            <div className="tabs-left">
              <button className={`tab-button ${tab === "parsed" ? "active" : ""}`} onClick={() => setTab("parsed")}>Parsed Preview</button>
              <button className={`tab-button ${tab === "pdf" ? "active" : ""}`} onClick={() => setTab("pdf")}>PDF Preview</button>
            </div>
            {selectableDraftExperience.length ? (
              <div className="experience-pill-row" aria-label="Experience visibility">
                {selectableDraftExperience.map((item) => (
                  <button
                    key={item.key}
                    className={`toggle-button experience-pill ${sanitizedEnabledExperienceKeys.includes(item.key) ? "active" : ""}`}
                    disabled={extensionDraftLocked || !viewingEditableResume}
                    onClick={() => toggleExperienceKey(item.key)}
                    title={sanitizedEnabledExperienceKeys.includes(item.key) ? "Included in this draft" : "Hidden from this draft"}
                  >
                    {item.company}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          {generatedContent.trim() && audit.status !== "not_started" ? (
            <div className={`quality-review-band status-${audit.status}`} aria-live="polite">
              <div className="quality-review-copy">
                <strong>{auditStatusLabel}</strong>
                <span>{auditStatusMessage}</span>
              </div>
              <div className="quality-review-actions">
                {hasChangesView ? (
                  <button className="secondary-button compact-button" onClick={() => selectResumeVersionView("changes")}>
                    View Changes
                  </button>
                ) : null}
                {["technical_failed", "stale"].includes(audit.status) ? (
                  <button className="secondary-button compact-button" disabled={auditActionLoading} onClick={retryAudit}>
                    {auditActionLoading ? "Reviewing..." : "Retry review"}
                  </button>
                ) : null}
                {audit.status === "manual_attention" ? (
                  <button className="text-button" onClick={openAuditEditor}>Open Editor</button>
                ) : null}
              </div>
            </div>
          ) : null}
          {tab === "parsed" && hasVersionViews ? (
            <div className="resume-version-bar" aria-label="Resume versions">
              <div className="resume-version-tabs">
                {resumeVersions.original ? (
                  <button
                    className={resumeVersionView === "original" ? "active" : ""}
                    onClick={() => selectResumeVersionView("original")}
                  >
                    Original
                  </button>
                ) : null}
                {resumeVersions.luna_reviewed ? (
                  <button
                    className={resumeVersionView === "luna_reviewed" ? "active" : ""}
                    onClick={() => selectResumeVersionView("luna_reviewed")}
                  >
                    Luna Reviewed
                  </button>
                ) : null}
                {resumeVersions.manual ? (
                  <button
                    className={resumeVersionView === "manual" ? "active" : ""}
                    onClick={() => selectResumeVersionView("manual")}
                  >
                    Current Edits
                  </button>
                ) : null}
                {hasChangesView ? (
                  <button
                    className={viewingChanges ? "active" : ""}
                    onClick={() => selectResumeVersionView("changes")}
                  >
                    Changes
                  </button>
                ) : null}
              </div>
              <span className="resume-version-note">
                {viewingChanges
                  ? "Review changes applied by Luna."
                  : (viewingEditableResume ? "This version is used for editing and PDF generation." : "Read-only version.")}
              </span>
            </div>
          ) : null}
          <div className="panel-body preview-body">
            {tab === "parsed" ? (
              <>
                {viewingEditableResume && validation.errors?.length ? (
                  <div className="error-list">
                    {validation.errors.map((error, index) => <div key={index}>{error}</div>)}
                  </div>
                ) : null}
                {viewingChanges ? (
                  <div className="resume-changes-view">
                    <AuditChangeReview
                      audit={audit}
                      loading={auditActionLoading}
                      onOpenEditor={openAuditEditor}
                      onRetry={retryAudit}
                    />
                  </div>
                ) : previewEditMode && viewingEditableResume ? (
                  <div className="preview-edit-shell">
                    {visibleDraftExperience.length ? (
                      <div className="experience-inline-editor">
                        {visibleDraftExperience.map((item) => {
                          const index = orderedDraftExperience.findIndex((entry) => entry.key === item.key);
                          return (
                            <input
                              key={item.key || index}
                              className="experience-inline-input"
                              value={item.company || ""}
                              onChange={(e) => updateEditableExperienceHistory(index, "company", e.target.value)}
                              placeholder="Company name"
                            />
                          );
                        })}
                      </div>
                    ) : null}
                    <textarea
                      ref={previewEditorRef}
                      className="preview-editor"
                      value={generatedContent}
                      disabled={extensionDraftLocked}
                      onChange={(e) => updateGeneratedContent(e.target.value)}
                    />
                  </div>
                ) : (
                  <ParsedPreview
                    preview={displayedPreview}
                    loadingExperience={viewingCurrentResume && generatingAi && aiStage === "experience"}
                  />
                )}
              </>
            ) : (
              <div className="pdf-shell">
                {pdfState.mode === "idle" ? <div className="blank-state">Generate a resume to preview the PDF.</div> : null}
                {pdfState.mode === "loading" || pdfState.mode === "polling" ? (
                  <div className="blank-state">{pdfState.statusLabel || "Generating PDF..."}</div>
                ) : null}
                {pdfState.mode === "error" ? <div className="error-banner">{pdfState.error}</div> : null}
                {pdfState.mode === "ready" ? (
                  <>
                    <div className="pdf-actions">
                      <a className="primary-button link-button" href={`/api/download?path=${encodeURIComponent(pdfState.pdfPath)}`}>Download</a>
                      <button className="secondary-button" onClick={() => fetchJson("/api/open-folder", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ path: pdfState.outputDir }),
                      }).catch((error) => window.alert(error.message))}>Open Folder</button>
                    </div>
                    <iframe title="PDF Preview" className="pdf-frame" src={pdfPreviewUrl} />
                  </>
                ) : null}
              </div>
            )}
          </div>
        </section>
      </main>

      <Modal
        open={modals.qualityReview}
        title={audit.status === "manual_attention" ? "Quality Review Guidance" : audit.status === "stale" ? "Review Needs Updating" : "Quality Review Changes"}
        onClose={() => closeModal("qualityReview")}
        footer={(
          <div className="audit-modal-actions">
            {["manual_attention", "stale"].includes(audit.status) ? (
              <>
                <button className="primary-button compact-button" disabled={auditActionLoading} onClick={openAuditEditor}>Start Editing</button>
                <button className="secondary-button compact-button" disabled={auditActionLoading} onClick={retryAudit}>
                  {auditActionLoading ? "Reviewing..." : "Retry review"}
                </button>
              </>
            ) : null}
            <button className="secondary-button compact-button" disabled={auditActionLoading} onClick={() => closeModal("qualityReview")}>Close</button>
          </div>
        )}
      >
        <AuditChangeReview
          key={`${aiSessionId || "no-session"}:${audit.baseRevision || ""}:${audit.baseHash || ""}:${audit.status}`}
          audit={audit}
          loading={auditActionLoading}
          onOpenEditor={openAuditEditor}
          onRetry={retryAudit}
        />
      </Modal>

      <Modal
        open={modals.instructions}
        title="Format Guide"
        onClose={() => closeModal("instructions")}
      >
        <div className="modal-copy">
          <p><strong>Updated Title</strong> followed by the target role.</p>
          <p><strong>Updated Summary</strong> with 3-4 production-focused lines.</p>
          <p><strong>Updated Skills</strong> as category-to-skill lists.</p>
          <p><strong>Professional Experience</strong> with the fixed company order and bullet rules.</p>
        </div>
      </Modal>

      <Modal
        open={modals.settings}
        title="Settings"
        onClose={() => closeModal("settings")}
        footer={(
          <>
            <button className="secondary-button" onClick={() => closeModal("settings")}>Cancel</button>
            <button className="primary-button" onClick={saveSettings}>Save</button>
          </>
        )}
      >
        <label className="field">
          Output Directory
          <input value={settingsDraft.output_directory || ""} onChange={(e) => setSettingsDraft((current) => ({ ...current, output_directory: e.target.value }))} />
        </label>
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={!!settingsDraft.allow_security_clearance_jobs}
            onChange={(e) => setSettingsDraft((current) => ({ ...current, allow_security_clearance_jobs: e.target.checked }))}
          />
          <span>
            <strong>Allow clearance-restricted jobs</strong>
            <small>When off, jobs requiring clearance, U.S. citizenship, Public Trust, ITAR, or export-control eligibility stop before AI generation.</small>
          </span>
        </label>
        <div className="profile-experience-section">
          <div className="section-label">Contact identities</div>
          <label className="field">
            Default contact identity
            <select
              value={settingsDraft.default_identity_id || defaultIdentityId(settingsDraft, normalizeIdentityProfiles(settingsDraft.identities || []))}
              onChange={(e) => setSettingsDraft((current) => ({ ...current, default_identity_id: e.target.value }))}
            >
              {normalizeIdentityProfiles(settingsDraft.identities || []).map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
            </select>
            <small>Used by resume generation and autofill when no identity is selected.</small>
          </label>
          <div className="profile-experience-list">
            {(settingsDraft.identities || []).map((item, index) => (
              <div key={item.id || index} className="profile-experience-card">
                <div className="profile-experience-card-header">
                  <div className="profile-experience-card-title">Identity {index + 1}</div>
                  <button
                    className="secondary-button"
                    disabled={(settingsDraft.identities || []).length <= 1}
                    onClick={() => removeSettingsIdentity(index)}
                  >
                    Remove
                  </button>
                </div>
                <div className="profile-grid">
                  <label className="field">
                    Label
                    <input value={item.label || ""} onChange={(e) => updateSettingsIdentity(index, "label", e.target.value)} />
                  </label>
                  <label className="field">
                    Format
                    <select value={item.format_profile || "outlook"} onChange={(e) => updateSettingsIdentity(index, "format_profile", e.target.value)}>
                      <option value="outlook">Outlook</option>
                      <option value="gmail">Gmail</option>
                    </select>
                  </label>
                  <label className="field">
                    Email
                    <input value={item.email || ""} onChange={(e) => updateSettingsIdentity(index, "email", e.target.value)} />
                  </label>
                  <label className="field">
                    Phone
                    <input value={item.phone || ""} onChange={(e) => updateSettingsIdentity(index, "phone", e.target.value)} />
                  </label>
                  <label className="field">
                    Location
                    <input value={item.location || ""} onChange={(e) => updateSettingsIdentity(index, "location", e.target.value)} />
                  </label>
                </div>
              </div>
            ))}
          </div>
          <button className="secondary-button" onClick={addSettingsIdentity}>Add identity</button>
        </div>
      </Modal>

      <Modal
        open={modals.profile}
        title={onboardingRequired ? "Profile Setup" : "Profile"}
        onClose={() => closeModal("profile")}
        footer={(
          <>
            {!onboardingRequired ? <button className="secondary-button" onClick={() => closeModal("profile")}>Cancel</button> : null}
            {!onboardingRequired ? <button className="secondary-button" onClick={() => saveProfile("session")}>Save for This Session</button> : null}
            <button className="primary-button" onClick={() => saveProfile("permanent")}>
              {onboardingRequired ? "Complete Setup" : "Save Permanently"}
            </button>
          </>
        )}
      >
        {onboardingRequired ? (
          <div className="profile-experience-note">
            Finish this once and we’ll create your permanent profile file. Session-only edits can be used later from this same screen.
          </div>
        ) : sessionProfileActive ? (
          <div className="profile-experience-note">
            Session-only profile changes are active right now. Restarting the server will revert to your permanent profile.
          </div>
        ) : null}
        <div className="profile-grid">
          <label className="field">
            Name
            <input value={profileDraft.name || ""} onChange={(e) => setProfileDraft((current) => ({ ...current, name: e.target.value }))} />
          </label>
          <label className="field">
            Location
            <input value={profileDraft.contact?.location || ""} onChange={(e) => setProfileDraft((current) => ({ ...current, contact: { ...(current.contact || {}), location: e.target.value } }))} />
          </label>
          <label className="field">
            Phone
            <input value={profileDraft.contact?.phone || ""} onChange={(e) => setProfileDraft((current) => ({ ...current, contact: { ...(current.contact || {}), phone: e.target.value } }))} />
          </label>
          <label className="field">
            Email
            <input value={profileDraft.contact?.email || ""} onChange={(e) => setProfileDraft((current) => ({ ...current, contact: { ...(current.contact || {}), email: e.target.value } }))} />
          </label>
        </div>
        <label className="field">
          Certifications
          <textarea value={profileDraft.certificationsText || (profileDraft.certifications || []).join("\n")} onChange={(e) => setProfileDraft((current) => ({ ...current, certificationsText: e.target.value }))} />
        </label>
        <label className="field">
          Projects
          <textarea value={profileDraft.projectsText || formatProjects(profileDraft.projects || [])} onChange={(e) => setProfileDraft((current) => ({ ...current, projectsText: e.target.value }))} />
        </label>
        <div className="profile-experience-section">
          <div className="section-label">Experience History</div>
          <div className="profile-experience-note">* Only enabled roles with all four fields filled are included in the resume and PDF.</div>
          <div className="profile-experience-list">
            {(profileDraft.experience_history || []).map((item, index) => (
              <div key={item.key || index} className="profile-experience-card">
                <div className="profile-experience-card-header">
                  <div className="profile-experience-card-title">Role {index + 1}</div>
                  <label className="profile-experience-toggle">
                    <input
                      type="checkbox"
                      checked={item.enabled !== false}
                      onChange={() => toggleProfileExperienceEnabled(index)}
                    />
                    <span>Enabled</span>
                  </label>
                </div>
                <div className="profile-grid">
                  <label className="field">
                    Company
                    <input
                      value={item.company || ""}
                      placeholder="Company name"
                      onChange={(e) => updateExperienceHistory(index, "company", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    Location
                    <input
                      value={item.location || ""}
                      placeholder="Location"
                      onChange={(e) => updateExperienceHistory(index, "location", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    Default Title
                    <input
                      value={item.title || ""}
                      placeholder="Role title"
                      onChange={(e) => updateExperienceHistory(index, "title", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    Dates
                    <input
                      value={item.dates || ""}
                      placeholder="Month YYYY – Month YYYY"
                      onChange={(e) => updateExperienceHistory(index, "dates", e.target.value)}
                    />
                  </label>
                </div>
                {!isExperienceHistoryComplete(item) ? (
                  <div className="profile-experience-warning">This role is incomplete and will be excluded until all fields are filled.</div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </Modal>

      <Modal
        open={modals.outreach}
        title="Startup Outreach Leads"
        onClose={() => closeModal("outreach")}
      >
        <div className="outreach-modal">
          <div className="tracker-summary-row outreach-summary-row">
            <span className="badge">Total {outreachData.summary?.total || 0}</span>
            {(outreachData.statuses || outreachStatuses).map((status) => (
              <span key={status} className="badge">{status} {outreachData.summary?.counts?.[status] || 0}</span>
            ))}
          </div>

          {outreachError ? <div className="error-banner">{outreachError}</div> : null}
          {outreachMessage ? (
            <div className="outreach-message-card">
              <div className="outreach-card-header">
                <div>
                  <div className="section-label">Stored Message</div>
                  <strong>{outreachMessage.subject || "Outreach note"}</strong>
                </div>
                <button className="secondary-button compact-button" onClick={copyOutreachMessage}>Copy</button>
              </div>
              <p>{outreachMessage.body}</p>
            </div>
          ) : null}

          <details className="outreach-import-card">
            <summary>Import from Codex</summary>
            <textarea
              placeholder='Paste JSON like {"leads":[{"company_name":"Acme","status":"Ready to contact","fit_score":82}]}'
              value={outreachImportText}
              onChange={(e) => setOutreachImportText(e.target.value)}
            />
            <div className="outreach-actions">
              <button className="secondary-button compact-button" onClick={() => setOutreachImportText("")}>Clear</button>
              <button className="primary-button compact-button" onClick={importOutreachLeads}>Import Leads</button>
            </div>
          </details>

          <div className="outreach-layout">
            <div className="outreach-form-card">
              <div className="outreach-card-header">
                <div>
                  <div className="section-label">{editingOutreachId ? "Edit Lead" : "New Lead"}</div>
                  <strong>{outreachDraft.company_name || "Company research"}</strong>
                </div>
                <button className="secondary-button compact-button" onClick={startNewOutreachLead}>New</button>
              </div>

              <div className="profile-grid">
                <label className="field">
                  Company *
                  <input value={outreachDraft.company_name} onChange={(e) => updateOutreachDraft("company_name", e.target.value)} />
                </label>
                <label className="field">
                  Target role
                  <input placeholder="Backend engineer, AI engineer..." value={outreachDraft.target_role_type} onChange={(e) => updateOutreachDraft("target_role_type", e.target.value)} />
                </label>
                <label className="field">
                  Website
                  <input value={outreachDraft.website} onChange={(e) => updateOutreachDraft("website", e.target.value)} />
                </label>
                <label className="field">
                  Source type
                  <select value={outreachDraft.source_type} onChange={(e) => updateOutreachDraft("source_type", e.target.value)}>
                    {(outreachData.source_types || outreachSourceTypes).map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Source URL
                  <input value={outreachDraft.source_url} onChange={(e) => updateOutreachDraft("source_url", e.target.value)} />
                </label>
                <label className="field">
                  Status
                  <select value={outreachDraft.status} onChange={(e) => updateOutreachDraft("status", e.target.value)}>
                    {(outreachData.statuses || outreachStatuses).map((status) => (
                      <option key={status} value={status}>{status}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Contact name
                  <input value={outreachDraft.contact_name} onChange={(e) => updateOutreachDraft("contact_name", e.target.value)} />
                </label>
                <label className="field">
                  Contact role
                  <input placeholder="CEO, CTO, Founder..." value={outreachDraft.contact_role} onChange={(e) => updateOutreachDraft("contact_role", e.target.value)} />
                </label>
                <label className="field">
                  Contact email
                  <input value={outreachDraft.contact_email} onChange={(e) => updateOutreachDraft("contact_email", e.target.value)} />
                </label>
                <label className="field">
                  Contact URL
                  <input value={outreachDraft.contact_url} onChange={(e) => updateOutreachDraft("contact_url", e.target.value)} />
                </label>
                <label className="field">
                  Fit score
                  <input type="number" min="0" max="100" value={outreachDraft.fit_score} onChange={(e) => updateOutreachDraft("fit_score", e.target.value)} />
                </label>
                <label className="field">
                  Follow-up date
                  <input type="date" value={outreachDraft.follow_up_at} onChange={(e) => updateOutreachDraft("follow_up_at", e.target.value)} />
                </label>
              </div>

              <label className="field">
                Hiring or growth signal
                <textarea placeholder="Funding news, founder post, product launch, hiring clue..." value={outreachDraft.signal_text} onChange={(e) => updateOutreachDraft("signal_text", e.target.value)} />
              </label>
              <label className="field">
                Product summary
                <textarea placeholder="What the startup builds and who it serves." value={outreachDraft.product_summary} onChange={(e) => updateOutreachDraft("product_summary", e.target.value)} />
              </label>
              <label className="field">
                Engineering need
                <textarea placeholder="Why your resume should be angled toward their current technical needs." value={outreachDraft.inferred_engineering_need} onChange={(e) => updateOutreachDraft("inferred_engineering_need", e.target.value)} />
              </label>
              <label className="field">
                Resume angle
                <textarea placeholder="How Codex wants the resume positioned for this lead." value={outreachDraft.resume_angle} onChange={(e) => updateOutreachDraft("resume_angle", e.target.value)} />
              </label>
              <label className="field">
                Fit reasons
                <textarea placeholder="One reason per line." value={outreachDraft.fit_reasons} onChange={(e) => updateOutreachDraft("fit_reasons", e.target.value)} />
              </label>
              <label className="field">
                Message subject
                <input value={outreachDraft.message_subject} onChange={(e) => updateOutreachDraft("message_subject", e.target.value)} />
              </label>
              <label className="field">
                Message body
                <textarea placeholder="Store the final outreach message Codex wrote." value={outreachDraft.message_body} onChange={(e) => updateOutreachDraft("message_body", e.target.value)} />
              </label>
              <label className="field">
                Blocked reason
                <textarea placeholder="Only fill this when Codex decides the lead should not be contacted." value={outreachDraft.blocked_reason} onChange={(e) => updateOutreachDraft("blocked_reason", e.target.value)} />
              </label>
              <label className="field">
                Notes
                <textarea value={outreachDraft.notes} onChange={(e) => updateOutreachDraft("notes", e.target.value)} />
              </label>

              <div className="outreach-actions">
                <button className="primary-button" onClick={saveOutreachLead}>{editingOutreachId ? "Save Lead" : "Add Lead"}</button>
              </div>
            </div>

            <div className="outreach-list-panel">
              <div className="tracker-filters outreach-filters">
                <input
                  className="tracker-search"
                  placeholder="Search company, role, contact, or signal"
                  value={outreachFilters.query}
                  onChange={(e) => setOutreachFilters((current) => ({ ...current, query: e.target.value }))}
                />
                <select
                  value={outreachFilters.status}
                  onChange={(e) => setOutreachFilters((current) => ({ ...current, status: e.target.value }))}
                >
                  <option value="">All statuses</option>
                  {(outreachData.statuses || outreachStatuses).map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
                <button className="secondary-button compact-button" onClick={loadOutreach}>Refresh</button>
              </div>

              {outreachLoading ? (
                <div className="blank-state">Loading outreach leads...</div>
              ) : filteredOutreachLeads.length ? (
                <div className="outreach-lead-list">
                  {filteredOutreachLeads.map((lead) => (
                    <article key={lead.id} className={`outreach-lead-card ${lead.blocked_reason ? "blocked" : ""}`}>
                      <div className="outreach-lead-top">
                        <div>
                          <div className="outreach-lead-company">{lead.company_name}</div>
                          <div className="outreach-lead-meta">{lead.target_role_type || "Role not set"}</div>
                        </div>
                        <span className="badge">Score {lead.fit_score || 0}</span>
                      </div>
                      <div className="outreach-lead-meta">
                        {lead.status || "Needs review"}
                        {lead.contact_name || lead.contact_role ? ` · ${[lead.contact_name, lead.contact_role].filter(Boolean).join(", ")}` : ""}
                      </div>
                      {lead.blocked_reason ? (
                        <div className="outreach-blocked-reason">{lead.blocked_reason}</div>
                      ) : null}
                      {lead.fit_reasons?.length ? (
                        <div className="outreach-reasons">
                          {lead.fit_reasons.map((reason) => <span key={reason}>{reason}</span>)}
                        </div>
                      ) : null}
                      <div className="outreach-actions">
                        <button className="secondary-button compact-button" onClick={() => editOutreachLead(lead)}>Edit</button>
                        <button className="primary-button compact-button" disabled={!!lead.blocked_reason} onClick={() => useOutreachLeadForResume(lead)}>Use for Resume</button>
                        <button className="secondary-button compact-button" onClick={() => loadOutreachMessage(lead)}>View Message</button>
                        {lead.source_url ? (
                          <a className="secondary-button compact-button link-button" href={lead.source_url} target="_blank" rel="noreferrer">Source</a>
                        ) : null}
                        <button className="secondary-button compact-button danger-button" onClick={() => deleteOutreachLead(lead)}>Delete</button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="blank-state">No outreach leads match this view.</div>
              )}
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        open={modals.trackApply}
        title="Tracker Details"
        onClose={() => closeModal("trackApply")}
        footer={(
          <>
            <button className="secondary-button" onClick={() => closeModal("trackApply")}>Cancel</button>
            <button className="primary-button" onClick={submitTrackApplication}>Save</button>
          </>
        )}
      >
        <div className="tracker-form-grid">
          <label className="field">
            Company
            <input value={companyName || latestAnalysis?.company_name || ""} onChange={(e) => updateCompanyName(e.target.value)} />
          </label>
          <label className="field">
            Applied Date
            <input type="date" value={trackApplyDraft.applied_date} onChange={(e) => setTrackApplyDraft((current) => ({ ...current, applied_date: e.target.value }))} />
          </label>
          <label className="field">
            Status
            <select value={trackApplyDraft.status} onChange={(e) => setTrackApplyDraft((current) => ({ ...current, status: e.target.value }))}>
              {trackerData.statuses.map((status) => <option key={status} value={status}>{status}</option>)}
            </select>
          </label>
          <label className="field">
            Source
            <input placeholder="LinkedIn, company site, referral..." value={trackApplyDraft.source} onChange={(e) => setTrackApplyDraft((current) => ({ ...current, source: e.target.value }))} />
          </label>
        </div>
        <label className="field">
          Job URL
          <input placeholder="Optional job link" value={trackApplyDraft.job_url} onChange={(e) => setTrackApplyDraft((current) => ({ ...current, job_url: e.target.value }))} />
        </label>
        <label className="field">
          Notes
          <textarea placeholder="Optional notes" value={trackApplyDraft.notes} onChange={(e) => setTrackApplyDraft((current) => ({ ...current, notes: e.target.value }))} />
        </label>
        <div className="tracker-lock-note">
          Saved resume folders are tracked automatically. Use this to attach details like source, link, notes, or a manual status to the current saved application.
        </div>
      </Modal>

      <Modal
        open={companyHistoryDecision.open}
        title="Existing Applications Found"
        onClose={cancelAfterCompanyHistoryDecision}
        footer={(
          <>
            <button className="secondary-button" onClick={cancelAfterCompanyHistoryDecision}>Stop Here</button>
            <button className="primary-button" onClick={continueAfterCompanyHistoryDecision}>Continue Anyway</button>
          </>
        )}
      >
        <div className="modal-copy">
          <p>
            We already found {companyHistoryDecision.history?.count || 0} tracked application{(companyHistoryDecision.history?.count || 0) === 1 ? "" : "s"} for{" "}
            <strong>{companyHistoryDecision.history?.company_name || companyName || latestAnalysis?.company_name || "this company"}</strong>.
          </p>
          <p>
            Review them before generating another tailored resume. If you continue, the app will resume normal generation from this point.
          </p>
        </div>
        <PriorApplicationsList history={companyHistoryDecision.history} />
      </Modal>

      <Modal
        open={modals.tracker}
        title="Application Tracker"
        onClose={() => closeModal("tracker")}
      >
        <div className="tracker-summary-row">
          <span className="badge">Total {trackerData.summary?.total || 0}</span>
          {trackerData.statuses.map((status) => (
            <span key={status} className="badge">{status} {trackerData.summary?.counts?.[status] || 0}</span>
          ))}
        </div>
        <div className="tracker-filters">
          <input
            className="tracker-search"
            placeholder="Search company or role"
            value={trackerFilters.query}
            onChange={(e) => setTrackerFilters((current) => ({ ...current, query: e.target.value }))}
          />
          <div className="tracker-date-filters">
            <label className="field">
              Applied From
              <input
                type="date"
                value={trackerFilters.applied_from}
                onChange={(e) => setTrackerFilters((current) => ({ ...current, applied_from: e.target.value }))}
              />
            </label>
            <label className="field">
              Applied To
              <input
                type="date"
                value={trackerFilters.applied_to}
                onChange={(e) => setTrackerFilters((current) => ({ ...current, applied_to: e.target.value }))}
              />
            </label>
          </div>
        </div>
        <div className="tracker-toolbar">
          <div className="identity-group tracker-view-toggle">
            <button className={`toggle-button ${trackerView === "board" ? "active" : ""}`} onClick={() => setTrackerView("board")}>Board</button>
            <button className={`toggle-button ${trackerView === "table" ? "active" : ""}`} onClick={() => setTrackerView("table")}>Table</button>
          </div>
          <button className="secondary-button" onClick={loadTracker}>Refresh</button>
        </div>
        {trackerError ? <div className="error-banner">{trackerError}</div> : null}
        {trackerLoading ? (
          <div className="blank-state">Loading tracker…</div>
        ) : trackerView === "board" ? (
          <TrackerBoard
            applications={filteredTrackerApplications}
            statuses={trackerData.statuses}
            onStatusChange={updateTrackedStatus}
            onPreview={openTrackerPreview}
            onOpenFile={openTrackerFile}
          />
        ) : (
          <TrackerTable
            applications={filteredTrackerApplications}
            statuses={trackerData.statuses}
            onStatusChange={updateTrackedStatus}
            onPreview={openTrackerPreview}
            onOpenFile={openTrackerFile}
          />
        )}
      </Modal>

      <Modal
        open={trackerPreview.open}
        title="Resume Preview"
        onClose={closeTrackerPreview}
      >
        {trackerPreview.application?.pdf_path ? (
          <div className="tracker-preview-shell">
            <iframe
              title="Tracked Resume Preview"
              className="pdf-frame tracker-preview-frame"
              src={`/api/download?path=${encodeURIComponent(trackerPreview.application.pdf_path)}&preview=true`}
            />
          </div>
        ) : trackerPreview.application?.resume_snapshot ? (
          <div className="preview-scroll tracker-preview-scroll">
            <section className="preview-section">
              <div className="preview-title">{trackerPreview.application.resume_snapshot.title || trackerPreview.application.role_title || ""}</div>
            </section>
            {trackerPreview.application.resume_snapshot.summary ? (
              <section className="preview-section">
                <h3 className="section-label">Summary</h3>
                <p className="preview-copy">{trackerPreview.application.resume_snapshot.summary}</p>
              </section>
            ) : null}
            {trackerPreview.application.resume_snapshot.technical_skills?.length ? (
              <section className="preview-section">
                <h3 className="section-label">Technical Skills</h3>
                <div className="skill-list">
                  {trackerPreview.application.resume_snapshot.technical_skills.map((skill) => (
                    <div key={skill.category} className="skill-row editable-row">
                      <strong>{skill.category}:</strong>
                      <span className="skill-row-text">{skill.items || ""}</span>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
            {trackerPreview.application.resume_snapshot.experience?.length ? (
              <section className="preview-section">
                <h3 className="section-label">Professional Experience</h3>
                <div className="experience-list">
                  {trackerPreview.application.resume_snapshot.experience.map((item) => (
                    <article key={`${item.company}-${item.dates}`} className="experience-card">
                      <div className="experience-company">{item.company} | {item.dates}</div>
                      <div className="experience-title-text">{item.title || ""}</div>
                      <div className="experience-bullets">
                        {(item.bullets || []).map((bullet, index) => (
                          <div key={index} className="experience-bullet editable-row">
                            <span>•</span>
                            <span className="experience-bullet-text">{bullet}</span>
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ) : null}
            {!trackerPreview.application.resume_snapshot.summary && !trackerPreview.application.resume_snapshot.technical_skills?.length && !trackerPreview.application.resume_snapshot.experience?.length ? (
              <div className="blank-state">No saved parsed preview is available for this application.</div>
            ) : null}
          </div>
        ) : (
          <div className="blank-state">No saved resume preview is available for this application.</div>
        )}
      </Modal>
    </div>
  );
}

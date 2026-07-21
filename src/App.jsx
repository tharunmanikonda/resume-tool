import React, { useEffect, useMemo, useRef, useState } from "react";

const emptyProfile = {
  name: "",
  contact: { location: "", phone: "", email: "" },
  certifications: [],
  projects: [],
  experience_history: [],
};

const experienceKeys = ["mckinsey", "uber", "kpmg", "trigent"];

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

function allEnabledExperienceKeys(history = []) {
  return normalizeInlineExperienceHistory(history)
    .filter((item) => isExperienceHistoryEnabled(item))
    .map((item) => item.key)
    .filter(Boolean);
}

function sanitizeEnabledExperienceKeys(history = [], selectedKeys = []) {
  const orderedEnabledKeys = allEnabledExperienceKeys(history);
  if (!orderedEnabledKeys.length) return [];

  const selectedSet = new Set((selectedKeys || []).filter(Boolean));
  const filteredKeys = orderedEnabledKeys.filter((key) => selectedSet.has(key));
  return filteredKeys.length ? filteredKeys : orderedEnabledKeys;
}

function deriveExperienceHistoryFromContent(content, history = []) {
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
  let roleCursor = 0;

  for (let index = experienceIndex + 1; index < lines.length && roleCursor < nextHistory.length; index += 1) {
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
    const role = nextHistory[roleCursor];
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

function applyExperienceHistoryToGeneratedContent(content, history = []) {
  const text = String(content || "");
  const normalizedHistory = normalizeInlineExperienceHistory(history);
  if (!text.trim() || !normalizedHistory.length) return text;

  const lines = text.split("\n");
  const experienceIndex = lines.findIndex((line) => line.trim().toLowerCase() === "professional experience");
  if (experienceIndex === -1) return text;

  const updatedLines = [...lines];
  let roleCursor = 0;

  for (let index = experienceIndex + 1; index < updatedLines.length && roleCursor < normalizedHistory.length; index += 1) {
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

    const role = normalizedHistory[roleCursor];
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

function combineCoreDraft(titleSummaryContent, skillsContent) {
  return [titleSummaryContent?.trim(), skillsContent?.trim(), "Professional Experience"]
    .filter(Boolean)
    .join("\n\n");
}

function formatDateShort(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
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
  const [extensionDraftId] = useState(() => new URLSearchParams(window.location.search).get("draft") || "");
  const [extensionDraftLocked, setExtensionDraftLocked] = useState(false);
  const [extensionDraftSaveState, setExtensionDraftSaveState] = useState("");
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [profile, setProfile] = useState(emptyProfile);
  const [profileDraft, setProfileDraft] = useState(emptyProfile);
  const [onboardingRequired, setOnboardingRequired] = useState(false);
  const [sessionProfileActive, setSessionProfileActive] = useState(false);
  const [settings, setSettings] = useState({ output_directory: "", identities: [] });
  const [settingsDraft, setSettingsDraft] = useState({ output_directory: "", identities: [] });
  const [pdfStatus, setPdfStatus] = useState({ ready: false, message: "Checking..." });
  const [aiStatus, setAiStatus] = useState({ ready: false, message: "Checking...", model: "gpt-5-mini", memory_limit: 2 });
  const [identity, setIdentity] = useState("");
  const [contact, setContact] = useState({ location: "", phone: "", email: "" });
  const [editableExperienceHistory, setEditableExperienceHistory] = useState([]);
  const [enabledExperienceKeys, setEnabledExperienceKeys] = useState([]);
  const [companyName, setCompanyName] = useState("");
  const [composerInput, setComposerInput] = useState("");
  const [resumeJobContext, setResumeJobContext] = useState(null);
  const [generatedContent, setGeneratedContent] = useState("");
  const [preview, setPreview] = useState(null);
  const [validation, setValidation] = useState({ valid: false, errors: [] });
  const [tab, setTab] = useState("parsed");
  const [aiSessionId, setAiSessionId] = useState(null);
  const [lastGeneratedJd, setLastGeneratedJd] = useState("");
  const [memoryCount, setMemoryCount] = useState(0);
  const [aiThread, setAiThread] = useState([]);
  const [aiError, setAiError] = useState("");
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

  const mediaRecorderRef = useRef(null);
  const mediaChunksRef = useRef([]);
  const streamRef = useRef(null);
  const previewRequestSeqRef = useRef(0);
  const extensionDraftHydratedRef = useRef(false);
  const extensionDraftLastSavedRef = useRef("");
  const [recordingTarget, setRecordingTarget] = useState("");

  useEffect(() => {
    fetchJson("/api/settings")
      .then((data) => {
        const identities = normalizeIdentityProfiles(data.identities || []);
        setSettings({ ...data, identities });
        setSettingsDraft({ output_directory: data.output_directory || "", identities });
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
        setEnabledExperienceKeys(allEnabledExperienceKeys(history));
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
  }, []);

  useEffect(() => {
    if (!extensionDraftId || !profileLoaded || extensionDraftHydratedRef.current) return;
    extensionDraftHydratedRef.current = true;
    fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}/editor-session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then((data) => {
        const draft = data.draft;
        const history = normalizeExperienceHistory(draft.experience_history_snapshot || []);
        setAiSessionId(data.session_id || null);
        setLastGeneratedJd(draft.job_description || "");
        setLatestAnalysis(draft.analysis || null);
        setGeneratedContent(draft.resume_content || "");
        setCompanyName(draft.company_name || "");
        setIdentity(draft.identity_id || "");
        setContact({
          location: draft.contact_snapshot?.location || "",
          phone: draft.contact_snapshot?.phone || "",
          email: draft.contact_snapshot?.email || "",
        });
        setEditableExperienceHistory(history);
        setEnabledExperienceKeys(draft.enabled_experience_keys || allEnabledExperienceKeys(history));
        setResumeJobContext({
          id: "",
          draft_id: draft.id,
          title: draft.role_title || "",
          company_name: draft.company_name || "",
          job_url: draft.canonical_url || "",
        });
        setPreview(draft.preview || draft.resume_snapshot || null);
        setShowGeneratedArea(!!draft.resume_content);
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
        setAiThread([{
          kind: "assistant",
          title: draft.locked ? "Applied Resume" : "LinkedIn Draft Loaded",
          lines: [draft.locked ? "This applied resume is locked." : "Edits in this page save back to the LinkedIn side-panel draft."],
        }]);
        extensionDraftLastSavedRef.current = JSON.stringify({
          content: draft.resume_content || "",
          company: draft.company_name || "",
          identity: draft.identity_id || "",
          enabled: draft.enabled_experience_keys || [],
          history,
        });
      })
      .catch((error) => {
        extensionDraftHydratedRef.current = false;
        setAiError(error.message || "Could not load the LinkedIn resume draft.");
      });
  }, [extensionDraftId, profileLoaded]);

  useEffect(() => {
    const identities = normalizeIdentityProfiles(settings.identities || []);
    if (!identities.length) {
      setIdentity("");
      setContact(emptyProfile.contact);
      return;
    }

    const activeIdentity = identities.find((item) => item.id === identity) || identities[0];
    if (activeIdentity.id !== identity) {
      setIdentity(activeIdentity.id);
    }
    setContact({
      location: activeIdentity.location || "",
      phone: activeIdentity.phone || "",
      email: activeIdentity.email || "",
    });
  }, [settings.identities]);

  function requestPreview(nextContent = generatedContent) {
    const content = String(nextContent || "");
    if (!content.trim()) {
      setPreview(null);
      setValidation({ valid: false, errors: [] });
      return Promise.resolve(null);
    }

    const draftExperienceHistory = deriveExperienceHistoryFromContent(content, editableExperienceHistory);
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
  }, [generatedContent, contact, identity, profile, editableExperienceHistory, enabledExperienceKeys]);

  useEffect(() => {
    if (!generatedContent.trim()) return;
    const derivedHistory = deriveExperienceHistoryFromContent(generatedContent, editableExperienceHistory);
    if (!experienceHistoryEquals(derivedHistory, editableExperienceHistory)) {
      setEditableExperienceHistory(derivedHistory);
    }
  }, [generatedContent]);

  useEffect(() => {
    if (!extensionDraftId || !extensionDraftHydratedRef.current || extensionDraftLocked || !generatedContent.trim() || generatingAi) return undefined;
    const fingerprint = JSON.stringify({
      content: generatedContent,
      company: companyName,
      identity,
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
          enabled_experience_keys: sanitizedEnabledExperienceKeys,
          experience_history: editableExperienceHistory,
        }),
      })
        .then((data) => {
          setPreview(data.draft?.preview || preview);
          setExtensionDraftSaveState("Draft saved");
          if (data.draft?.pdf_stale) {
            setPdfState({ mode: "idle", error: "", statusPath: "", pdfPath: "", outputDir: "", statusLabel: "" });
          }
        })
        .catch((error) => {
          extensionDraftLastSavedRef.current = "";
          setExtensionDraftSaveState(error.message || "Draft save failed");
        });
    }, 800);
    return () => window.clearTimeout(timer);
  }, [extensionDraftId, extensionDraftLocked, generatedContent, companyName, identity, enabledExperienceKeys, editableExperienceHistory, generatingAi]);

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
  const canGeneratePdf = validation.valid && generatedContent.trim().length > 0;
  const orderedDraftExperience = normalizeInlineExperienceHistory(editableExperienceHistory);
  const selectableDraftExperience = orderedDraftExperience.filter((item) => isExperienceHistoryComplete(item));
  const sanitizedEnabledExperienceKeys = sanitizeEnabledExperienceKeys(orderedDraftExperience, enabledExperienceKeys);
  const visibleDraftExperience = selectableDraftExperience.filter((item) => sanitizedEnabledExperienceKeys.includes(item.key));
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

  useEffect(() => {
    const nextKeys = sanitizeEnabledExperienceKeys(editableExperienceHistory, enabledExperienceKeys);
    if (nextKeys.length === enabledExperienceKeys.length && nextKeys.every((key, index) => key === enabledExperienceKeys[index])) {
      return;
    }
    setEnabledExperienceKeys(nextKeys);
  }, [editableExperienceHistory, enabledExperienceKeys]);

  function openModal(name) {
    if (name === "settings") {
      fetchJson("/api/settings").then((data) => {
        const identities = normalizeIdentityProfiles(data.identities || []);
        setSettings({ ...data, identities });
        setSettingsDraft({ output_directory: data.output_directory || "", identities });
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
    setShowGeneratedArea(false);
    setLatestAnalysis(null);
    setGeneratedContent("");
    setAiStage("");
    setResumeJobContext(null);
    setEnabledExperienceKeys(allEnabledExperienceKeys(editableExperienceHistory));
    if (clearJd) setComposerInput("");

    if (sessionId) {
      fetchJson("/api/ai/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      }).catch(() => {});
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

  async function continueAiGenerationFromAnalysis({ sessionId, baseThread, enabledKeys }) {
    setAiStage("core");
    const [titleSummaryData, skillsData] = await Promise.all([
      fetchJson("/api/ai/generate-title-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, enabled_experience_keys: enabledKeys }),
      }),
      fetchJson("/api/ai/generate-skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, enabled_experience_keys: enabledKeys }),
      }),
    ]);

    const sessionAfterCore = titleSummaryData.session_id || skillsData.session_id || sessionId;
    const coreContent = combineCoreDraft(titleSummaryData.content, skillsData.content);
    setAiSessionId(sessionAfterCore);
    setShowGeneratedArea(true);
    setGeneratedContent(coreContent);
    setAiThread((current) => [
      ...(current?.length ? current : baseThread),
      {
        kind: "assistant",
        title: "Core Draft Ready",
        lines: ["Title, summary, and technical skills are ready. Professional experience is generating now."],
      },
    ]);

    setAiStage("experience");
    const [recentExperienceData, olderExperienceData] = await Promise.all([
      fetchJson("/api/ai/generate-experience-recent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionAfterCore, enabled_experience_keys: enabledKeys }),
      }),
      fetchJson("/api/ai/generate-experience-older", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionAfterCore, enabled_experience_keys: enabledKeys }),
      }),
    ]);

    const finalExperienceData = recentExperienceData.complete ? recentExperienceData : olderExperienceData;
    const sessionAfterExperience = finalExperienceData.session_id || sessionAfterCore;
    const fullResumeContent = finalExperienceData.content || coreContent;
    setAiSessionId(sessionAfterExperience || null);
    setGeneratedContent(fullResumeContent);
    setShowGeneratedArea(true);

    setAiStage("refinement");
    const reviewedCoreData = await fetchJson("/api/ai/review-core", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionAfterExperience, enabled_experience_keys: enabledKeys }),
    });

    const sessionAfterReview = reviewedCoreData.session_id || sessionAfterExperience;
    const reviewedContent = reviewedCoreData.content || fullResumeContent;
    setAiSessionId(sessionAfterReview || null);
    setGeneratedContent(reviewedContent);
    setShowGeneratedArea(true);
    setComposerInput("");
    setTab("parsed");
    setAiThread((current) => {
      const next = [
        ...(current?.length ? current : baseThread),
        {
          kind: "assistant",
          title: reviewedCoreData.revised ? "Resume Refined" : "Resume Complete",
          lines: [
            reviewedCoreData.revised
              ? "The full resume is ready, and the summary and technical skills were tightened after experience generation."
              : "Complete resume is generated. You can edit it directly in the parsed preview.",
          ],
        },
      ];
      if (reviewedCoreData.title_warnings?.length) {
        next.push({
          kind: "assistant",
          title: "Experience Titles Adjusted",
          lines: ["A few historical job titles were normalized to fit the detected role family."],
          list: reviewedCoreData.title_warnings,
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
      if (autoDetectedNewJd) {
        setAiSessionId(null);
        setMemoryCount(0);
        setGeneratedContent("");
        setPreview(null);
        setValidation({ valid: false, errors: [] });
      }
      setCompanyName("");
      if (!resumeJobContext?.id) setResumeJobContext(null);
      setEnabledExperienceKeys(allEnabledExperienceKeys(editableExperienceHistory));
    }

    try {
      const analyzeData = await fetchJson("/api/ai/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_description: jd,
          revision_request: revisionRequest,
          current_resume_content: generatedContent,
          session_id: aiSessionId,
          reset_memory: isNewJd,
          enabled_experience_keys: sanitizedEnabledExperienceKeys,
        }),
      });

      const nextSessionId = analyzeData.session_id || aiSessionId || null;
      setAiSessionId(nextSessionId);
      setLastGeneratedJd(jd);
      setLatestAnalysis(analyzeData.analysis || null);
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
              enabledKeys: sanitizedEnabledExperienceKeys,
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
        enabledKeys: sanitizedEnabledExperienceKeys,
      });
    } catch (error) {
      const payload = error.data || {};
      if (payload.analysis) {
        setAiSessionId(payload.session_id || aiSessionId || null);
        setMemoryCount(payload.memory_count || 0);
        setAiThread([...baseThread, soulThreadEntry(payload.analysis)]);
        setShowGeneratedArea(true);
      }
      if (payload.content) {
        setGeneratedContent(payload.content);
        setShowGeneratedArea(true);
        setTab("parsed");
      }

      const stageNames = {
        analysis: "JD analysis failed",
        title_summary_generation: "Title and summary generation failed",
        skills_generation: "Skills generation failed",
        core_review: "Resume refinement failed",
        core_generation: "Core resume generation failed",
        experience_generation: "Experience generation failed",
        resume_generation: "Resume generation failed",
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
        setGeneratedContent(payload.content);
        setShowGeneratedArea(true);
        setTab("parsed");
      }
      const stageNames = {
        analysis: "JD analysis failed",
        title_summary_generation: "Title and summary generation failed",
        skills_generation: "Skills generation failed",
        core_review: "Resume refinement failed",
        core_generation: "Core resume generation failed",
        experience_generation: "Experience generation failed",
        resume_generation: "Resume generation failed",
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
        const latestHistory = deriveExperienceHistoryFromContent(generatedContent, editableExperienceHistory);
        await fetchJson(`/api/extension/drafts/${encodeURIComponent(extensionDraftId)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resume_content: generatedContent,
            company_name: companyName,
            identity_id: identity,
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
      const latestHistory = deriveExperienceHistoryFromContent(generatedContent, editableExperienceHistory);

      const data = await fetchJson("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: generatedContent,
          company_name: companyName,
          job_id: resumeJobContext?.id || "",
          contact_override: contact,
          identity,
          experience_history_override: latestHistory,
          enabled_experience_keys: sanitizedEnabledExperienceKeys,
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
    fetchJson("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_directory: settingsDraft.output_directory,
        identities: normalizeIdentityProfiles(settingsDraft.identities || []),
      }),
    })
      .then((data) => {
        const identities = normalizeIdentityProfiles(data.identities || []);
        setSettings((current) => ({ ...current, output_directory: data.output_directory, identities }));
        setSettingsDraft({ output_directory: data.output_directory || "", identities });
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
        setEnabledExperienceKeys(allEnabledExperienceKeys(history));
        const selected = normalizeIdentityProfiles(settings.identities || []).find((item) => item.id === identity);
        setContact(selected ? {
          location: selected.location || "",
          phone: selected.phone || "",
          email: selected.email || "",
        } : (profileData.contact || emptyProfile.contact));
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
    setEditableExperienceHistory((current) => {
      const nextHistory = normalizeInlineExperienceHistory(current).map((item, itemIndex) => (
        itemIndex === index ? { ...item, [field]: value } : item
      ));
      setGeneratedContent((currentContent) => applyExperienceHistoryToGeneratedContent(currentContent, nextHistory));
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
    setEnabledExperienceKeys((current) => {
      const allowedKeys = allEnabledExperienceKeys(editableExperienceHistory);
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
    setIdentity(nextIdentity);
    setContact(selected ? {
      location: selected.location || "",
      phone: selected.phone || "",
      email: selected.email || "",
    } : emptyProfile.contact);
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
    }));
  }

  function removeSettingsIdentity(index) {
    setSettingsDraft((current) => {
      const identities = normalizeIdentityProfiles(current.identities || []);
      if (identities.length <= 1) return current;
      return {
        ...current,
        identities: identities.filter((_, itemIndex) => itemIndex !== index),
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

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-wrap">
          <div className="brand-dot" />
          <div className="brand">Resume Generator</div>
        </div>
        <div className="topbar-actions">
          <button className="icon-button" onClick={() => openModal("profile")}>{onboardingRequired ? "Setup Profile" : "Profile"}</button>
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
                      : aiStage === "core"
                        ? "Building title, summary, and skills..."
                        : aiStage === "experience"
                          ? "Writing the experience section..."
                          : showGeneratedArea
                            ? "Updating the draft for this JD..."
                            : "Reading the JD and building the first draft..."}
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
                    <div className="message-label">
                      {generatingAi && (aiStage === "core" || aiStage === "experience") ? "Core Resume Draft" : "Generated Resume"}
                      {generatingAi && aiStage === "experience" ? <span className="inline-status-pill">Experience still generating</span> : null}
                    </div>
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
                  disabled={extensionDraftLocked}
                  onChange={(e) => setCompanyName(e.target.value)}
                  placeholder="Company name (required)"
                />
                <button
                  className="primary-button"
                  disabled={!profileReady || extensionDraftLocked || !canGeneratePdf || !companyName.trim() || pdfState.mode === "loading" || pdfState.mode === "polling"}
                  onClick={submitPdfGeneration}
                >
                  Generate PDF
                </button>
              </div>
            </div>
            <div className="preview-toolbar-right">
              {tab === "parsed" && preview && !extensionDraftLocked ? (
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
                    disabled={extensionDraftLocked}
                    onClick={() => toggleExperienceKey(item.key)}
                    title={sanitizedEnabledExperienceKeys.includes(item.key) ? "Included in this draft" : "Hidden from this draft"}
                  >
                    {item.company}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="panel-body preview-body">
            {tab === "parsed" ? (
              <>
                {validation.errors?.length ? (
                  <div className="error-list">
                    {validation.errors.map((error, index) => <div key={index}>{error}</div>)}
                  </div>
                ) : null}
                {previewEditMode ? (
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
                      className="preview-editor"
                      value={generatedContent}
                      disabled={extensionDraftLocked}
                      onChange={(e) => setGeneratedContent(e.target.value)}
                    />
                  </div>
                ) : (
                  <ParsedPreview
                    preview={preview}
                    loadingExperience={generatingAi && aiStage === "experience"}
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
        <div className="profile-experience-section">
          <div className="section-label">Contact identities</div>
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
            <input value={companyName || latestAnalysis?.company_name || ""} onChange={(e) => setCompanyName(e.target.value)} />
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

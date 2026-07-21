import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./panel.css";

const ACTIVE_STATUSES = new Set(["queued", "analyzing", "generating_core", "generating_experience", "reviewing", "pdf_generating"]);
const STATUS_LABELS = {
  duplicate_review: "Decision",
  queued: "Waiting",
  analyzing: "Analyzing",
  generating_core: "Core",
  generating_experience: "Experience",
  reviewing: "Reviewing",
  ready: "Ready",
  pdf_generating: "PDF",
  pdf_ready: "PDF Ready",
  failed: "Failed",
  skipped: "Skipped",
  applied: "Applied",
};

function send(message) {
  return chrome.runtime.sendMessage(message);
}

async function api(path, options = {}) {
  const result = await send({ type: "API_REQUEST", path, method: options.method || "GET", body: options.body });
  if (!result?.success) throw new Error(result?.error || "The local resume server is unavailable.");
  return result;
}

function skillsText(skillsPayload) {
  return (skillsPayload?.updated_skills || []).map((skill) => {
    const items = Array.isArray(skill.items) ? skill.items.join(", ") : String(skill.items || "");
    return `${skill.category}: ${items}`;
  }).join("\n");
}

function experienceEditsFromDraft(draft) {
  if (!draft) return [];
  const historyByKey = Object.fromEntries((draft.experience_history_snapshot || []).map((item) => [item.key, item]));
  const generatedByKey = {
    ...((draft.experience_recent || {}).experience || {}),
    ...((draft.experience_older || {}).experience || {}),
  };
  const previewExperience = draft.preview?.experience || [];
  return (draft.enabled_experience_keys || []).map((key, index) => {
    const history = historyByKey[key] || {};
    const generated = generatedByKey[key] || previewExperience[index] || {};
    return {
      key,
      company: history.company || generated.company || "",
      location: history.location || generated.location || "",
      dates: history.dates || generated.dates || "",
      title: generated.title || history.title || "",
      bullets_text: (generated.bullets || []).join("\n"),
    };
  });
}

function quickEditValuesFromDraft(draft) {
  return {
    title: draft?.title_summary?.updated_title || draft?.preview?.title || "",
    summary: draft?.title_summary?.updated_summary || draft?.preview?.summary || "",
    skills_text: skillsText(draft?.skills),
    experience: experienceEditsFromDraft(draft),
  };
}

function emptyContext() {
  return { source: "linkedin", external_job_id: "", url: "", company_name: "", role_title: "", location: "", job_description: "" };
}

function emptyAssistantState() {
  return { recipient_name: "", reachout: "", question: "", followups: [] };
}

function assistantStorageKey(draftId) {
  return `resumeDraftAssistant:${draftId}`;
}

function autofillAnswerStorageKey(draftId) {
  return `resumeAutofillAnswers:${draftId}`;
}

function recentPdfDrafts(drafts) {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  return (drafts || []).filter((item) => {
    const generatedAt = new Date(item.pdf_generated_at || "").getTime();
    return item.status === "pdf_ready" && !item.pdf_stale && item.pdf_path && Number.isFinite(generatedAt) && generatedAt >= cutoff;
  });
}

function generatedAgo(value) {
  const elapsed = Date.now() - new Date(value || "").getTime();
  if (!Number.isFinite(elapsed) || elapsed < 0) return "recently";
  const minutes = Math.max(1, Math.floor(elapsed / 60000));
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

function sourceIdentity(value) {
  if (!value) return "";
  const explicitId = String(value.external_job_id || "").trim();
  if (explicitId) return `linkedin:${explicitId}`;
  const url = String(value.url || value.canonical_url || "");
  const pathId = url.match(/\/jobs\/view\/(\d+)/)?.[1];
  const queryId = url.match(/[?&]currentJobId=(\d+)/)?.[1];
  if (pathId || queryId) return `linkedin:${pathId || queryId}`;
  return [value.source || "linkedin", value.company_name || "", value.role_title || ""].map((item) => String(item).trim().toLowerCase()).join(":");
}

function linkedinSearchUrl(type, query) {
  return `https://www.linkedin.com/search/results/${type}/?keywords=${encodeURIComponent(query)}&origin=GLOBAL_SEARCH_HEADER`;
}

function hiringManagerTitles(roleTitle) {
  const role = String(roleTitle || "").toLowerCase();
  if (/data|analytics|business intelligence/.test(role)) return ["data engineering manager", "director of data engineering"];
  if (/machine learning|\bai\b|artificial intelligence/.test(role)) return ["AI engineering manager", "director of AI engineering"];
  if (/security|cyber/.test(role)) return ["security engineering manager", "director of security engineering"];
  if (/product manager|product owner/.test(role)) return ["director of product", "head of product"];
  if (/business analyst|systems analyst/.test(role)) return ["business systems manager", "director of business systems"];
  if (/gtm|revenue operations|revops|sales operations/.test(role)) return ["GTM leader", "head of revenue operations"];
  if (/frontend|front-end/.test(role)) return ["frontend engineering manager", "director of frontend engineering"];
  if (/backend|back-end|platform|infrastructure/.test(role)) return ["backend engineering manager", "director of platform engineering"];
  return ["engineering manager", "director of engineering"];
}

function searchesForDraft(draft) {
  const company = String(draft?.company_name || "").trim();
  const role = String(draft?.role_title || draft?.analysis?.target_role || "").trim();
  if (!company) return { people: [], posts: [] };
  const managerTitles = hiringManagerTitles(role);
  const peopleQueries = [
    { label: "Technical recruiters", query: `technical recruiter at ${company}` },
    { label: "Talent acquisition", query: `talent acquisition at ${company}` },
    ...managerTitles.map((title, index) => ({ label: index === 0 ? "Likely hiring managers" : "Department leaders", query: `${title} at ${company}` })),
    ...(role ? [{ label: "People in this role", query: `${role} at ${company}` }] : []),
  ];
  const postQueries = [
    ...(role ? [
      { label: "Hiring for this role", query: `${company} hiring ${role}` },
      { label: "Join my team", query: `${company} join my team ${role}` },
      { label: "We are hiring", query: `${company} we are hiring ${role}` },
    ] : []),
    { label: "Company hiring posts", query: `${company} hiring` },
    { label: "Company team posts", query: `${company} join our team` },
  ];
  return {
    people: peopleQueries.map((item) => ({ ...item, url: linkedinSearchUrl("people", item.query) })),
    posts: postQueries.map((item) => ({ ...item, url: linkedinSearchUrl("content", item.query) })),
  };
}

function Preview({ preview }) {
  if (!preview) return <div className="blank-state">Resume content will appear here when generation finishes.</div>;
  return (
    <div className="resume-preview">
      <h2>{preview.name}</h2>
      <div className="resume-contact">{[preview.contact?.location, preview.contact?.phone, preview.contact?.email].filter(Boolean).join(" · ")}</div>
      <h1>{preview.title}</h1>
      <section><h3>Summary</h3><p>{preview.summary}</p></section>
      <section>
        <h3>Technical Skills</h3>
        {(preview.technical_skills || []).map((skill) => <p key={skill.category}><strong>{skill.category}:</strong> {skill.items}</p>)}
      </section>
      <section>
        <h3>Professional Experience</h3>
        {(preview.experience || []).map((item, index) => (
          <article className="experience-row" key={`${item.company}-${index}`}>
            <div className="experience-heading"><strong>{item.company}</strong><span>{item.dates}</span></div>
            <div className="experience-heading"><em>{item.title}</em><span>{item.location}</span></div>
            <ul>{(item.bullets || []).map((bullet, bulletIndex) => <li key={bulletIndex}>{bullet}</li>)}</ul>
          </article>
        ))}
      </section>
    </div>
  );
}

function History({ history }) {
  if (!history?.count) return null;
  return (
    <section className="history-band">
      <div className="section-heading"><strong>{history.count} previous application{history.count === 1 ? "" : "s"}</strong></div>
      {(history.applications || []).map((item) => (
        <div className="history-row" key={item.id || `${item.applied_date}-${item.role_title}`}>
          <div><strong>{item.role_title || item.target_role || "Saved resume"}</strong><span>{item.status || "Applied"}</span></div>
          <small>{item.applied_date || "Date unavailable"}{item.resume_title ? ` · ${item.resume_title}` : ""}</small>
        </div>
      ))}
    </section>
  );
}

const APPLICATION_FIELDS = [
  ["firstName", "First name"], ["middleName", "Middle name"], ["lastName", "Last name"],
  ["addressLine1", "Address line 1"], ["addressLine2", "Address line 2"], ["city", "City"],
  ["state", "State / province"], ["postalCode", "Postal code"], ["country", "Country"],
  ["linkedinUrl", "LinkedIn URL"], ["githubUrl", "GitHub URL"], ["portfolioUrl", "Portfolio URL"],
  ["websiteUrl", "Website URL"], ["yearsOfExperience", "Years of experience"],
  ["currentTitle", "Current title"], ["currentCompany", "Current company"],
  ["highestDegree", "Highest degree"], ["graduationYear", "Graduation year"],
  ["salaryExpectation", "Salary expectation"], ["noticePeriod", "Notice period"],
  ["relocationWilling", "Willing to relocate"], ["workAuthorization", "Authorized to work"],
  ["sponsorshipRequired", "Requires sponsorship"], ["workAuthExpiration", "Authorization expiration"],
  ["j1Visa", "Previously held J-1 visa"],
];

function emptyApplicationProfile() {
  return Object.fromEntries([...APPLICATION_FIELDS.map(([key]) => [key, ""]), ["autoFillEnabled", false], ["customAnswers", {}]]);
}

function customAnswersText(answers) {
  return Object.entries(answers || {}).map(([question, answer]) => `${question} => ${answer}`).join("\n");
}

function parseCustomAnswers(value) {
  const answers = {};
  String(value || "").split("\n").forEach((line) => {
    const separator = line.indexOf("=>");
    if (separator < 1) return;
    const question = line.slice(0, separator).trim();
    const answer = line.slice(separator + 2).trim();
    if (question && answer) answers[question] = answer;
  });
  return answers;
}

function AutofillWorkspace({
  status, profile, application, fullName, identities, identityId, drafts, selectedDraftId,
  busy, message, saveState, answers, answerBusy, onIdentity, onRefresh, onFill, onAttach, onSelectDraft, onAskQuestion, onCopyAnswer,
  onApplication, onFullName, onSave, onImport, onExport, onReset,
}) {
  const percent = status?.totalFields ? Math.round((status.filledFields / status.totalFields) * 100) : 0;
  const unmatched = (status?.fields || []).filter((field) => field.type !== "file" && !field.filled && !field.matched && !field.applicationQuestion);
  const review = (status?.fields || []).filter((field) => field.reviewRequired && !field.filled);
  const questions = status?.questions || [];
  const recentResumes = recentPdfDrafts(drafts);
  const selectedResume = recentResumes.find((item) => item.id === selectedDraftId);
  return (
    <section className="autofill-workspace">
      <div className="autofill-heading">
        <div><h2>Application Autofill</h2><p>{status?.supported ? `${status.platform || "Application"} form` : "Open a supported job application page."}</p></div>
        <button onClick={onRefresh} disabled={busy !== ""}>Refresh</button>
      </div>

      {message ? <div className={message.type === "error" ? "error-band compact" : "success-band"}>{message.text}</div> : null}

      <div className="autofill-status">
        <div><strong>{status?.filledFields || 0}/{status?.totalFields || 0}</strong><span>fields filled</span></div>
        <div><strong>{status?.matchedFields || 0}</strong><span>recognized</span></div>
        <div><strong>{status?.fileFields || 0}</strong><span>file fields</span></div>
      </div>
      <div className="autofill-progress"><span style={{ width: `${percent}%` }} /></div>

      <label>Contact identity<select value={identityId} onChange={(event) => onIdentity(event.target.value)}>{(identities || []).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <div className="autofill-actions">
        <button className="primary" disabled={!status?.supported || !status?.applicationPage || busy !== ""} onClick={onFill}>{busy === "fill" ? "Filling..." : "Fill this page"}</button>
        <label>Resume generated in the last 24 hours<select aria-label="Resume to attach and answer with" value={selectedDraftId} onChange={(event) => onSelectDraft(event.target.value)}><option value="">Select generated resume</option>{recentResumes.map((item) => <option key={item.id} value={item.id}>{item.company_name} - {item.role_title} - {generatedAgo(item.pdf_generated_at)}</option>)}</select></label>
        <button disabled={!selectedDraftId || !status?.fileFields || busy !== ""} onClick={onAttach}>{busy === "attach" ? "Attaching..." : "Attach resume"}</button>
      </div>
      <small className="autofill-note">Existing answers are left unchanged. The extension never submits the application.</small>

      {questions.length ? <section className="application-questions"><div className="application-questions-heading"><strong>Application questions</strong><span>{questions.length}</span></div>{questions.map((question) => {
        const savedCandidate = answers?.[question.questionId];
        const saved = savedCandidate?.resume_revision === selectedResume?.resume_revision ? savedCandidate : null;
        const overLimit = saved?.answer && question.maxLength > 0 && saved.answer.length > question.maxLength;
        return <article className="application-question" data-question-id={question.questionId} key={question.questionId}><div className="application-question-top"><strong>{question.label}</strong>{question.required ? <span>Required</span> : null}</div>{question.maxLength ? <small>Limit: {question.maxLength} characters</small> : null}{question.aiEligible ? <button className="question-ai-button" disabled={!selectedDraftId || answerBusy !== ""} onClick={() => onAskQuestion(question)}>{answerBusy === question.questionId ? "Writing..." : saved ? "Regenerate" : "Ask AI"}</button> : <small className="question-manual-note">{question.aiBlockedReason || "Answer this question manually."}</small>}{saved ? <div className="application-answer"><div><span>{saved.answer.length}{question.maxLength ? `/${question.maxLength}` : ""} characters</span><button onClick={() => onCopyAnswer(saved.answer)}>Copy</button></div><p>{saved.answer}</p>{overLimit ? <small className="field-error">The generated answer is over this field's character limit. Regenerate or shorten it before using it.</small> : null}</div> : null}</article>;
      })}</section> : null}

      {review.length ? <details className="field-review"><summary>{review.length} saved sensitive answer{review.length === 1 ? "" : "s"} available</summary>{review.map((field, index) => <div key={`${field.name}-${index}`}><strong>{field.label}</strong><span>{field.dataField}</span></div>)}</details> : null}
      {unmatched.length ? <details className="field-review"><summary>{unmatched.length} unmatched field{unmatched.length === 1 ? "" : "s"}</summary>{unmatched.map((field, index) => <div key={`${field.name}-${index}`}><strong>{field.label}</strong><span>{field.required ? "Required" : field.type}</span></div>)}</details> : null}

      <details className="autofill-profile-editor">
        <summary>Autofill profile <span>{saveState}</span></summary>
        <section className="autofill-name-section"><h3>Name</h3><label>Full name<input value={fullName} onChange={(event) => onFullName(event.target.value)} /></label><div className="profile-field-grid">{APPLICATION_FIELDS.filter(([key]) => ["firstName", "middleName", "lastName"].includes(key)).map(([key, label]) => <label key={key}>{label}<input value={application[key] || ""} onChange={(event) => onApplication(key, event.target.value)} /></label>)}</div></section>
        <div className="profile-field-grid">
          {APPLICATION_FIELDS.filter(([key]) => !["firstName", "middleName", "lastName"].includes(key)).map(([key, label]) => <label key={key}>{label}<input value={application[key] || ""} onChange={(event) => onApplication(key, event.target.value)} /></label>)}
        </div>
        <label className="autofill-toggle"><input type="checkbox" checked={application.autoFillEnabled !== false} onChange={(event) => onApplication("autoFillEnabled", event.target.checked)} />Fill recognized fields automatically on application pages</label>
        <label>Custom answers<textarea value={customAnswersText(application.customAnswers)} onChange={(event) => onApplication("customAnswers", parseCustomAnswers(event.target.value))} placeholder="Question text => Saved answer" /></label>
        <div className="button-row"><button className="primary" onClick={() => onSave("permanent")}>Save permanently</button><button onClick={() => onSave("session")}>Use this session</button></div>
        <div className="profile-data-actions"><button onClick={onExport}>Export JSON</button><label className="file-button">Import JSON<input type="file" accept="application/json,.json" onChange={onImport} /></label><button className="danger-text" onClick={onReset}>Clear application fields</button></div>
        <small>Email, phone, and location come from the selected contact identity: {profile?.identityLabel || "default"}.</small>
      </details>
    </section>
  );
}

function App() {
  const [server, setServer] = useState(null);
  const [serverUrl, setServerUrl] = useState("http://127.0.0.1:5001");
  const [context, setContext] = useState(null);
  const [contextForm, setContextForm] = useState(emptyContext());
  const [resolution, setResolution] = useState({ history: null, issues: [], draft: null });
  const [drafts, setDrafts] = useState([]);
  const [hiddenDraftIds, setHiddenDraftIds] = useState([]);
  const [draft, setDraft] = useState(null);
  const [viewingCurrent, setViewingCurrent] = useState(true);
  const draftRef = useRef(null);
  const viewingCurrentRef = useRef(true);
  const contextResolveRef = useRef(0);
  const draftLoadRef = useRef(0);
  const selectedDraftIdRef = useRef("");
  const currentContextRef = useRef(null);
  const generatingContextRef = useRef("");
  const [identityId, setIdentityId] = useState("");
  const [enabledKeys, setEnabledKeys] = useState([]);
  const [tab, setTab] = useState("preview");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [quickDraftId, setQuickDraftId] = useState("");
  const [quickHydratedDraftId, setQuickHydratedDraftId] = useState("");
  const [quickEdits, setQuickEdits] = useState({ title: "", summary: "", skills_text: "", experience: [] });
  const [quickDirty, setQuickDirty] = useState(false);
  const [saveState, setSaveState] = useState("");
  const quickDirtyRef = useRef(false);
  const quickEditVersionRef = useRef(0);
  const quickEditsRef = useRef(quickEdits);
  const quickSavePromiseRef = useRef(null);
  const [assistantDraftId, setAssistantDraftId] = useState("");
  const [assistantState, setAssistantState] = useState(emptyAssistantState());
  const [assistantBusy, setAssistantBusy] = useState("");
  const assistantDraftRef = useRef("");
  const [showApply, setShowApply] = useState(false);
  const [applyForm, setApplyForm] = useState({ applied_date: new Date().toISOString().slice(0, 10), status: "Applied", source: "LinkedIn", notes: "" });
  const [workspace, setWorkspace] = useState("resume");
  const [autofillStatus, setAutofillStatus] = useState(null);
  const [autofillProfile, setAutofillProfile] = useState(null);
  const [applicationEdits, setApplicationEdits] = useState(emptyApplicationProfile());
  const [autofillFullName, setAutofillFullName] = useState("");
  const [autofillDraftId, setAutofillDraftId] = useState("");
  const [autofillBusy, setAutofillBusy] = useState("");
  const [autofillMessage, setAutofillMessage] = useState(null);
  const [autofillSaveState, setAutofillSaveState] = useState("");
  const [autofillAnswers, setAutofillAnswers] = useState({});
  const [autofillAnswerBusy, setAutofillAnswerBusy] = useState("");

  async function loadServer() {
    const stored = await send({ type: "GET_SERVER_URL" });
    if (stored?.url) setServerUrl(stored.url);
    try {
      const data = await api("/api/extension/status");
      setServer(data);
      setError("");
      const completeKeys = (data.experience_history || []).filter((item) => item.enabled !== false && item.company && item.location && item.title && item.dates).map((item) => item.key);
      setEnabledKeys((current) => current.length ? current : completeKeys);
      setIdentityId((current) => current || data.identities?.[0]?.id || "");
      return data;
    } catch (loadError) {
      setServer(null);
      setError(loadError.message);
      return null;
    }
  }

  async function loadDrafts() {
    try {
      const data = await api("/api/extension/drafts?limit=50");
      const loadedDrafts = data.drafts || [];
      const availableResumes = recentPdfDrafts(loadedDrafts);
      setDrafts(loadedDrafts);
      setAutofillDraftId((current) => availableResumes.some((item) => item.id === current) ? current : availableResumes[0]?.id || "");
      setServer((current) => current ? { ...current, queue_paused: !!data.queue_paused } : current);
      return loadedDrafts;
    } catch (_) {
      return [];
    }
  }

  useEffect(() => {
    setAutofillAnswers({});
    if (!autofillDraftId) return undefined;
    let cancelled = false;
    chrome.storage.local.get(autofillAnswerStorageKey(autofillDraftId)).then((stored) => {
      const saved = stored[autofillAnswerStorageKey(autofillDraftId)];
      if (!cancelled && saved && typeof saved === "object") setAutofillAnswers(saved);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [autofillDraftId]);

  async function loadAutofillProfile(selectedIdentity = identityId) {
    try {
      const data = await send({ type: "AUTOFILL_GET_PROFILE", identityId: selectedIdentity || "" });
      if (!data?.success) throw new Error(data?.error || "The autofill profile is unavailable.");
      setAutofillProfile(data.profile || null);
      setApplicationEdits({ ...emptyApplicationProfile(), ...(data.application || {}) });
      setAutofillFullName(data.profile?.fullName || "");
      return data;
    } catch (loadError) {
      setAutofillMessage({ type: "error", text: loadError.message });
      return null;
    }
  }

  async function refreshAutofillStatus(selectedIdentity = identityId, selectWorkspace = false) {
    try {
      const result = await send({ type: "AUTOFILL_GET_ACTIVE_STATUS", identityId: selectedIdentity || "" });
      if (!result?.success) throw new Error(result?.error || "Could not inspect this page.");
      setAutofillStatus(result);
      if (selectWorkspace && result.supported && result.applicationPage) setWorkspace("autofill");
      return result;
    } catch (statusError) {
      setAutofillStatus(null);
      setAutofillMessage({ type: "error", text: statusError.message });
      return null;
    }
  }

  async function refreshResumeContext() {
    setBusy("refresh-context");
    setError("");
    try {
      const result = await send({ type: "GET_ACTIVE_CONTEXT", forceRefresh: true });
      if (!result?.context) throw new Error("No LinkedIn job could be read from the active tab.");
      setViewingCurrent(true);
      viewingCurrentRef.current = true;
      await resolveContext(result.context);
    } catch (refreshError) {
      setError(refreshError.message);
    } finally {
      setBusy("");
    }
  }

  async function fillActiveApplication() {
    setAutofillBusy("fill");
    setAutofillMessage(null);
    try {
      const result = await send({ type: "AUTOFILL_FILL_ACTIVE", identityId });
      if (!result?.success && !result?.filledCount) throw new Error(result?.error || "No empty recognized fields could be filled.");
      setAutofillStatus(result.status || autofillStatus);
      setAutofillMessage({ type: "success", text: `Filled ${result.filledCount} field${result.filledCount === 1 ? "" : "s"}. Review the form before submitting.` });
    } catch (fillError) {
      setAutofillMessage({ type: "error", text: fillError.message });
    } finally {
      setAutofillBusy("");
    }
  }

  async function attachResumeToApplication() {
    setAutofillBusy("attach");
    setAutofillMessage(null);
    try {
      const result = await send({ type: "AUTOFILL_ATTACH_RESUME", draftId: autofillDraftId });
      if (!result?.success) throw new Error(result?.error || "The resume could not be attached.");
      setAutofillMessage({ type: "success", text: `${result.filename} was attached. Confirm the file name on the application.` });
      await refreshAutofillStatus();
    } catch (attachError) {
      setAutofillMessage({ type: "error", text: attachError.message });
    } finally {
      setAutofillBusy("");
    }
  }

  async function answerApplicationQuestion(question) {
    if (!autofillDraftId || !question?.questionId || !question.aiEligible) return;
    setAutofillAnswerBusy(question.questionId);
    setAutofillMessage(null);
    try {
      const data = await api(`/api/extension/drafts/${encodeURIComponent(autofillDraftId)}/application-answer`, {
        method: "POST",
        body: { question: question.label, max_characters: question.maxLength || 0 },
      });
      const answer = String(data.answer?.answer || "").trim();
      if (!answer) throw new Error("The AI returned an empty answer.");
      const selectedResume = recentPdfDrafts(drafts).find((item) => item.id === autofillDraftId);
      setAutofillAnswers((current) => {
        const next = { ...current, [question.questionId]: { answer, resume_revision: selectedResume?.resume_revision, created_at: new Date().toISOString() } };
        chrome.storage.local.set({ [autofillAnswerStorageKey(autofillDraftId)]: next }).catch(() => {});
        return next;
      });
    } catch (answerError) {
      setAutofillMessage({ type: "error", text: answerError.message });
    } finally {
      setAutofillAnswerBusy("");
    }
  }

  function updateApplicationField(key, value) {
    setApplicationEdits((current) => ({ ...current, [key]: value }));
    setAutofillSaveState("Unsaved");
  }

  async function saveAutofillProfile(saveTarget) {
    setAutofillSaveState("Saving");
    try {
      const data = await api("/api/extension/autofill-profile", { method: "POST", body: { application: applicationEdits, fullName: autofillFullName, identity_id: identityId, save_target: saveTarget } });
      setAutofillProfile(data.profile || null);
      setApplicationEdits({ ...emptyApplicationProfile(), ...(data.application || {}) });
      setAutofillFullName(data.profile?.fullName || autofillFullName);
      setAutofillSaveState(saveTarget === "permanent" ? "Saved permanently" : "Saved for session");
      await refreshAutofillStatus();
    } catch (saveError) {
      setAutofillSaveState(saveError.message);
    }
  }

  function exportAutofillProfile() {
    const payload = { fullName: autofillFullName, ...applicationEdits };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "job-autofill-profile.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function importAutofillProfile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const imported = JSON.parse(await file.text());
      const source = imported.application && typeof imported.application === "object" ? imported.application : imported;
      const next = { ...emptyApplicationProfile() };
      APPLICATION_FIELDS.forEach(([key]) => { if (source[key] !== undefined) next[key] = String(source[key] ?? ""); });
      next.autoFillEnabled = source.autoFillEnabled !== false;
      next.customAnswers = source.customAnswers && typeof source.customAnswers === "object" ? source.customAnswers : {};
      setApplicationEdits(next);
      setAutofillFullName(String(imported.fullName || imported.name || autofillFullName));
      setAutofillSaveState("Imported, not saved");
    } catch (importError) {
      setAutofillMessage({ type: "error", text: `Import failed: ${importError.message}` });
    }
  }

  function resetAutofillProfile() {
    if (!window.confirm("Clear the application-only fields? Your resume profile and contact identities will stay unchanged.")) return;
    setApplicationEdits(emptyApplicationProfile());
    setAutofillSaveState("Cleared, not saved");
  }

  function commitDraft(nextDraft) {
    selectedDraftIdRef.current = nextDraft?.id || "";
    draftRef.current = nextDraft;
    setDraft(nextDraft);
  }

  async function loadDraft(draftId, select = false) {
    if (!draftId) return null;
    if (select) selectedDraftIdRef.current = draftId;
    else if (selectedDraftIdRef.current !== draftId) return null;
    const requestId = ++draftLoadRef.current;
    try {
      const data = await api(`/api/extension/drafts/${encodeURIComponent(draftId)}`);
      if (requestId !== draftLoadRef.current || selectedDraftIdRef.current !== draftId) return null;
      commitDraft(data.draft);
      setEnabledKeys(data.draft.enabled_experience_keys || []);
      setIdentityId(data.draft.identity_id || "");
      return data.draft;
    } catch (loadError) {
      if (requestId !== draftLoadRef.current || selectedDraftIdRef.current !== draftId) return null;
      setError(loadError.message);
      return null;
    }
  }

  async function resolveContext(nextContext) {
    if (!nextContext) return;
    currentContextRef.current = nextContext;
    const nextIdentity = sourceIdentity(nextContext);
    if (generatingContextRef.current && generatingContextRef.current === nextIdentity) {
      setContext(nextContext);
      setContextForm({ ...emptyContext(), ...nextContext });
      return;
    }
    const requestId = ++contextResolveRef.current;
    setContext(nextContext);
    setContextForm({ ...emptyContext(), ...nextContext });
    viewingCurrentRef.current = true;
    setViewingCurrent(true);
    try {
      const data = await api("/api/extension/contexts/resolve", { method: "POST", body: nextContext });
      if (requestId !== contextResolveRef.current) return;
      setResolution({ history: data.history, issues: data.issues || [], draft: data.draft || null });
      if (data.draft) await loadDraft(data.draft.id, true);
      else {
        if (draftRef.current && sourceIdentity(draftRef.current) === nextIdentity) return;
        draftLoadRef.current += 1;
        commitDraft(null);
      }
      setError("");
    } catch (resolveError) {
      if (requestId !== contextResolveRef.current) return;
      setError(resolveError.message);
    }
  }

  useEffect(() => {
    chrome.storage.local.get("hiddenResumeDraftIds").then((stored) => {
      if (Array.isArray(stored.hiddenResumeDraftIds)) setHiddenDraftIds(stored.hiddenResumeDraftIds);
    }).catch(() => {});
    loadServer().then((ready) => {
      if (!ready) return;
      loadDrafts();
      const initialIdentity = ready.identities?.[0]?.id || "";
      refreshAutofillStatus(initialIdentity, false);
      send({ type: "GET_ACTIVE_CONTEXT" }).then((result) => {
        if (result?.context) resolveContext(result.context);
      });
    });
    const listener = (message) => {
      if (message?.type === "JOB_CONTEXT_CHANGED" && viewingCurrentRef.current) resolveContext(message.context);
      if (message?.type === "AUTOFILL_ACTIVE_STATUS_CHANGED") refreshAutofillStatus();
    };
    chrome.runtime.onMessage.addListener(listener);
    return () => chrome.runtime.onMessage.removeListener(listener);
  }, []);

  useEffect(() => {
    if (!identityId || !server) return;
    loadAutofillProfile(identityId);
    refreshAutofillStatus(identityId);
  }, [identityId]);

  useEffect(() => {
    if (!draft) {
      if (quickDraftId) {
        setQuickDraftId("");
        setQuickHydratedDraftId("");
        setQuickEdits({ title: "", summary: "", skills_text: "", experience: [] });
        quickEditsRef.current = { title: "", summary: "", skills_text: "", experience: [] };
        quickDirtyRef.current = false;
        setQuickDirty(false);
        setSaveState("");
      }
      return;
    }
    const serverValues = quickEditValuesFromDraft(draft);
    const contentAvailable = Boolean(serverValues.title || serverValues.summary || serverValues.skills_text || serverValues.experience.length);
    if (quickDraftId !== draft.id) {
      const nextValues = contentAvailable ? serverValues : { title: "", summary: "", skills_text: "", experience: [] };
      setQuickDraftId(draft.id);
      setQuickEdits(nextValues);
      quickEditsRef.current = nextValues;
      quickDirtyRef.current = false;
      setQuickDirty(false);
      setQuickHydratedDraftId(contentAvailable ? draft.id : "");
      setSaveState("");
      return;
    }
    if (contentAvailable && quickHydratedDraftId !== draft.id) {
      setQuickEdits(serverValues);
      quickEditsRef.current = serverValues;
      quickDirtyRef.current = false;
      setQuickDirty(false);
      setQuickHydratedDraftId(draft.id);
      setSaveState("");
    }
  }, [draft?.id, draft?.status, draft?.title_summary, draft?.preview, draft?.skills, quickDraftId, quickHydratedDraftId]);

  useEffect(() => {
    assistantDraftRef.current = draft?.id || "";
    if (!draft?.id) {
      setAssistantDraftId("");
      setAssistantState(emptyAssistantState());
      setAssistantBusy("");
      return;
    }
    if (assistantDraftId === draft.id) return;
    setAssistantDraftId(draft.id);
    setAssistantState(emptyAssistantState());
    setAssistantBusy("");
    let cancelled = false;
    chrome.storage.local.get(assistantStorageKey(draft.id)).then((stored) => {
      const saved = stored[assistantStorageKey(draft.id)];
      if (!cancelled && saved && typeof saved === "object") setAssistantState({ ...emptyAssistantState(), ...saved, question: "" });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [draft?.id, assistantDraftId]);

  const hasActiveWork = useMemo(() => drafts.some((item) => ACTIVE_STATUSES.has(item.status)) || ACTIVE_STATUSES.has(draft?.status), [drafts, draft]);
  const visibleDrafts = useMemo(() => drafts.filter((item) => !hiddenDraftIds.includes(item.id)), [drafts, hiddenDraftIds]);
  useEffect(() => {
    if (!hasActiveWork) return undefined;
    const timer = setInterval(async () => {
      await loadDrafts();
      if (draft?.id) await loadDraft(draft.id);
    }, 1600);
    return () => clearInterval(timer);
  }, [hasActiveWork, draft?.id]);

  async function persistQuickEdits() {
    if (quickSavePromiseRef.current) {
      await quickSavePromiseRef.current;
      if (!quickDirtyRef.current) return draftRef.current;
    }
    const activeDraft = draftRef.current;
    if (!activeDraft || !quickDirtyRef.current || !["ready", "pdf_ready"].includes(activeDraft.status) || activeDraft.locked) return activeDraft;
    const version = quickEditVersionRef.current;
    const edits = quickEditsRef.current;
    quickDirtyRef.current = false;
    setQuickDirty(false);
    setSaveState("Saving");
    const request = api(`/api/extension/drafts/${activeDraft.id}`, { method: "PATCH", body: { quick_edits: edits } })
      .then((data) => {
        commitDraft(data.draft);
        if (quickEditVersionRef.current === version) setSaveState("Saved");
        else {
          quickDirtyRef.current = true;
          setQuickDirty(true);
        }
        loadDrafts();
        return data.draft;
      })
      .catch((saveError) => {
        quickDirtyRef.current = true;
        setQuickDirty(true);
        setSaveState(saveError.message);
        throw saveError;
      })
      .finally(() => { quickSavePromiseRef.current = null; });
    quickSavePromiseRef.current = request;
    return request;
  }

  useEffect(() => {
    if (!quickDirty || !draft || quickDraftId !== draft.id || quickHydratedDraftId !== draft.id || !["ready", "pdf_ready"].includes(draft.status) || draft.locked) return undefined;
    const timer = setTimeout(() => { persistQuickEdits().catch(() => {}); }, 700);
    return () => clearTimeout(timer);
  }, [quickDirty, quickEdits, quickDraftId, quickHydratedDraftId, draft?.id, draft?.status]);

  const profileHistory = draft?.experience_history_snapshot || server?.experience_history || [];
  const visibleExperiences = profileHistory.filter((item) => item.enabled !== false && item.company && item.location && item.title && item.dates);
  const contextComplete = contextForm.company_name.trim() && contextForm.role_title.trim() && contextForm.job_description.trim().length >= 120;
  const draftSearches = useMemo(() => searchesForDraft(draft), [draft?.company_name, draft?.role_title, draft?.analysis]);

  function updateExperienceEdit(key, field, value) {
    updateQuickEdits((current) => ({
      ...current,
      experience: (current.experience || []).map((item) => item.key === key ? { ...item, [field]: value } : item),
    }));
  }

  function updateQuickEdits(nextValue) {
    setQuickEdits((current) => {
      const next = typeof nextValue === "function" ? nextValue(current) : nextValue;
      quickEditsRef.current = next;
      quickEditVersionRef.current += 1;
      quickDirtyRef.current = true;
      return next;
    });
    setQuickDirty(true);
  }

  async function generateResume() {
    const generationIdentity = sourceIdentity(contextForm);
    generatingContextRef.current = generationIdentity;
    contextResolveRef.current += 1;
    setBusy("generate");
    setError("");
    try {
      const data = await api("/api/extension/drafts", { method: "POST", body: { context: contextForm, identity_id: identityId, enabled_experience_keys: enabledKeys } });
      if (viewingCurrentRef.current && sourceIdentity(currentContextRef.current || contextForm) === generationIdentity) {
        draftLoadRef.current += 1;
        commitDraft(data.draft);
        setResolution((current) => ({ ...current, history: data.history, draft: data.draft }));
      }
      setServer((current) => current ? { ...current, queue_paused: data.queue_paused } : current);
      await loadDrafts();
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      if (generatingContextRef.current === generationIdentity) generatingContextRef.current = "";
      setBusy("");
    }
  }

  async function runDraftAction(action, body = {}) {
    if (!draft) return;
    setBusy(action);
    setError("");
    try {
      const data = await api(`/api/extension/drafts/${draft.id}/${action}`, { method: "POST", body });
      commitDraft(data.draft);
      if (typeof data.queue_paused === "boolean") setServer((current) => current ? { ...current, queue_paused: data.queue_paused } : current);
      await loadDrafts();
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setBusy("");
    }
  }

  async function generateDraftPdf() {
    if (!draftRef.current) return;
    setTab("pdf");
    setBusy("pdf");
    setError("");
    try {
      await persistQuickEdits();
      const activeDraft = draftRef.current;
      if (!activeDraft || activeDraft.status !== "ready") throw new Error("Wait for the latest resume edits to finish saving.");
      const data = await api(`/api/extension/drafts/${activeDraft.id}/pdf`, { method: "POST", body: {} });
      commitDraft(data.draft);
      await loadDrafts();
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setBusy("");
    }
  }

  async function toggleExperience(key) {
    const next = enabledKeys.includes(key) ? enabledKeys.filter((item) => item !== key) : [...enabledKeys, key];
    if (!next.length) return;
    setEnabledKeys(next);
    if (!draft || draft.locked || ACTIVE_STATUSES.has(draft.status)) return;
    try {
      const data = await api(`/api/extension/drafts/${draft.id}`, { method: "PATCH", body: { enabled_experience_keys: next } });
      commitDraft(data.draft);
      loadDrafts();
    } catch (toggleError) {
      setEnabledKeys(draft.enabled_experience_keys || []);
      setError(toggleError.message);
    }
  }

  async function changeIdentity(nextIdentity) {
    setIdentityId(nextIdentity);
    if (!draft || draft.locked || ACTIVE_STATUSES.has(draft.status)) return;
    try {
      const data = await api(`/api/extension/drafts/${draft.id}`, { method: "PATCH", body: { identity_id: nextIdentity } });
      commitDraft(data.draft);
      loadDrafts();
    } catch (identityError) {
      setError(identityError.message);
    }
  }

  async function markApplied(event) {
    event.preventDefault();
    await runDraftAction("mark-applied", applyForm);
    setShowApply(false);
  }

  async function persistAssistant(draftId, nextState) {
    await chrome.storage.local.set({ [assistantStorageKey(draftId)]: { ...nextState, question: "" } });
    if (assistantDraftRef.current === draftId) setAssistantState(nextState);
  }

  async function generateReachout() {
    if (!draft?.id) return;
    const draftId = draft.id;
    const currentAssistant = assistantState;
    setAssistantBusy("reachout");
    setError("");
    try {
      const data = await api(`/api/extension/drafts/${draftId}/reachout`, {
        method: "POST",
        body: { recipient_name: currentAssistant.recipient_name },
      });
      await persistAssistant(draftId, { ...currentAssistant, reachout: data.reachout?.message || "" });
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setAssistantBusy("");
    }
  }

  async function generateFollowup() {
    const question = assistantState.question.trim();
    if (!draft?.id || !question) return;
    const draftId = draft.id;
    const currentAssistant = assistantState;
    setAssistantBusy("followup");
    setError("");
    try {
      const data = await api(`/api/extension/drafts/${draftId}/followup`, {
        method: "POST",
        body: { question },
      });
      const answer = data.followup?.answer || "";
      await persistAssistant(draftId, {
        ...currentAssistant,
        question: "",
        followups: [...(currentAssistant.followups || []), { question, answer, created_at: new Date().toISOString() }],
      });
    } catch (actionError) {
      setError(actionError.message);
    } finally {
      setAssistantBusy("");
    }
  }

  async function copyText(value) {
    if (!value) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_) {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.setAttribute("readonly", "");
      Object.assign(textarea.style, { position: "fixed", left: "-9999px", top: "0", opacity: "0" });
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      if (!copied) throw new Error("Clipboard access was blocked by the browser.");
      return true;
    }
  }

  async function copyAutofillAnswer(value) {
    try {
      await copyText(value);
      setAutofillMessage({ type: "success", text: "Answer copied to clipboard." });
    } catch (copyError) {
      setAutofillMessage({ type: "error", text: copyError.message });
    }
  }

  async function selectDraft(item) {
    contextResolveRef.current += 1;
    viewingCurrentRef.current = false;
    setViewingCurrent(false);
    setTab(item.status === "pdf_ready" ? "pdf" : "preview");
    setResolution({ history: null, issues: [], draft: item });
    const loaded = await loadDraft(item.id, true);
    if (loaded) {
      setContextForm({
        source: loaded.source || "linkedin",
        external_job_id: loaded.external_job_id || "",
        url: loaded.canonical_url || "",
        company_name: loaded.company_name || "",
        role_title: loaded.role_title || "",
        location: loaded.location || "",
        job_description: loaded.job_description || "",
      });
    }
  }

  async function openLinkedInJob(item) {
    const result = await send({ type: "OPEN_LINKEDIN_JOB", url: item.canonical_url });
    if (!result?.success) setError(result?.error || "This draft does not have a LinkedIn job link.");
  }

  async function openLinkedInSearch(url) {
    const result = await send({ type: "OPEN_LINKEDIN_SEARCH", url });
    if (!result?.success) setError(result?.error || "Could not open the LinkedIn search.");
  }

  function hideRecentDraft(draftId) {
    setHiddenDraftIds((current) => {
      const next = [...new Set([...current, draftId])];
      chrome.storage.local.set({ hiddenResumeDraftIds: next }).catch(() => {});
      return next;
    });
  }

  if (!server) {
    return (
      <main className="panel-shell centered">
        <div className="brand-row"><span className="brand-mark" />Resume Generator</div>
        <h1>Start the local resume app</h1>
        <p>The extension could not reach <code>{serverUrl}</code>.</p>
        <pre>./run_local.sh</pre>
        {error ? <div className="error-band">{error}</div> : null}
        <div className="button-row"><button className="primary" onClick={loadServer}>Retry</button><button onClick={() => chrome.runtime.openOptionsPage()}>Connection</button></div>
      </main>
    );
  }

  if (server.onboarding_required) {
    return (
      <main className="panel-shell centered">
        <div className="brand-row"><span className="brand-mark" />Resume Generator</div>
        <h1>Complete your profile</h1>
        <p>Add your contact details and at least one complete experience before generating resumes.</p>
        <button className="primary" onClick={() => send({ type: "OPEN_APP" })}>Open Profile Setup</button>
      </main>
    );
  }

  return (
    <main className="panel-shell">
      <header className="panel-header">
        <div className="brand-row"><span className="brand-mark" />Resume Generator</div>
        <div className={`server-state ${server.queue_paused ? "paused" : ""}`}>{server.queue_paused ? "Queue paused" : "Local"}</div>
      </header>

      <nav className="workspace-tabs" aria-label="Extension workspace">
        <button className={workspace === "resume" ? "active" : ""} onClick={() => setWorkspace("resume")}>Resume</button>
        <button className={workspace === "autofill" ? "active" : ""} onClick={() => { setWorkspace("autofill"); refreshAutofillStatus(); }}>Autofill{autofillStatus?.supported && autofillStatus.totalFields ? ` ${autofillStatus.filledFields}/${autofillStatus.totalFields}` : ""}</button>
        {workspace === "resume" ? <button className="workspace-refresh" disabled={busy === "refresh-context"} onClick={refreshResumeContext}>{busy === "refresh-context" ? "Reading..." : "Refresh"}</button> : null}
      </nav>

      {workspace === "autofill" ? (
        <AutofillWorkspace
          status={autofillStatus}
          profile={autofillProfile}
          application={applicationEdits}
          fullName={autofillFullName}
          identities={server.identities}
          identityId={identityId}
          drafts={drafts}
          selectedDraftId={autofillDraftId}
          busy={autofillBusy}
          message={autofillMessage}
          saveState={autofillSaveState}
          answers={autofillAnswers}
          answerBusy={autofillAnswerBusy}
          onIdentity={setIdentityId}
          onRefresh={() => refreshAutofillStatus()}
          onFill={fillActiveApplication}
          onAttach={attachResumeToApplication}
          onSelectDraft={setAutofillDraftId}
          onAskQuestion={answerApplicationQuestion}
          onCopyAnswer={copyAutofillAnswer}
          onApplication={updateApplicationField}
          onFullName={(value) => { setAutofillFullName(value); setAutofillSaveState("Unsaved"); }}
          onSave={saveAutofillProfile}
          onImport={importAutofillProfile}
          onExport={exportAutofillProfile}
          onReset={resetAutofillProfile}
        />
      ) : (
        <>

      {visibleDrafts.length ? (
        <nav className="draft-tray" aria-label="Recent resume drafts">
          {visibleDrafts.map((item) => (
            <div className={`draft-tray-item ${draft?.id === item.id && !viewingCurrent ? "active" : ""}`} key={item.id}>
              <button className="draft-select" onClick={() => selectDraft(item)}>
                <span>{item.company_name}</span><small>{STATUS_LABELS[item.status] || item.status}</small>
              </button>
              <div className="draft-tray-actions">
                {item.canonical_url ? <button className="draft-job-link" title={`Open ${item.role_title || "job"} on LinkedIn in a new tab`} onClick={() => openLinkedInJob(item)}>LinkedIn</button> : <span />}
                <button className="draft-hide" title={`Remove ${item.company_name} from recent drafts`} aria-label={`Remove ${item.company_name} from recent drafts`} onClick={() => hideRecentDraft(item.id)}>X</button>
              </div>
            </div>
          ))}
        </nav>
      ) : null}

      {!viewingCurrent && context ? <button className="current-job-link" onClick={() => resolveContext(context)}>Back to current LinkedIn job</button> : null}
      {error ? <div className="error-band">{error}</div> : null}

      {viewingCurrent && !context ? (
        <div className="blank-state"><h2>{visibleDrafts.length ? "Select a recent draft" : "No LinkedIn job selected"}</h2><p>{visibleDrafts.length ? "Choose a draft above to review progress or answer follow-up questions. This page is not being read." : "Open a LinkedIn job to create a resume. On other pages, the extension stays available without reading page content."}</p><button onClick={() => send({ type: "GET_ACTIVE_CONTEXT" }).then((result) => result?.context && resolveContext(result.context))}>Check LinkedIn again</button></div>
      ) : null}

      {(context || draft) ? (
        <>
          <section className="job-band">
            <label>Company<input value={contextForm.company_name} disabled={!viewingCurrent || !!draft?.locked} onChange={(event) => setContextForm({ ...contextForm, company_name: event.target.value })} /></label>
            <label>Role<input value={contextForm.role_title} disabled={!viewingCurrent || !!draft?.locked} onChange={(event) => setContextForm({ ...contextForm, role_title: event.target.value })} /></label>
            <div className="job-meta">{contextForm.location || "Location not provided"}</div>
            {viewingCurrent ? (
              <details><summary>Review extracted job description</summary><textarea value={contextForm.job_description} onChange={(event) => setContextForm({ ...contextForm, job_description: event.target.value })} /></details>
            ) : null}
          </section>

          <History history={resolution.history} />

          {!draft ? (
            <section className="setup-band">
              <div className="field-row">
                <label>Contact identity<select value={identityId} onChange={(event) => setIdentityId(event.target.value)}>{(server.identities || []).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
              </div>
              <div className="experience-pills">{visibleExperiences.map((item) => <button key={item.key} className={enabledKeys.includes(item.key) ? "active" : ""} onClick={() => toggleExperience(item.key)}>{item.company}</button>)}</div>
              <button className="primary wide" disabled={!contextComplete || busy === "generate" || !server.ai_ready} onClick={generateResume}>{busy === "generate" ? "Starting..." : "Generate Resume"}</button>
              {!server.ai_ready ? <small className="field-error">{server.ai_message}</small> : null}
            </section>
          ) : null}

          {draft ? (
            <section className="draft-workspace">
              <div className="draft-status-row"><strong>{STATUS_LABELS[draft.status] || draft.status}</strong><span>{draft.stage?.replaceAll("_", " ")}</span></div>
              {draft.source_changed && viewingCurrent ? <div className="warning-band">LinkedIn changed this job description. Your current resume was preserved.<button onClick={() => window.confirm("Replace this draft using the latest job description?") && runDraftAction("regenerate", { context: contextForm })}>Regenerate</button></div> : null}
              {draft.status === "duplicate_review" ? (
                <div className="decision-band"><strong>Previous applications found</strong><p>Generation has not called the AI yet. Choose whether to continue.</p><div className="button-row"><button className="primary" onClick={() => runDraftAction("duplicate-decision", { decision: "continue" })}>Continue</button><button onClick={() => runDraftAction("duplicate-decision", { decision: "skip" })}>Skip</button></div></div>
              ) : null}
              {draft.status === "failed" ? <div className="error-band"><strong>{draft.error_stage}</strong><p>{draft.error_message}</p><button onClick={() => runDraftAction("retry")}>Retry from checkpoint</button></div> : null}
              {ACTIVE_STATUSES.has(draft.status) ? <div className="progress-line"><span /></div> : null}

              <div className="draft-settings">
                <select value={identityId} disabled={draft.locked || ACTIVE_STATUSES.has(draft.status)} onChange={(event) => changeIdentity(event.target.value)}>{(server.identities || []).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
                <div className="experience-pills">{visibleExperiences.map((item) => <button key={item.key} disabled={draft.locked || ACTIVE_STATUSES.has(draft.status)} className={enabledKeys.includes(item.key) ? "active" : ""} onClick={() => toggleExperience(item.key)}>{item.company}</button>)}</div>
              </div>

              {draft.resume_content ? (
                <>
                  <div className="view-tabs"><button className={tab === "preview" ? "active" : ""} onClick={() => setTab("preview")}>Resume</button><button className={tab === "pdf" ? "active" : ""} onClick={() => setTab("pdf")}>PDF</button><button className={tab === "messages" ? "active" : ""} onClick={() => setTab("messages")}>Messages</button><button className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}>Search</button></div>
                  {tab === "preview" ? (
                    <>
                      {["ready", "pdf_ready"].includes(draft.status) && !draft.locked ? (
                        <details className="quick-editor"><summary>Edit resume content <span>{saveState}</span></summary><label>Resume title<input value={quickEdits.title} onChange={(event) => updateQuickEdits({ ...quickEditsRef.current, title: event.target.value })} /></label><label>Summary<textarea value={quickEdits.summary} onChange={(event) => updateQuickEdits({ ...quickEditsRef.current, summary: event.target.value })} /></label><label>Technical skills<textarea className="skills-editor" value={quickEdits.skills_text} onChange={(event) => updateQuickEdits({ ...quickEditsRef.current, skills_text: event.target.value })} /></label><div className="experience-editor"><h4>Work experience</h4>{(quickEdits.experience || []).map((item) => <details className="experience-editor-row" key={item.key}><summary>{item.company || "Work experience"}<span>{item.title}</span></summary><div className="experience-metadata-grid"><label>Company<input value={item.company} onChange={(event) => updateExperienceEdit(item.key, "company", event.target.value)} /></label><label>Location<input value={item.location} onChange={(event) => updateExperienceEdit(item.key, "location", event.target.value)} /></label></div><label>Dates<input value={item.dates} onChange={(event) => updateExperienceEdit(item.key, "dates", event.target.value)} /></label><label>Role title<input value={item.title} onChange={(event) => updateExperienceEdit(item.key, "title", event.target.value)} /></label><label>Bullets, one per line<textarea className="experience-bullets-editor" value={item.bullets_text} onChange={(event) => updateExperienceEdit(item.key, "bullets_text", event.target.value)} /></label></details>)}</div></details>
                      ) : null}
                      <Preview preview={draft.preview} />
                    </>
                  ) : tab === "pdf" ? (
                    <div className="pdf-view">{draft.status === "pdf_ready" && !draft.pdf_stale ? <iframe title="Generated resume PDF" src={`${serverUrl}/api/download?path=${encodeURIComponent(draft.pdf_path)}&preview=true`} /> : <div className="blank-state">{draft.status === "pdf_generating" ? "Generating PDF..." : "Generate the latest PDF to preview it here."}</div>}</div>
                  ) : tab === "messages" ? (
                    <div className="message-tools">
                      <section className="message-tool">
                        <div className="message-tool-heading"><div><strong>LinkedIn reachout</strong><small>Uses this draft's final edited resume and job description.</small></div>{assistantState.reachout ? <button onClick={() => copyText(assistantState.reachout)}>Copy</button> : null}</div>
                        <label>Recipient name, optional<input value={assistantState.recipient_name} onChange={(event) => setAssistantState({ ...assistantState, recipient_name: event.target.value })} placeholder="Alex" /></label>
                        <button className="primary" disabled={assistantBusy !== "" || !draft.resume_content} onClick={generateReachout}>{assistantBusy === "reachout" ? "Writing..." : assistantState.reachout ? "Rewrite Reachout" : "Generate Reachout"}</button>
                        {assistantState.reachout ? <div className="generated-message">{assistantState.reachout}</div> : null}
                      </section>

                      <section className="message-tool">
                        <div className="message-tool-heading"><div><strong>Application follow-up</strong><small>Uses the latest generated PDF, including your edits.</small></div></div>
                        <label>Question<textarea value={assistantState.question} onChange={(event) => setAssistantState({ ...assistantState, question: event.target.value })} placeholder="Why are you interested in this role?" /></label>
                        <button className="primary" disabled={assistantBusy !== "" || !assistantState.question.trim() || !draft.pdf_path || draft.pdf_stale} onClick={generateFollowup}>{assistantBusy === "followup" ? "Writing..." : "Answer Question"}</button>
                        {!draft.pdf_path || draft.pdf_stale ? <small className="field-error">Generate the latest PDF before using follow-up answers.</small> : null}
                        {(assistantState.followups || []).slice().reverse().map((item, index) => <article className="followup-result" key={`${item.created_at}-${index}`}><div className="message-tool-heading"><strong>{item.question}</strong><button onClick={() => copyText(item.answer)}>Copy</button></div><p>{item.answer}</p></article>)}
                      </section>
                    </div>
                  ) : (
                    <div className="search-tools">
                      <div className="search-intro"><strong>Find the right people</strong><p>These buttons open focused LinkedIn searches. The extension does not collect profiles or send messages.</p></div>
                      <section className="search-group">
                        <h4>People</h4>
                        {draftSearches.people.map((item) => <button className="search-row" key={item.query} onClick={() => openLinkedInSearch(item.url)}><span><strong>{item.label}</strong><small>{item.query}</small></span><b>Open</b></button>)}
                      </section>
                      <section className="search-group">
                        <h4>Hiring posts</h4>
                        {draftSearches.posts.map((item) => <button className="search-row" key={item.query} onClick={() => openLinkedInSearch(item.url)}><span><strong>{item.label}</strong><small>{item.query}</small></span><b>Open</b></button>)}
                      </section>
                    </div>
                  )}
                  <div className="action-bar">
                    <button onClick={() => send({ type: "OPEN_EDITOR", draftId: draft.id })}>Open Full Editor</button>
                    <button className="primary" disabled={draft.locked || draft.status !== "ready" || busy === "pdf"} onClick={generateDraftPdf}>{busy === "pdf" ? "Saving..." : "Generate PDF"}</button>
                    <button disabled={draft.status !== "pdf_ready" || draft.pdf_stale || draft.locked} onClick={() => setShowApply(true)}>{draft.locked ? "Applied" : "Mark Applied"}</button>
                  </div>
                </>
              ) : null}
            </section>
          ) : null}

          {showApply && draft ? <form className="apply-band" onSubmit={markApplied}><div className="section-heading"><strong>Mark application as submitted</strong><button type="button" onClick={() => setShowApply(false)}>Close</button></div><label>Applied date<input type="date" value={applyForm.applied_date} onChange={(event) => setApplyForm({ ...applyForm, applied_date: event.target.value })} /></label><label>Status<select value={applyForm.status} onChange={(event) => setApplyForm({ ...applyForm, status: event.target.value })}>{["Applied", "Updated", "Converted", "Ghosted", "Rejected"].map((item) => <option key={item}>{item}</option>)}</select></label><label>Source<input value={applyForm.source} onChange={(event) => setApplyForm({ ...applyForm, source: event.target.value })} /></label><label>Notes<textarea value={applyForm.notes} onChange={(event) => setApplyForm({ ...applyForm, notes: event.target.value })} /></label><button className="primary" type="submit">Confirm Applied</button></form> : null}
        </>
      ) : null}
        </>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);

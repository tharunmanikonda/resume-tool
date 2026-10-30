import React, { useEffect, useRef, useState } from "react";

export default function JdDraftExperiment({ enabled, jobDescription, enabledKeys, resumeMode, request, disabled = false }) {
  const [phase, setPhase] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const runId = useRef(0);
  const keys = (enabledKeys || []).join(",");
  const modeLabel = { professional: "Professional", internship: "Internship", coop: "Co-op", new_grad: "New Grad" }[resumeMode] || "Professional";
  useEffect(() => {
    runId.current += 1;
    setResult(null);
    setError("");
    setPhase("");
  }, [jobDescription, keys, resumeMode]);

  async function generate() {
    const id = ++runId.current;
    setError("");
    setResult(null);
    setPhase("Planning project stories…");
    try {
      const plan = await request("/api/ai/jd-draft/plan", {
        job_description: jobDescription, enabled_experience_keys: enabledKeys, resume_mode: resumeMode,
      });
      if (id !== runId.current) return;
      setPhase("Writing and checking the draft…");
      const draft = await request("/api/ai/jd-draft/generate", { plan_id: plan.plan_id, resume_mode: resumeMode });
      if (id === runId.current) setResult(draft);
    } catch (e) {
      if (id === runId.current) setError(e.message || "Draft could not be generated.");
    } finally {
      if (id === runId.current) setPhase("");
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([result.markdown], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "proposed-jd-draft.md";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  if (!enabled) return null;
  return <section aria-label="Experimental JD-only draft" style={{ margin: "12px 0", padding: 14, border: "1px solid #cbd5e1", borderRadius: 10, maxHeight: 540, overflowY: "auto" }}>
    <strong>JD-only draft · Experimental</strong>
    <p style={{ fontSize: 13 }}>Profile mode: <strong>{modeLabel}</strong>{resumeMode !== "professional" ? " · Prior experience with mid-level engineering scope." : ""}</p>
    <p style={{ fontSize: 13 }}>Explore project stories from this job description using employment headings only. Project details and numbers are proposed, not confirmed work history.</p>
    <button type="button" disabled={disabled || !!phase || !jobDescription?.trim()} onClick={generate}>
      {phase || "Explore JD-only draft"}
    </button>
    {phase ? <p role="status">{phase}</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {result ? <>
      <p><strong>Proposed draft — review assumptions and measurements before use.</strong></p>
      <button type="button" onClick={download}>Download proposed draft</button>
      <h3>{result.draft.headline}</h3>
      <p>{result.draft.summary}</p>
      {result.review ? <details open><summary>{result.review.findings.length ? "Draft review: changes suggested" : "Ready to review assumptions"}</summary>
        <p>{result.review.summary}</p>
        <ul>{result.review.findings.map((finding, i) => <li key={i}>{finding.issue}</li>)}</ul>
      </details> : null}
      <details><summary>Required work and optional strengths</summary>
        <p>{result.plan.role_positioning}</p>
        <strong>Required</strong><ul>{result.plan.required.map((r, i) => <li key={i}>{r.capability}</li>)}</ul>
        <strong>Optional</strong><ul>{result.plan.optional.map((r, i) => <li key={i}>{r.capability}</li>)}</ul>
      </details>
      {Object.entries(result.draft.experience).map(([key, role]) => <article key={key}>
        <h4>{(result.employment_headings || []).find(h => h.key === key)?.company || key}</h4>
        <p><strong>{result.plan.experience[key].system}</strong></p>
        <p>{result.plan.experience[key].workflow}</p>
        <ul>{role.bullets.map((b, i) => <li key={i}>{b.text}</li>)}</ul>
        <details><summary>Proposed scope and assumptions</summary>
          <p>{result.plan.experience[key].scope}</p>
          <ul>{result.plan.experience[key].assumptions.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </details>
      </article>)}
      {(result.numerical_notes || []).map((note, i) => <p key={i}>{note}</p>)}
    </> : null}
  </section>;
}

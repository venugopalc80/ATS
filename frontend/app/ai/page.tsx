"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, API_BASE } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Job = { id: string; title: string; description?: string | null; status: string };
type Candidate = { id: string; first_name: string; last_name?: string | null; current_title?: string | null };
type Output = { run: { id: string; task: string; status: string; created_at: string; retention_expires_at: string }; output: { text: string; draft_only?: boolean; draft_record?: { id: string; version_number: number; status: string } }; evidence_references: Array<{ record_type: string; id: string; fields?: string[] }>; model: { provider: string; name: string; version: string; prompt_version: string }; limitations: string[]; human_review_required: boolean };
type UseCaseKey = "recruitment_assistant" | "job_description_writer" | "interview_preparation" | "explainable_recommendations" | "fairness_monitoring" | "model_governance";

const useCases: Array<{ key: UseCaseKey; name: string; purpose: string }> = [
  { key: "recruitment_assistant", name: "AI Recruitment Assistant", purpose: "Summarise CVs, extract stated job requirements, draft candidate messages and answer from authorised recruitment records." },
  { key: "job_description_writer", name: "Job Description Writing", purpose: "Create editable, evidence-based job description drafts for human review." },
  { key: "interview_preparation", name: "Interview Preparation", purpose: "Suggest job-related interview questions mapped to role competencies." },
  { key: "explainable_recommendations", name: "Explainable Recommendations", purpose: "Explain recorded recommendations using their original inputs and evidence." },
  { key: "fairness_monitoring", name: "Fairness Monitoring", purpose: "Review approved aggregate process outcomes without inferring protected traits." },
  { key: "model_governance", name: "AI Governance", purpose: "Track approved use cases, model versions, evaluations, incidents and limitations." },
];

export default function AIWorkspacePage() {
  const organizationId = getActiveOrganizationId();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [task, setTask] = useState("summarize_candidate");
  const [jobId, setJobId] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [interviewId, setInterviewId] = useState("");
  const [recommendationId, setRecommendationId] = useState("");
  const [userRequest, setUserRequest] = useState("");
  const [result, setResult] = useState<Output | null>(null);
  const [editedText, setEditedText] = useState("");
  const [savingDraft, setSavingDraft] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [feedback, setFeedback] = useState("");
  const [governance, setGovernance] = useState<Record<string, unknown> | null>(null);
  const [showGovernance, setShowGovernance] = useState(false);
  const [useCaseKey, setUseCaseKey] = useState<UseCaseKey>("recruitment_assistant");
  const [providerApproved, setProviderApproved] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [approvalStatus, setApprovalStatus] = useState("pending");
  const [provider, setProvider] = useState("openai-compatible");
  const [modelName, setModelName] = useState("gpt-4.1-mini");
  const [modelVersion, setModelVersion] = useState("1");
  const [dataProcessingApproved, setDataProcessingApproved] = useState(false);
  const [modelStatus, setModelStatus] = useState("draft");

  useEffect(() => {
    if (!API_BASE || !organizationId) return;
    let cancelled = false;
    async function load() {
      try {
        const [jobsResponse, candidatesResponse] = await Promise.all([
          apiFetch(API_BASE + "/api/jobs?organization_id=" + encodeURIComponent(organizationId)),
          apiFetch(API_BASE + "/api/candidates?organization_id=" + encodeURIComponent(organizationId)),
        ]);
        if (!jobsResponse.ok || !candidatesResponse.ok) throw new Error("Unable to load authorised recruitment records.");
        const [jobRows, candidateRows] = await Promise.all([jobsResponse.json(), candidatesResponse.json()]);
        if (!cancelled) { setJobs(jobRows); setCandidates(candidateRows); }
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "Unable to load records.");
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [organizationId]);

  async function generate(event: FormEvent) {
    event.preventDefault();
    if (!API_BASE || !organizationId) { setMessage("Select an organisation and configure the API first."); return; }
    if (task === "explain_recommendation" && !recommendationId.trim()) { setMessage("A recorded recommendation ID is required."); return; }
    if (["extract_job_requirements", "draft_job_description", "interview_questions"].includes(task) && !jobId) { setMessage("Select a job for this task."); return; }
    if (task === "summarize_candidate" && !candidateId) { setMessage("Select a candidate."); return; }
    setBusy(true); setMessage(""); setResult(null); setFeedback("");
    try {
      const response = await apiFetch(API_BASE + "/api/ai/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId, task, job_id: jobId || null, candidate_id: candidateId || null,
          application_id: applicationId || null, interview_id: interviewId || null,
          recommendation_id: recommendationId || null, user_request: userRequest || null,
        }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "AI request failed (" + response.status + ").");
      setResult(body); setEditedText(body.output.text);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "AI request failed.");
    } finally { setBusy(false); }
  }

  async function saveDraft() {
    if (!result?.output.draft_record || !API_BASE) return;
    const path = task === "draft_job_description" ? "job-description-versions" : "interview-kits";
    setSavingDraft(true); setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/ai/" + path + "/" + result.output.draft_record.id, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, content: editedText }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Draft changes could not be saved.");
      setResult(current => current ? { ...current, output: { ...current.output, text: editedText } } : current);
      setMessage("Draft changes saved. The draft is still unpublished and requires review.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Draft changes could not be saved."); }
    finally { setSavingDraft(false); }
  }

  async function submitFeedback(value: "helpful" | "incorrect" | "unsafe") {
    if (!result || !API_BASE) return;
    try {
      const response = await apiFetch(API_BASE + "/api/ai/runs/" + result.run.id + "/feedback", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, feedback_status: value }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Feedback could not be saved.");
      setFeedback(value === "unsafe" ? "Reported for review." : "Feedback recorded.");
    } catch (error) { setFeedback(error instanceof Error ? error.message : "Feedback could not be saved."); }
  }

  async function loadGovernance() {
    if (!API_BASE || !organizationId) return;
    try {
      const response = await apiFetch(API_BASE + "/api/ai/governance?organization_id=" + encodeURIComponent(organizationId));
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Governance view requires organisation admin access.");
      setGovernance(body); setMessage("");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to load governance."); }
  }

  async function saveUseCase(event: FormEvent) {
    event.preventDefault();
    if (!API_BASE) return;
    const selected = useCases.find(item => item.key === useCaseKey)!;
    try {
      const response = await apiFetch(API_BASE + "/api/ai/governance/use-cases?organization_id=" + encodeURIComponent(organizationId), {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ use_case_key: useCaseKey, name: selected.name, purpose: selected.purpose,
          provider_approved: providerApproved, enabled, approval_status: approvalStatus, retention_days: 90,
          limitations: ["Administrative assistance only; outputs require human review.", "No automated candidate rejection or external message sending."] }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Use-case settings could not be saved.");
      setMessage("Use-case settings saved."); await loadGovernance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to save use case."); }
  }

  async function approveModel(modelId: string) {
    if (!API_BASE) return;
    try {
      const response = await apiFetch(API_BASE + "/api/ai/governance/models/" + modelId + "/approve?organization_id=" + encodeURIComponent(organizationId), {
        method: "POST",
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Model approval failed.");
      setMessage("Model approved after passing evaluation."); await loadGovernance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to approve model."); }
  }

  async function registerModel(event: FormEvent) {
    event.preventDefault();
    if (!API_BASE) return;
    try {
      const response = await apiFetch(API_BASE + "/api/ai/governance/models?organization_id=" + encodeURIComponent(organizationId), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, model_name: modelName, model_version: modelVersion,
          intended_purpose: "Administrative recruitment assistance; no autonomous hiring decisions.",
          data_processing_approved: dataProcessingApproved, status: modelStatus,
          limitations: ["Provider approval and data-processing review must be documented before enabling use."] }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Model could not be registered.");
      setMessage("Model version registered."); await loadGovernance();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to register model."); }
  }

  const needsJob = ["extract_job_requirements", "draft_job_description", "interview_questions"].includes(task);
  const needsCandidate = ["summarize_candidate", "draft_candidate_message"].includes(task);
  const needsApplication = task === "answer_authorized_records";
  const needsInterview = task === "answer_authorized_records";
  const needsRecommendation = task === "explain_recommendation";

  return <main className="content" style={{ maxWidth: 1180, margin: "0 auto" }}>
    <div className="header-row">
      <div><div className="eyebrow">Section 7 · Responsible automation</div><h1>AI workspace</h1>
        <p className="subtitle">Evidence-led assistance for recruiters. Drafts remain drafts, and a person remains responsible for decisions.</p></div>
      <div className="actions"><Link className="btn" href="/dashboard">Back to dashboard</Link>
        <button className="btn" type="button" onClick={() => { setShowGovernance(v => !v); if (!showGovernance) void loadGovernance(); }}>AI governance</button></div>
    </div>
    {message && <div className="notice" role="alert">{message}</div>}
    <div className="grid">
      <section className="card">
        <div className="card-head"><span className="card-title">Recruitment assistant</span><span className="badge blue">Human review</span></div>
        <form onSubmit={generate} style={{ display: "grid", gap: 14 }}>
          <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 650 }}>Task
            <select className="filter" value={task} onChange={event => { setTask(event.target.value); setResult(null); }}>
              <option value="summarize_candidate">Summarise candidate CV</option>
              <option value="extract_job_requirements">Extract stated job requirements</option>
              <option value="draft_candidate_message">Draft candidate communication</option>
              <option value="draft_job_description">Draft job description</option>
              <option value="interview_questions">Suggest interview questions</option>
              <option value="explain_recommendation">Explain a recorded recommendation</option>
              <option value="answer_authorized_records">Answer from authorised records</option>
            </select>
          </label>
          {needsCandidate && <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 650 }}>Candidate
            <select className="filter" value={candidateId} onChange={event => setCandidateId(event.target.value)}><option value="">Select a candidate</option>
              {candidates.map(candidate => <option key={candidate.id} value={candidate.id}>{[candidate.first_name, candidate.last_name].filter(Boolean).join(" ")}{candidate.current_title ? " · " + candidate.current_title : ""}</option>)}</select>
          </label>}
          {needsJob && <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 650 }}>Job
            <select className="filter" value={jobId} onChange={event => setJobId(event.target.value)}><option value="">Select a job</option>
              {jobs.map(job => <option key={job.id} value={job.id}>{job.title} · {job.status}</option>)}</select>
          </label>}
          {needsApplication && <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 650 }}>Application record ID
            <input className="filter" value={applicationId} onChange={event => setApplicationId(event.target.value)} placeholder="Application UUID" />
          </label>}
          {needsInterview && <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 650 }}>Interview record ID
            <input className="filter" value={interviewId} onChange={event => setInterviewId(event.target.value)} placeholder="Interview UUID (optional)" />
          </label>}
          {needsRecommendation && <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 650 }}>Recorded recommendation ID
            <input className="filter" value={recommendationId} onChange={event => setRecommendationId(event.target.value)} placeholder="Recommendation UUID" required />
          </label>}
          <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 650 }}>Additional instructions (optional)
            <textarea className="filter" rows={4} value={userRequest} onChange={event => setUserRequest(event.target.value)} maxLength={4000} placeholder="Tell the assistant what you need. Do not include unnecessary sensitive data." />
          </label>
          <p className="muted-small">Source documents are treated as untrusted content. The assistant cannot send messages, publish job descriptions or change recruitment decisions.</p>
          <button className="btn primary" type="submit" disabled={busy}>{busy ? "Working…" : "Generate draft"}</button>
        </form>
      </section>
      <section className="card">
        <div className="card-head"><span className="card-title">Result and evidence</span></div>
        {!result ? <p className="muted-small">Generated output and source references will appear here. AI remains unavailable until an organisation administrator approves a use case and model, and provider approval is configured on the server.</p> : <>
          <div className="notice">Draft only · Human review required · Run {result.run.id}</div>
          <label style={{ display: "grid", gap: 6, fontSize: 13, fontWeight: 650 }}>Editable draft / response<textarea className="filter" rows={12} value={editedText} onChange={event => setEditedText(event.target.value)} maxLength={20000} style={{ lineHeight: 1.6, fontWeight: 400, resize: "vertical" }} /></label>
          {result.output.draft_record && <p className="muted-small" style={{ marginTop: 12 }}>Saved draft version {result.output.draft_record.version_number} · {result.output.draft_record.status} · {result.output.draft_record.id}</p>}
          <div style={{ marginTop: 18 }}><strong style={{ fontSize: 13 }}>Source records</strong>
            {result.evidence_references.map(ref => <div key={ref.record_type + ref.id} className="activity-row" style={{ marginTop: 8 }}>
              <span className="dot" aria-hidden="true" /><div className="activity-text"><strong>{ref.record_type}</strong><div className="muted-small">{ref.id}{ref.fields?.length ? " · " + ref.fields.join(", ") : ""}</div></div>
            </div>)}
          </div>
          <p className="muted-small" style={{ marginTop: 14 }}>Model: {result.model.provider} / {result.model.name} ({result.model.version}); prompt {result.model.prompt_version}. Retention expiry: {new Date(result.run.retention_expires_at).toLocaleString()}.</p>
          {result.limitations.map((limitation, index) => <p className="muted-small" key={index}>{limitation}</p>)}
          <div className="actions" style={{ marginTop: 16, flexWrap: "wrap" }}>{result.output.draft_record && <button className="btn primary" type="button" disabled={savingDraft} onClick={() => void saveDraft()}>{savingDraft ? "Saving…" : "Save draft edits"}</button>}
            <button className="btn" type="button" onClick={() => void submitFeedback("helpful")}>Helpful</button>
            <button className="btn" type="button" onClick={() => void submitFeedback("incorrect")}>Incorrect</button>
            <button className="btn" type="button" onClick={() => void submitFeedback("unsafe")}>Report unsafe</button>
          </div>
          {feedback && <p className="muted-small" role="status">{feedback}</p>}
        </>}
      </section>
    </div>

    {showGovernance && <section className="card" style={{ marginTop: 18 }}>
      <div className="card-head"><span className="card-title">AI governance registry</span><button className="btn" type="button" onClick={() => void loadGovernance()}>Refresh</button></div>
      <p className="muted-small">Administrator-only. Registering approval is a governance attestation; it does not set the server's AI_PROVIDER_APPROVED environment gate.</p>
      <div className="grid" style={{ marginTop: 16 }}>
        <form onSubmit={saveUseCase} style={{ display: "grid", gap: 12 }}>
          <strong>Use-case approval</strong>
          <label style={{ display: "grid", gap: 6, fontSize: 13 }}>Use case<select className="filter" value={useCaseKey} onChange={e => setUseCaseKey(e.target.value as UseCaseKey)}>{useCases.map(item => <option key={item.key} value={item.key}>{item.name}</option>)}</select></label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}><input type="checkbox" checked={providerApproved} onChange={e => setProviderApproved(e.target.checked)} /> Provider/data processing approved</label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> Enable this use case</label>
          <label style={{ display: "grid", gap: 6, fontSize: 13 }}>Approval status<select className="filter" value={approvalStatus} onChange={e => setApprovalStatus(e.target.value)}><option value="pending">Pending</option><option value="suspended">Suspended</option><option value="retired">Retired</option></select></label>
          <button className="btn primary">Save use case</button>
        </form>
        <form onSubmit={registerModel} style={{ display: "grid", gap: 12 }}>
          <strong>Model version</strong>
          <label style={{ display: "grid", gap: 6, fontSize: 13 }}>Provider identifier<input className="filter" value={provider} onChange={e => setProvider(e.target.value)} required /></label>
          <label style={{ display: "grid", gap: 6, fontSize: 13 }}>Model name<input className="filter" value={modelName} onChange={e => setModelName(e.target.value)} required /></label>
          <label style={{ display: "grid", gap: 6, fontSize: 13 }}>Model version<input className="filter" value={modelVersion} onChange={e => setModelVersion(e.target.value)} required /></label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}><input type="checkbox" checked={dataProcessingApproved} onChange={e => setDataProcessingApproved(e.target.checked)} /> Data processing approved</label>
          <label style={{ display: "grid", gap: 6, fontSize: 13 }}>Registry status<select className="filter" value={modelStatus} onChange={e => setModelStatus(e.target.value)}><option value="draft">Draft</option><option value="evaluating">Evaluating</option><option value="approved">Approved</option><option value="disabled">Disabled</option><option value="retired">Retired</option></select></label>
          <button className="btn primary">Register model</button>
        </form>
      </div>
      {governance && <div style={{ marginTop: 20, display: "grid", gap: 16 }}>
        {(["use_cases", "evaluations", "incidents"] as const).map(key => <div key={key}><strong style={{ textTransform: "capitalize" }}>{key.replaceAll("_", " ")}</strong><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", background: "#f8fafc", padding: 12, borderRadius: 8, fontSize: 12 }}>{JSON.stringify(governance[key] ?? [], null, 2)}</pre></div>)}
        <div><strong>Model versions</strong>
          {Array.isArray(governance.models) && (governance.models as Array<Record<string, unknown>>).map(model => <div key={String(model.id)} className="card" style={{ marginTop: 8, padding: 12 }}>
            <div><strong>{String(model.provider)} / {String(model.model_name)} ({String(model.model_version)})</strong></div>
            <div className="muted-small">Status: {String(model.status)} · Data approval: {String(model.data_processing_approved)}</div>
            {model.status !== "approved" && model.data_processing_approved === true && <button className="btn" style={{ marginTop: 8 }} type="button" onClick={() => void approveModel(String(model.id))}>Approve after evaluation</button>}
          </div>)}
        </div>
      </div>}
    </section>}
  </main>;
}

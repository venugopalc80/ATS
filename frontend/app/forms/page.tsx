"use client";

import { FormEvent, useEffect, useState } from "react";
import "./forms.css";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

type Question = {
  id: string;
  question_key: string;
  label: string;
  help_text?: string | null;
  field_type: "text" | "textarea" | "email" | "phone" | "number" | "date" | "select" | "radio" | "checkbox" | "multi_select" | "boolean";
  required: boolean;
  options: string[];
  is_eligibility: boolean;
  position: number;
};
type FormVersion = { id: string; version_number: number; status: "draft" | "published" | "archived"; published_at?: string | null; questions?: Question[] };
type FormSummary = { id: string; name: string; description?: string | null; latest_version_id?: string | null; version_number?: number | null; status?: string | null };
type Job = { id: string; title: string; status: string };
type EditorQuestion = Omit<Question, "id"> & { id: string };

const blankQuestion = (): EditorQuestion => ({
  id: crypto.randomUUID(), question_key: "question_" + Math.random().toString(36).slice(2, 7),
  label: "", help_text: "", field_type: "text", required: false, options: [],
  is_eligibility: false, position: 0,
});

export default function ApplicationFormsPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [forms, setForms] = useState<FormSummary[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [name, setName] = useState("Standard job application");
  const [description, setDescription] = useState("");
  const [privacyNotice, setPrivacyNotice] = useState("The recruiting organisation will use the information you provide to assess your application and contact you about this role. The organisation should provide its legal identity, lawful basis, retention period and privacy contact before publishing this notice.");
  const [questions, setQuestions] = useState<EditorQuestion[]>([
    { ...blankQuestion(), question_key: "work_authorisation", label: "Are you legally authorised to work in the advertised location?", field_type: "boolean", required: true, is_eligibility: true },
    { ...blankQuestion(), question_key: "relevant_experience", label: "Briefly describe your relevant experience", field_type: "textarea", required: true },
  ]);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [jobId, setJobId] = useState("");
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setOrganizationId(getActiveOrganizationId());
  }, []);

  async function loadData(org = organizationId) {
    if (!org) return;
    const [formResponse, jobsResponse] = await Promise.all([
      apiFetch(`${API_BASE}/api/application-forms?organization_id=${encodeURIComponent(org)}`),
      apiFetch(`${API_BASE}/api/jobs?organization_id=${encodeURIComponent(org)}`),
    ]);
    if (formResponse.ok) setForms(await formResponse.json());
    if (jobsResponse.ok) setJobs(await jobsResponse.json());
  }

  useEffect(() => { if (organizationId) loadData(organizationId).catch(() => setError("Unable to load forms. Check your access and try again.")); }, [organizationId]);

  function patchQuestion(id: string, patch: Partial<EditorQuestion>) {
    setQuestions(current => current.map(question => question.id === id ? { ...question, ...patch } : question));
  }

  async function createForm(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await apiFetch(`${API_BASE}/api/application-forms`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId, name, description,
          privacy_notice_text: privacyNotice, privacy_notice_version: "1",
          questions: questions.map(({ id, ...question }, position) => ({ ...question, position, options: question.options })),
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "Could not create the form");
      setSelectedVersion(body.version.id);
      setMessage("Draft created. Preview it, then publish when it is ready.");
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the form");
    } finally { setBusy(false); }
  }

  async function publishAndAssign() {
    if (!selectedVersion) { setError("Create a draft first, then select its version."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      const publish = await apiFetch(`${API_BASE}/api/application-forms/versions/${selectedVersion}/publish`, { method: "POST" });
      const publishedBody = await publish.json().catch(() => ({}));
      if (!publish.ok && publishedBody.status !== "published") throw new Error(publishedBody.detail || "Could not publish this version");
      if (jobId) {
        const assign = await apiFetch(`${API_BASE}/api/application-forms/jobs/${encodeURIComponent(jobId)}/assignment`, {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ organization_id: organizationId, form_version_id: selectedVersion }),
        });
        const assignBody = await assign.json().catch(() => ({}));
        if (!assign.ok) throw new Error(assignBody.detail || "Published, but assignment failed. Assign it to a job before candidates can use it.");
      }
      setMessage(jobId ? "Form version published and assigned to the selected job." : "Form version published. Assign it to a job to make it available to candidates.");
      await loadData();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not publish form"); }
    finally { setBusy(false); }
  }

  return (
    <main className="content">
      <div className="header-row">
        <div><p className="eyebrow">Recruitment setup</p><h1>Application forms</h1><p className="subtitle">Build reusable question sets and preserve the exact version candidates answered.</p></div>
        <button className="btn" type="button" onClick={() => setPreview(value => !value)}>{preview ? "Back to editor" : "Preview candidate form"}</button>
      </div>
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      {message ? <p role="status" className="form-success">{message}</p> : null}
      <div className="form-builder-layout">
        <section className="card">
          <h2>{preview ? "Candidate preview" : "Form editor"}</h2>
          {preview ? (
            <div className="candidate-form-preview">
              <h3>{name || "Untitled application form"}</h3>
              <p>{description}</p>
              <div className="notice-preview"><strong>Applicant privacy notice</strong><p>{privacyNotice}</p></div>
              <label>First name <input disabled placeholder="Your first name" /></label>
              <label>Last name <input disabled placeholder="Your last name" /></label>
              <label>Email address <input disabled type="email" placeholder="you@example.com" /></label>
              <label>Phone (optional) <input disabled type="tel" placeholder="Phone number" /></label>
              {questions.map(q => <label key={q.id}>{q.label}{q.required ? " *" : ""}{q.help_text ? <small>{q.help_text}</small> : null}
                {q.field_type === "textarea" ? <textarea disabled rows={3} /> :
                  ["select", "radio"].includes(q.field_type) ? <select disabled defaultValue=""><option value="">Choose an answer</option>{q.options.map(o => <option key={o}>{o}</option>)}</select> :
                  q.field_type === "boolean" ? <select disabled defaultValue=""><option value="">Choose yes or no</option><option>Yes</option><option>No</option></select> :
                  q.field_type === "checkbox" ? <input disabled type="checkbox" /> : q.field_type === "multi_select" ? <div>{q.options.map(o => <span className="preview-option" key={o}>{o}</span>)}</div> :
                  <input disabled type={q.field_type === "number" ? "number" : q.field_type === "date" ? "date" : q.field_type === "email" ? "email" : "text"} />}
                {q.is_eligibility ? <small>Eligibility question</small> : null}
              </label>)}
              <p className="subtitle">Candidates will review their answers before submitting. Marketing permission, if offered, is optional.</p>
            </div>
          ) : (
            <form onSubmit={createForm} className="application-form-editor">
              <label>Form name<input value={name} onChange={e => setName(e.target.value)} maxLength={160} required /></label>
              <label>Description (optional)<textarea value={description} onChange={e => setDescription(e.target.value)} rows={2} maxLength={2000} /></label>
              <label>Applicant privacy notice<textarea value={privacyNotice} onChange={e => setPrivacyNotice(e.target.value)} rows={5} maxLength={12000} required /></label>
              <div className="form-questions-head"><div><h3>Questions</h3><p className="subtitle">Avoid unnecessary sensitive or discriminatory questions.</p></div><button className="btn" type="button" onClick={() => setQuestions(q => [...q, { ...blankQuestion(), position: q.length }])}>+ Add question</button></div>
              {questions.map((q, index) => <fieldset className="question-editor" key={q.id}>
                <legend>Question {index + 1}</legend>
                <label>Question text<input value={q.label} onChange={e => patchQuestion(q.id, { label: e.target.value })} required maxLength={500} /></label>
                <div className="question-grid">
                  <label>Question key<input value={q.question_key} pattern="[A-Za-z][A-Za-z0-9_]{0,79}" onChange={e => patchQuestion(q.id, { question_key: e.target.value })} required /></label>
                  <label>Answer type<select value={q.field_type} onChange={e => patchQuestion(q.id, { field_type: e.target.value as EditorQuestion["field_type"] })}>
                    {["text","textarea","email","phone","number","date","select","radio","checkbox","multi_select","boolean"].map(type => <option key={type} value={type}>{type.replace("_", " ")}</option>)}
                  </select></label>
                </div>
                {["select","radio","multi_select"].includes(q.field_type) ? <label>Options (one per line)<textarea rows={3} value={q.options.join("\n")} onChange={e => patchQuestion(q.id, { options: e.target.value.split("\n").map(v => v.trim()).filter(Boolean) })} required /></label> : null}
                <label>Help text (optional)<input value={q.help_text ?? ""} onChange={e => patchQuestion(q.id, { help_text: e.target.value })} maxLength={2000} /></label>
                <div className="question-flags"><label><input type="checkbox" checked={q.required} onChange={e => patchQuestion(q.id, { required: e.target.checked })} /> Required</label><label><input type="checkbox" checked={q.is_eligibility} onChange={e => patchQuestion(q.id, { is_eligibility: e.target.checked })} /> Job-related eligibility question</label><button className="btn" type="button" onClick={() => setQuestions(current => current.filter(item => item.id !== q.id))}>Remove</button></div>
              </fieldset>)}
              <button className="btn primary" type="submit" disabled={busy || !organizationId}>{busy ? "Saving…" : "Create draft version"}</button>
            </form>
          )}
        </section>
        <aside className="card">
          <h2>Publish & assign</h2>
          <p className="subtitle">Publishing freezes a version. Make a new version to change questions later.</p>
          <label>Draft version ID<input value={selectedVersion} onChange={e => setSelectedVersion(e.target.value)} placeholder="Created version ID" /></label>
          <label>Assign to vacancy (optional)<select value={jobId} onChange={e => setJobId(e.target.value)}><option value="">Choose a job</option>{jobs.map(job => <option key={job.id} value={job.id}>{job.title} · {job.status}</option>)}</select></label>
          <button className="btn primary" type="button" onClick={publishAndAssign} disabled={busy || !selectedVersion}>{busy ? "Working…" : "Publish version"}</button>
          <h3>Existing forms</h3>
          {forms.length ? forms.map(form => <div className="existing-form" key={form.id}><strong>{form.name}</strong><p>{form.description || "Reusable application form"}</p><small>Version {form.version_number ?? "—"} · {form.status ?? "no version"}</small>{form.latest_version_id ? <button className="btn" type="button" onClick={() => { setSelectedVersion(form.latest_version_id ?? ""); setName(form.name); setDescription(form.description ?? ""); }}>Use latest version ID</button> : null}</div>) : <p className="subtitle">No forms created yet.</p>}
        </aside>
      </div>
    </main>
  );
}

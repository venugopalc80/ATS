"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Job = { id: string; title: string; required_skills?: string[] };
type Application = { id: string; job_id: string; candidate_id: string; status: string };
type Candidate = { id: string; first_name: string; last_name?: string | null };
type Template = {
  id: string; job_id?: string | null; name: string; assessment_type: string;
  instructions: string; role_requirements: string[]; status: string; provider_key?: string | null;
};
type Assignment = {
  id: string; application_id: string; template_id: string; status: string;
  due_at?: string | null; extended_due_at?: string | null; accommodation_requested: boolean;
  assigned_at: string; submitted_at?: string | null;
};
type Evidence = { assignment: Assignment; submissions: Array<Record<string, unknown>>; results: Array<Record<string, unknown>>; reviews: Array<Record<string, unknown>> };

const typeLabels: Record<string, string> = {
  work_sample: "Work sample", technical_exercise: "Technical exercise",
  written_task: "Written task", external_test: "External provider test",
};
const statuses = ["assigned", "in_progress", "submitted", "under_review", "completed", "cancelled", "expired", "provider_error"];

export default function AssessmentsPage() {
  const organizationId = getActiveOrganizationId(DEFAULT_ORG);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [showTemplate, setShowTemplate] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [name, setName] = useState("");
  const [jobId, setJobId] = useState("");
  const [assessmentType, setAssessmentType] = useState("work_sample");
  const [instructions, setInstructions] = useState("");
  const [requirements, setRequirements] = useState("");
  const [guidance, setGuidance] = useState("");
  const [providerKey, setProviderKey] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [selectedApplication, setSelectedApplication] = useState("");
  const [deadline, setDeadline] = useState("");
  const [activeEvidence, setActiveEvidence] = useState<Evidence | null>(null);
  const [reviewFeedback, setReviewFeedback] = useState("");
  const [recommendation, setRecommendation] = useState("review");

  const jobMap = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);
  const candidateMap = useMemo(() => new Map(candidates.map((candidate) => [candidate.id, candidate])), [candidates]);
  const applicationMap = useMemo(() => new Map(applications.map((app) => [app.id, app])), [applications]);
  const templateMap = useMemo(() => new Map(templates.map((template) => [template.id, template])), [templates]);

  async function load() {
    setLoading(true);
    try {
      const q = encodeURIComponent(organizationId);
      const [tr, ar, jr, appr, cr] = await Promise.all([
        apiFetch(API_BASE + "/api/assessments/templates?organization_id=" + q),
        apiFetch(API_BASE + "/api/assessments/assignments?organization_id=" + q),
        apiFetch(API_BASE + "/api/jobs?organization_id=" + q),
        apiFetch(API_BASE + "/api/applications?organization_id=" + q),
        apiFetch(API_BASE + "/api/candidates?organization_id=" + q),
      ]);
      if (!tr.ok || !ar.ok || !jr.ok || !appr.ok || !cr.ok) throw new Error("Unable to load the assessment workspace.");
      setTemplates(await tr.json()); setAssignments(await ar.json()); setJobs(await jr.json());
      setApplications(await appr.json()); setCandidates(await cr.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load assessments.");
    } finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);

  async function createTemplate(event: FormEvent) {
    event.preventDefault(); setSaving(true); setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/assessments/templates", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: organizationId, job_id: jobId || null, name, assessment_type: assessmentType,
          instructions, evaluation_guidance: guidance || null,
          role_requirements: requirements.split(",").map((item) => item.trim()).filter(Boolean),
          provider_key: assessmentType === "external_test" ? providerKey.trim() : null,
          accessibility_options: { alternative_format_available: true, extension_available: true },
        }),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to create assessment template.");
      setMessage("Draft template created. Publish it after confirming the role requirements.");
      setName(""); setInstructions(""); setGuidance(""); setRequirements(""); setJobId(""); setProviderKey(""); setShowTemplate(false);
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to create template."); }
    finally { setSaving(false); }
  }

  async function publish(template: Template) {
    setSaving(true); setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/assessments/templates/" + template.id + "/publish?organization_id=" + encodeURIComponent(organizationId), { method: "POST" });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to publish template.");
      setMessage("Assessment template published."); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to publish template."); }
    finally { setSaving(false); }
  }

  async function assign(event: FormEvent) {
    event.preventDefault(); setSaving(true); setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/assessments/assignments", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, application_id: selectedApplication,
          template_id: selectedTemplate, due_at: deadline ? new Date(deadline).toISOString() : null,
          idempotency_key: crypto.randomUUID() }),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to assign assessment.");
      setMessage("Assessment assigned and recorded."); setShowAssign(false); setDeadline(""); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to assign assessment."); }
    finally { setSaving(false); }
  }

  async function viewEvidence(assignment: Assignment) {
    setMessage(""); setActiveEvidence(null);
    try {
      const response = await apiFetch(API_BASE + "/api/assessments/assignments/" + assignment.id + "/evidence?organization_id=" + encodeURIComponent(organizationId));
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to load evidence.");
      setActiveEvidence(result);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to load evidence."); }
  }

  async function submitReview(event: FormEvent) {
    event.preventDefault(); if (!activeEvidence) return;
    setSaving(true); setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/assessments/assignments/" + activeEvidence.assignment.id + "/reviews?organization_id=" + encodeURIComponent(organizationId), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback: reviewFeedback, recommendation }),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to save review.");
      setMessage("Human review recorded. The application stage was not changed."); setReviewFeedback(""); setActiveEvidence(null); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to save review."); }
    finally { setSaving(false); }
  }

  function applicationLabel(applicationId: string) {
    const app = applicationMap.get(applicationId);
    const candidate = app ? candidateMap.get(app.candidate_id) : undefined;
    const candidateName = candidate ? [candidate.first_name, candidate.last_name].filter(Boolean).join(" ") : "Candidate";
    return app ? candidateName + " · " + (jobMap.get(app.job_id)?.title ?? "Job") : applicationId;
  }

  const eligibleApplications = applications.filter((app) => !["rejected", "withdrawn", "hired"].includes(app.status));

  return <main className="mx-auto max-w-7xl p-6 md:p-8">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-sm font-medium uppercase tracking-wider text-violet-600">Hiring workflow</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Candidate assessments</h1>
        <p className="mt-2 max-w-2xl text-sm text-gray-500">Assign role-relevant work, track deadlines and review evidence. Results inform recruiters; they do not automatically change application decisions.</p></div>
      <div className="flex gap-2"><button className="btn secondary" onClick={() => setShowTemplate(!showTemplate)}>Create template</button>
        <button className="btn primary" onClick={() => setShowAssign(!showAssign)}>Assign assessment</button></div>
    </div>
    {message && <div role="status" className="notice mt-5">{message}</div>}

    {showTemplate && <form onSubmit={createTemplate} className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold">New assessment template</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <label className="block text-sm">Template name<input required maxLength={160} className="mt-1 w-full rounded-lg border p-2.5" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="block text-sm">Assessment type<select className="mt-1 w-full rounded-lg border p-2.5" value={assessmentType} onChange={(e) => setAssessmentType(e.target.value)}>{Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="block text-sm">Role (optional)<select className="mt-1 w-full rounded-lg border p-2.5" value={jobId} onChange={(e) => setJobId(e.target.value)}><option value="">Reusable across roles</option>{jobs.map((job) => <option key={job.id} value={job.id}>{job.title}</option>)}</select></label>
        {assessmentType === "external_test" && <label className="block text-sm">Provider key<input required className="mt-1 w-full rounded-lg border p-2.5" value={providerKey} onChange={(e) => setProviderKey(e.target.value)} placeholder="provider identifier" /></label>}
        <label className="block text-sm md:col-span-2">Role requirements (comma-separated)<input required className="mt-1 w-full rounded-lg border p-2.5" value={requirements} onChange={(e) => setRequirements(e.target.value)} placeholder="e.g. Python, API design, testing" /></label>
        <label className="block text-sm md:col-span-2">Candidate instructions<textarea required rows={4} maxLength={8000} className="mt-1 w-full rounded-lg border p-2.5" value={instructions} onChange={(e) => setInstructions(e.target.value)} /></label>
        <label className="block text-sm md:col-span-2">Evaluation guidance<textarea rows={3} maxLength={8000} className="mt-1 w-full rounded-lg border p-2.5" value={guidance} onChange={(e) => setGuidance(e.target.value)} placeholder="Describe the evidence evaluators should look for." /></label>
      </div>
      <p className="mt-3 text-xs text-gray-500">Keep criteria tied to the job. Do not use covert monitoring, emotion inference or unrelated speed/equipment requirements.</p>
      <div className="mt-4 flex justify-end gap-2"><button type="button" className="btn secondary" onClick={() => setShowTemplate(false)}>Cancel</button><button disabled={saving} className="btn primary">{saving ? "Saving…" : "Save draft"}</button></div>
    </form>}

    {showAssign && <form onSubmit={assign} className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold">Assign assessment</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <label className="block text-sm md:col-span-1">Candidate / vacancy<select required className="mt-1 w-full rounded-lg border p-2.5" value={selectedApplication} onChange={(e) => setSelectedApplication(e.target.value)}><option value="">Select application</option>{eligibleApplications.map((app) => <option key={app.id} value={app.id}>{applicationLabel(app.id)}</option>)}</select></label>
        <label className="block text-sm md:col-span-1">Published template<select required className="mt-1 w-full rounded-lg border p-2.5" value={selectedTemplate} onChange={(e) => setSelectedTemplate(e.target.value)}><option value="">Select template</option>{templates.filter((t) => t.status === "published").map((t) => <option key={t.id} value={t.id}>{t.name}{t.job_id ? " · " + (jobMap.get(t.job_id)?.title ?? "Role-specific") : ""}</option>)}</select></label>
        <label className="block text-sm">Deadline (optional)<input type="datetime-local" className="mt-1 w-full rounded-lg border p-2.5" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></label>
      </div>
      <div className="mt-4 flex justify-end gap-2"><button type="button" className="btn secondary" onClick={() => setShowAssign(false)}>Cancel</button><button disabled={saving || !templates.some((t) => t.id === selectedTemplate && t.status === "published")} className="btn primary">{saving ? "Assigning…" : "Assign assessment"}</button></div>
    </form>}

    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between"><h2 className="text-xl font-semibold">Assessment templates</h2><span className="text-sm text-gray-500">{templates.length} total</span></div>
      <div className="overflow-hidden rounded-xl border bg-white">
        {loading ? <p className="p-6 text-sm text-gray-500">Loading assessments…</p> : templates.length === 0 ? <p className="p-6 text-sm text-gray-500">No templates yet. Create one with explicit role requirements.</p> :
          <div className="divide-y">{templates.map((template) => <div key={template.id} className="flex flex-wrap items-center justify-between gap-4 p-4">
            <div><div className="font-medium">{template.name}</div><div className="mt-1 text-sm text-gray-500">{typeLabels[template.assessment_type] ?? template.assessment_type} · {template.role_requirements.join(", ") || "No role requirements"} · {template.job_id ? jobMap.get(template.job_id)?.title ?? "Role-specific" : "Reusable"}</div></div>
            <div className="flex items-center gap-3"><span className="rounded-full bg-gray-100 px-3 py-1 text-xs capitalize">{template.status}</span>{template.status === "draft" && <button disabled={saving} className="btn secondary" onClick={() => void publish(template)}>Publish</button>}</div>
          </div>)}</div>}
      </div>
    </section>

    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between"><h2 className="text-xl font-semibold">Assignments</h2><span className="text-sm text-gray-500">{assignments.length} total</span></div>
      <div className="overflow-x-auto rounded-xl border bg-white">
        {loading ? <p className="p-6 text-sm text-gray-500">Loading assignments…</p> : assignments.length === 0 ? <p className="p-6 text-sm text-gray-500">Assignments will appear here once a published assessment is assigned.</p> :
          <table className="w-full text-left text-sm"><thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500"><tr><th className="px-4 py-3">Candidate / vacancy</th><th className="px-4 py-3">Assessment</th><th className="px-4 py-3">Deadline</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Evidence</th></tr></thead>
            <tbody className="divide-y">{assignments.map((assignment) => <tr key={assignment.id}>
              <td className="px-4 py-3 font-medium">{applicationLabel(assignment.application_id)}</td>
              <td className="px-4 py-3">{templateMap.get(assignment.template_id)?.name ?? "Assessment"}</td>
              <td className="px-4 py-3">{(assignment.extended_due_at ?? assignment.due_at) ? new Date(assignment.extended_due_at ?? assignment.due_at!).toLocaleString() : "No deadline"}</td>
              <td className="px-4 py-3"><span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs capitalize">{assignment.status.replace("_", " ")}</span>{assignment.accommodation_requested && <span className="ml-2 text-xs text-violet-700">Accommodation</span>}</td>
              <td className="px-4 py-3"><button className="font-medium text-violet-700 hover:underline" onClick={() => void viewEvidence(assignment)}>Review evidence</button></td>
            </tr>)}</tbody></table>}
      </div>
    </section>

    {activeEvidence && <section className="mt-8 rounded-xl border bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-wide text-violet-600">Evidence review</p><h2 className="mt-1 text-xl font-semibold">{templateMap.get(activeEvidence.assignment.template_id)?.name ?? "Assessment"}</h2><p className="mt-1 text-sm text-gray-500">{applicationLabel(activeEvidence.assignment.application_id)} · {activeEvidence.assignment.status}</p></div><button className="btn secondary" onClick={() => setActiveEvidence(null)}>Close</button></div>
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div><h3 className="font-semibold">Submissions ({activeEvidence.submissions.length})</h3>{activeEvidence.submissions.length === 0 ? <p className="mt-2 text-sm text-gray-500">No submission evidence recorded.</p> : activeEvidence.submissions.map((item, index) => <article key={String(item.id ?? index)} className="mt-2 rounded-lg bg-gray-50 p-3"><p className="text-xs text-gray-500">{String(item.submission_type)} · {item.submitted_at ? new Date(String(item.submitted_at)).toLocaleString() : ""}</p><p className="mt-2 whitespace-pre-wrap text-sm">{String(item.text_content ?? item.provider_submission_ref ?? "Evidence is held by the external provider.")}</p></article>)}</div>
        <div><h3 className="font-semibold">Results ({activeEvidence.results.length})</h3>{activeEvidence.results.length === 0 ? <p className="mt-2 text-sm text-gray-500">No result recorded yet.</p> : activeEvidence.results.map((item, index) => <article key={String(item.id ?? index)} className="mt-2 rounded-lg bg-gray-50 p-3"><p className="font-medium">{item.score != null ? String(item.score) + (item.max_score != null ? " / " + String(item.max_score) : "") : "No numeric score"} <span className="text-xs font-normal text-gray-500">· {String(item.source)} · {String(item.methodology)}</span></p><p className="mt-1 text-sm">{String(item.summary ?? "No summary supplied.")}</p><p className="mt-2 text-xs text-gray-500">Evidence and methodology should be reviewed before making a hiring decision.</p></article>)}</div>
      </div>
      {["submitted", "under_review"].includes(activeEvidence.assignment.status) && <form onSubmit={submitReview} className="mt-6 border-t pt-5"><h3 className="font-semibold">Record human review</h3><div className="mt-3 grid gap-4 md:grid-cols-3"><label className="text-sm md:col-span-2">Evidence-based feedback<textarea required minLength={1} maxLength={8000} rows={3} className="mt-1 w-full rounded-lg border p-2.5" value={reviewFeedback} onChange={(e) => setReviewFeedback(e.target.value)} /></label><label className="text-sm">Recommendation<select className="mt-1 w-full rounded-lg border p-2.5" value={recommendation} onChange={(e) => setRecommendation(e.target.value)}><option value="advance">Advance</option><option value="review">Further review</option><option value="not_recommended">Not recommended</option><option value="no_recommendation">No recommendation</option></select></label></div><div className="mt-3 flex justify-end"><button disabled={saving} className="btn primary">{saving ? "Saving…" : "Save human review"}</button></div></form>}
      {activeEvidence.reviews.length > 0 && <div className="mt-5 border-t pt-4"><h3 className="font-semibold">Previous reviews</h3>{activeEvidence.reviews.map((item, index) => <p key={String(item.id ?? index)} className="mt-2 text-sm">{String(item.feedback)} <span className="text-gray-500">({String(item.recommendation)})</span></p>)}</div>}
    </section>}
    <p className="mt-6 text-xs text-gray-500">Assessment workspace is organisation-scoped. Provider results are labelled separately, deadlines are auditable, and human review does not automatically advance or reject an application.</p>
  </main>;
}

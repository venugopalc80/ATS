"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Job = { id: string; title: string };
type Kit = {
  id: string;
  job_id?: string | null;
  name: string;
  description?: string | null;
  status: string;
  current_version_id?: string | null;
  draft_template_id?: string | null;
  version_number?: number | null;
};

type Competency = { key: string; name: string; description: string; question: string; guidance: string };
const emptyCompetency = (): Competency => ({
  key: "competency_1", name: "", description: "", question: "", guidance: "",
});

export default function InterviewKitsPage() {
  const [kits, setKits] = useState<Kit[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [editingKitId, setEditingKitId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [competencies, setCompetencies] = useState<Competency[]>([emptyCompetency()]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const organizationId = getActiveOrganizationId(DEFAULT_ORG);

  async function load() {
    setLoading(true);
    try {
      const [response, jobsResponse] = await Promise.all([
        apiFetch(API_BASE + "/api/interview-kits?organization_id=" + encodeURIComponent(organizationId)),
        apiFetch(API_BASE + "/api/jobs?organization_id=" + encodeURIComponent(organizationId)),
      ]);
      if (!response.ok) throw new Error("Unable to load interview kits.");
      setKits(await response.json());
      if (jobsResponse.ok) setJobs(await jobsResponse.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load interview kits.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  function updateCompetency(index: number, field: keyof Competency, value: string) {
    setCompetencies((current) => current.map((item, i) => i === index ? { ...item, [field]: value } : item));
  }

  async function createKit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const target = editingKitId
        ? API_BASE + "/api/interview-kits/" + editingKitId + "/versions?organization_id=" + encodeURIComponent(organizationId)
        : API_BASE + "/api/interview-kits";
      const response = await apiFetch(target, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify((() => {
          const definition = {
            name, description: description || null, instructions: instructions || null,
            competencies: competencies.map((item, index) => ({
            key: item.key.trim() || ("competency_" + (index + 1)),
            name: item.name, description: item.description,
            rating_guidance: {
              "1": "No relevant evidence demonstrated",
              "2": "Limited evidence; substantial support required",
              "3": "Meets the role requirement with relevant evidence",
              "4": "Strong evidence beyond the expected level",
              "5": "Exceptional, specific evidence at this level",
            },
              questions: item.question.trim() ? [{
                question: item.question, evaluation_guidance: item.guidance || null,
              }] : [],
            })),
          };
          return editingKitId ? definition : { organization_id: organizationId, job_id: jobId || null, ...definition };
        })()),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to create interview kit.");
      setMessage(editingKitId ? "New draft version created. Review it, then publish when ready." : "Draft kit created. Review the criteria, then publish the version when it is ready.");
      setEditingKitId(null); setName(""); setDescription(""); setInstructions(""); setJobId(""); setCompetencies([emptyCompetency()]);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create interview kit.");
    } finally {
      setSaving(false);
    }
  }

  async function publish(kit: Kit) {
    if (!kit.draft_template_id) {
      setMessage("No draft version is available to publish. Create a new version first.");
      return;
    }
    setSaving(true); setMessage("");
    try {
      const query = new URLSearchParams({ organization_id: organizationId, template_id: kit.draft_template_id });
      const response = await apiFetch(API_BASE + "/api/interview-kits/" + kit.id + "/publish?" + query, { method: "POST" });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail ?? "Unable to publish this version.");
      setMessage("Published " + kit.name + " version " + result.version_number + ". Published versions cannot be edited.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to publish this version.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="p-8 mx-auto max-w-6xl">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold">Interview kits &amp; scorecards</h1>
          <p className="mt-2 text-sm text-gray-500">Build role-relevant questions and anchored rating guidance. Published versions remain fixed for historical assessments.</p>
        </div>
        <a className="btn" href="/interviews">Back to interviews</a>
      </div>
      {message && <div className="notice mt-5" role="status">{message}</div>}

      <section className="card mt-8">
        <h2 className="text-xl font-semibold">Create a kit</h2>
        <p className="mt-1 text-sm text-gray-500">Use observable, job-related competencies. Avoid vague criteria such as cultural similarity or personality fit.</p>
        <form className="mt-5 space-y-5" onSubmit={createKit}>
          <div className="grid gap-4 md:grid-cols-2">
            {!editingKitId && <label className="block text-sm">Apply to vacancy (optional)
              <select className="input mt-1 w-full" value={jobId} onChange={(e) => setJobId(e.target.value)}><option value="">All vacancies</option>{jobs.map((job) => <option key={job.id} value={job.id}>{job.title}</option>)}</select>
            </label>}
            <label className="block text-sm">Kit name
              <input className="input mt-1 w-full" required minLength={1} maxLength={160} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Senior Python Engineer" />
            </label>
            <label className="block text-sm">Description
              <input className="input mt-1 w-full" maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Role and interview stage" />
            </label>
          </div>
          <label className="block text-sm">Interviewer guidance
            <textarea className="input mt-1 w-full" rows={2} maxLength={4000} value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Assess evidence against the stated role requirements." />
          </label>
          <div className="space-y-4">
            {competencies.map((item, index) => (
              <div className="rounded-xl border p-4" key={index}>
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-medium">Competency {index + 1}</h3>
                  {competencies.length > 1 && <button type="button" className="text-sm underline" onClick={() => setCompetencies((current) => current.filter((_, i) => i !== index))}>Remove</button>}
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <label className="block text-sm">Competency name
                    <input className="input mt-1 w-full" required value={item.name} onChange={(e) => updateCompetency(index, "name", e.target.value)} placeholder="e.g. Debugging and problem solving" />
                  </label>
                  <label className="block text-sm">Stable key
                    <input className="input mt-1 w-full" required pattern="[A-Za-z0-9_-]+" value={item.key} onChange={(e) => updateCompetency(index, "key", e.target.value)} />
                  </label>
                  <label className="block text-sm md:col-span-2">What good evidence looks like
                    <textarea className="input mt-1 w-full" required rows={2} value={item.description} onChange={(e) => updateCompetency(index, "description", e.target.value)} placeholder="Describe observable, role-related behaviour or outcomes." />
                  </label>
                  <label className="block text-sm md:col-span-2">Interview question
                    <textarea className="input mt-1 w-full" rows={2} value={item.question} onChange={(e) => updateCompetency(index, "question", e.target.value)} placeholder="Ask for a specific example or work-related demonstration." />
                  </label>
                  <label className="block text-sm md:col-span-2">Question evaluation guidance
                    <input className="input mt-1 w-full" value={item.guidance} onChange={(e) => updateCompetency(index, "guidance", e.target.value)} placeholder="What evidence should the interviewer look for?" />
                  </label>
                </div>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-3">
            {editingKitId && <button type="button" className="btn" onClick={() => { setEditingKitId(null); setName(""); setDescription(""); setInstructions(""); setCompetencies([emptyCompetency()]); }}>Cancel version</button>}
            <button type="button" className="btn" disabled={competencies.length >= 30} onClick={() => setCompetencies((current) => [...current, { ...emptyCompetency(), key: "competency_" + (current.length + 1) }])}>+ Add competency</button>
            <button type="submit" className="btn primary" disabled={saving}>{saving ? "Saving…" : editingKitId ? "Save new version" : "Save draft kit"}</button>
          </div>
        </form>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">Your organisation&apos;s kits</h2>
        {loading ? <p className="mt-4 text-sm text-gray-500">Loading kits…</p> : kits.length === 0 ? <p className="mt-4 text-sm text-gray-500">No interview kits yet.</p> : (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {kits.map((kit) => (
              <article className="card" key={kit.id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold">{kit.name}</h3>
                    <p className="mt-1 text-sm text-gray-500">{kit.description || "No description provided."}</p>
                    <p className="mt-2 text-xs uppercase tracking-wide">{kit.status}{kit.version_number ? " · version " + kit.version_number : " · draft"}</p><p className="mt-1 text-xs text-gray-500">{kit.job_id ? "Vacancy-specific kit" : "Available across vacancies"}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">{kit.draft_template_id && <button className="btn primary" disabled={saving} onClick={() => void publish(kit)}>Publish draft</button>}{kit.status === "published" && !kit.draft_template_id && <button className="btn" disabled={saving} onClick={() => { setEditingKitId(kit.id); setName(kit.name); setDescription(kit.description ?? ""); setInstructions(""); setCompetencies([emptyCompetency()]); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Create new version</button>}</div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

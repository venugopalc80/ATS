'use client';

import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Job = {
  id?: string;
  organization_id?: string;
  title: string;
  client?: string;
  client_id?: string | null;
  location?: string | null;
  status: "draft" | "open" | "on_hold" | "closed" | "filled" | "cancelled";
  employment_type?: string | null;
  work_mode?: string | null;
  required_skills?: string[];
  description?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string | null;
};

type DistributionChannelId = "careers" | "google" | "linkedin" | "indeed" | "monster" | "other";
type DistributionStatus = "not_selected" | "ready" | "needs_public_page" | "integration_required";

type DistributionChannel = {
  id: DistributionChannelId;
  name: string;
  description: string;
  kind: "native" | "discovery" | "partner";
};

const distributionChannels: DistributionChannel[] = [
  { id: "careers", name: "TalentOS Careers", description: "Your public careers page", kind: "native" },
  { id: "google", name: "Google for Jobs", description: "Search discovery via JobPosting structured data", kind: "discovery" },
  { id: "linkedin", name: "LinkedIn", description: "Requires approved partner integration", kind: "partner" },
  { id: "indeed", name: "Indeed", description: "Requires approved ATS / Job Sync access", kind: "partner" },
  { id: "monster", name: "Monster", description: "Requires an approved integration or feed", kind: "partner" },
  { id: "other", name: "Other job boards", description: "Configure supported partners or job feeds", kind: "partner" },
];

type JobDistribution = Record<DistributionChannelId, { selected: boolean; status: DistributionStatus }>;
const initialDistribution = (): JobDistribution => ({
  careers: { selected: true, status: "ready" },
  google: { selected: true, status: "needs_public_page" },
  linkedin: { selected: false, status: "integration_required" },
  indeed: { selected: false, status: "integration_required" },
  monster: { selected: false, status: "integration_required" },
  other: { selected: false, status: "integration_required" },
});

function distributionStatusLabel(channel: DistributionChannel, entry: JobDistribution[DistributionChannelId]) {
  if (!entry.selected) return "Not selected";
  if (entry.status === "ready") return "Ready for careers page";
  if (entry.status === "needs_public_page") return "Public page / indexing required";
  return "Integration required";
}

type JobForm = {
  title: string;
  client: string;
  location: string;
  employment_type: string;
  work_mode: string;
  skills: string;
  status: Job["status"];
  description: string;
  salary_min: string;
  salary_max: string;
  salary_currency: string;
};

const emptyForm: JobForm = {
  title: "",
  client: "",
  location: "",
  employment_type: "Permanent",
  work_mode: "Hybrid",
  skills: "",
  status: "draft",
  description: "",
  salary_min: "",
  salary_max: "",
  salary_currency: "GBP",
};

const seedJobs: Job[] = [
  { id: "demo-1", title: "Senior Python Engineer", client: "Northstar Digital", location: "London, UK", status: "open", employment_type: "Permanent", required_skills: ["Python", "FastAPI", "PostgreSQL"] },
  { id: "demo-2", title: "Data Analyst", client: "Brightline Group", location: "Manchester, UK", status: "open", employment_type: "Permanent", required_skills: ["SQL", "Tableau", "Python"] },
  { id: "demo-3", title: "Full Stack Developer", client: "Vertex Systems", location: "Remote, UK", status: "open", employment_type: "Contract", required_skills: ["TypeScript", "React", "Node.js"] },
];

function formFromJob(job: Job): JobForm {
  return {
    title: job.title,
    client: job.client ?? "",
    location: job.location ?? "",
    employment_type: job.employment_type ?? "Permanent",
    work_mode: job.work_mode ?? "Hybrid",
    skills: (job.required_skills ?? []).join(", "),
    status: job.status,
    description: job.description ?? "",
    salary_min: job.salary_min?.toString() ?? "",
    salary_max: job.salary_max?.toString() ?? "",
    salary_currency: job.salary_currency ?? "GBP",
  };
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>(API_BASE ? [] : seedJobs);
  const [loading, setLoading] = useState(Boolean(API_BASE));
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [showForm, setShowForm] = useState(false);
  const [editingJob, setEditingJob] = useState<Job | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState<JobForm>(emptyForm);
  const [distributionJob, setDistributionJob] = useState<Job | null>(null);
  const [distributionByJob, setDistributionByJob] = useState<Record<string, JobDistribution>>({});
  const [distributionDraft, setDistributionDraft] = useState<JobDistribution>(initialDistribution);
  const [distributionStorageLoaded, setDistributionStorageLoaded] = useState(false);
  const [distributionLoading, setDistributionLoading] = useState(false);
  const [distributionSaving, setDistributionSaving] = useState(false);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("talentos_job_distribution_v1");
      if (saved) {
        const parsed = JSON.parse(saved) as Record<string, JobDistribution>;
        if (parsed && typeof parsed === "object") setDistributionByJob(parsed);
      }
    } catch {
      // Keep the in-memory prototype usable if browser storage is unavailable.
    } finally {
      setDistributionStorageLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!distributionStorageLoaded) return;
    try {
      window.localStorage.setItem("talentos_job_distribution_v1", JSON.stringify(distributionByJob));
    } catch {
      // Storage can be disabled or full; keep this session functional.
    }
  }, [distributionByJob, distributionStorageLoaded]);

  useEffect(() => {
    if (!API_BASE || !ORGANIZATION_ID) return;
    let cancelled = false;

    async function loadJobs() {
      try {
        const response = await apiFetch(API_BASE + "/api/jobs?organization_id=" + encodeURIComponent(ORGANIZATION_ID));
        if (!response.ok) throw new Error("API returned " + response.status);
        const data: Job[] = await response.json();
        if (!cancelled) setJobs(data);
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "Unable to load requisitions.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadJobs();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => jobs.filter((job) => {
    const matchesQuery = (job.title + " " + (job.client ?? "") + " " + (job.location ?? "")).toLowerCase().includes(query.toLowerCase());
    const matchesStatus = status === "all" || job.status === status;
    return matchesQuery && matchesStatus;
  }), [jobs, query, status]);

  async function openDistribution(job: Job) {
    const key = job.id ?? job.title;
    setDistributionJob(job);
    setDistributionDraft(distributionByJob[key] ?? initialDistribution());
    setMessage("");

    const organizationId = job.organization_id || (typeof window !== "undefined" ? window.localStorage.getItem("talentos_active_org") : null) || ORGANIZATION_ID;
    const isPersistedJob = Boolean(job.id && !job.id.startsWith("demo-") && !job.id.startsWith("local-"));
    if (!API_BASE || !organizationId || !isPersistedJob) return;

    setDistributionLoading(true);
    try {
      const response = await apiFetch(`${API_BASE}/api/jobs/${job.id}/distribution?organization_id=${encodeURIComponent(organizationId)}`);
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `Unable to load distribution settings (${response.status})`);
      const saved: Array<{ channel_id: DistributionChannelId; selected: boolean; status: DistributionStatus }> = await response.json();
      if (saved.length) {
        const next = initialDistribution();
        for (const item of saved) next[item.channel_id] = { selected: item.selected, status: item.status };
        setDistributionDraft(next);
        setDistributionByJob((current) => ({ ...current, [key]: next }));
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load distribution settings.");
    } finally {
      setDistributionLoading(false);
    }
  }

  async function saveDistribution() {
    if (!distributionJob) return;
    const key = distributionJob.id ?? distributionJob.title;
    const organizationId = distributionJob.organization_id || (typeof window !== "undefined" ? window.localStorage.getItem("talentos_active_org") : null) || ORGANIZATION_ID;
    const isPersistedJob = Boolean(distributionJob.id && !distributionJob.id.startsWith("demo-") && !distributionJob.id.startsWith("local-"));

    if (API_BASE && organizationId && isPersistedJob) {
      setDistributionSaving(true);
      try {
        const channels = distributionChannels.map((channel) => ({
          channel_id: channel.id,
          selected: distributionDraft[channel.id].selected,
          status: !distributionDraft[channel.id].selected ? "not_selected" : channel.kind === "native" ? "ready" : channel.kind === "discovery" ? "needs_public_page" : "integration_required",
        }));
        const response = await apiFetch(`${API_BASE}/api/jobs/${distributionJob.id}/distribution?organization_id=${encodeURIComponent(organizationId)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channels }),
        });
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `Unable to save distribution settings (${response.status})`);
        const saved: Array<{ channel_id: DistributionChannelId; selected: boolean; status: DistributionStatus }> = await response.json();
        const next = initialDistribution();
        for (const item of saved) next[item.channel_id] = { selected: item.selected, status: item.status };
        setDistributionDraft(next);
        setDistributionByJob((current) => ({ ...current, [key]: next }));
        setDistributionJob(null);
        setMessage("Distribution preferences saved to the organisation database. External publishing is not enabled.");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Unable to save distribution settings.");
      } finally {
        setDistributionSaving(false);
      }
      return;
    }

    setDistributionByJob((current) => ({ ...current, [key]: distributionDraft }));
    setDistributionJob(null);
    setMessage("Demo distribution preferences saved in this browser. No external job board has been contacted or published to.");
  }

  function openCreate() {
    setEditingJob(null);
    setForm(emptyForm);
    setMessage("");
    setShowForm(true);
  }

  function openEdit(job: Job) {
    setEditingJob(job);
    setForm(formFromJob(job));
    setMessage("");
    setShowForm(true);
  }

  async function saveJob(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");

    const payload = {
      ...(editingJob ? {} : { organization_id: ORGANIZATION_ID }),
      title: form.title,
      location: form.location || null,
      employment_type: form.employment_type || null,
      work_mode: form.work_mode || null,
      required_skills: form.skills.split(",").map((s) => s.trim()).filter(Boolean),
      status: form.status,
      description: form.description || null,
      salary_min: form.salary_min ? Number(form.salary_min) : null,
      salary_max: form.salary_max ? Number(form.salary_max) : null,
      salary_currency: form.salary_currency || null,
    };

    try {
      if (!API_BASE || !ORGANIZATION_ID) {
        if (editingJob) {
          setJobs((current) => current.map((job) => job.id === editingJob.id ? { ...job, ...payload, client: form.client } : job));
          setMessage("Demo requisition updated.");
        } else {
          const demoJob: Job = { id: `local-${Date.now()}`, ...payload, client: form.client } as Job;
          setJobs((current) => [demoJob, ...current]);
          setMessage("Demo requisition created.");
        }
      } else {
        const endpoint = editingJob?.id
          ? `${API_BASE}/api/jobs/${editingJob.id}`
          : `${API_BASE}/api/jobs`;
        const response = await apiFetch(endpoint, {
          method: editingJob?.id ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const errorBody = await response.json().catch(() => null);
          throw new Error(errorBody?.detail || `API returned ${response.status}`);
        }
        const saved: Job = await response.json();
        setJobs((current) => editingJob?.id
          ? current.map((job) => job.id === saved.id ? { ...saved, client: form.client } : job)
          : [{ ...saved, client: form.client }, ...current]);
        setMessage(editingJob ? "Requisition updated successfully." : "Requisition created successfully.");
      }

      setForm(emptyForm);
      setEditingJob(null);
      setShowForm(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save requisition.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteJob(job: Job) {
    if (!job.id) return;
    if (!window.confirm(`Delete "${job.title}"? This cannot be undone.`)) return;

    setDeletingId(job.id);
    setMessage("");
    try {
      if (!API_BASE || !ORGANIZATION_ID) {
        setJobs((current) => current.filter((item) => item.id !== job.id));
      } else {
        const response = await apiFetch(`${API_BASE}/api/jobs/${job.id}`, { method: "DELETE" });
        if (!response.ok) {
          const errorBody = await response.json().catch(() => null);
          throw new Error(errorBody?.detail || `API returned ${response.status}`);
        }
        setJobs((current) => current.filter((item) => item.id !== job.id));
      }
      setMessage("Requisition deleted.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to delete requisition.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">Talent<span>OS</span></Link>
        <div className="nav-label">Workspace</div>
        <Link href="/" className="nav-item"><span>⌂</span><span>Dashboard</span></Link>
        <Link href="/jobs" className="nav-item active" aria-current="page"><span>▣</span><span>Jobs</span></Link>
        <Link href="/candidates" className="nav-item"><span>♙</span><span>Candidates</span></Link>
        <Link href="/submissions" className="nav-item"><span>↗</span><span>Submissions</span></Link>
        <Link href="/interviews" className="nav-item"><span>◷</span><span>Interviews</span></Link>
        <Link href="/clients" className="nav-item"><span>□</span><span>Clients</span></Link>
        <div className="nav-item" aria-disabled="true" title="Not available yet"><span>◇</span><span>Vendors</span></div>
        <div className="nav-item" aria-disabled="true" title="Not available yet"><span>♧</span><span>Talent Bench</span></div>
        <Link href="/onboarding" className="nav-item"><span>✓</span><span>Onboarding</span></Link>
        <Link href="/placements" className="nav-item"><span>◈</span><span>Placements</span></Link>
        <div className="nav-item" aria-disabled="true" title="Not available yet"><span>◌</span><span>Leads</span></div>
        <div className="nav-item" aria-disabled="true" title="Not available yet"><span>▤</span><span>Reports</span></div>
        <div className="nav-label">Administration</div>
        <div className="nav-item"><span>⚙</span><span>Settings</span></div>
      </aside>

      <main className="main">
        <header className="topbar">
          <input className="search" placeholder="Search jobs, clients, locations..." value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="profile"><span>Acme Recruitment</span><div className="avatar">VG</div></div>
        </header>

        <section className="content">
          <div className="header-row">
            <div><div className="eyebrow">Recruitment operations</div><h1>Jobs</h1><p className="subtitle">Manage requisitions, hiring requirements and recruitment status.</p></div>
            <button className="btn primary" onClick={openCreate}>+ New requisition</button>
          </div>

          <div className="card" style={{ marginBottom: 18 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <select className="filter" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="all">All statuses</option><option value="draft">Draft</option><option value="open">Open</option><option value="on_hold">On hold</option><option value="closed">Closed</option><option value="filled">Filled</option><option value="cancelled">Cancelled</option>
              </select>
              <span className="muted-small">{filtered.length} requisition{filtered.length === 1 ? "" : "s"}</span>
            </div>
          </div>

          {message && <div className="notice">{message}</div>}

          <div className="card">
            <div className="card-head"><span className="card-title">Requisitions</span><span className="muted-small">{API_BASE ? (loading ? "Loading..." : "Connected to API") : "Demo mode"}</span></div>
            <table className="table">
              <thead><tr><th>Position</th><th>Client</th><th>Location</th><th>Type</th><th>Status</th><th>Skills</th><th>Distribution</th><th>Actions</th></tr></thead>
              <tbody>
                {loading ? <tr><td colSpan={8}>Loading requisitions...</td></tr> : filtered.length === 0 ? <tr><td colSpan={8}>No requisitions yet. Create your first one.</td></tr> : filtered.map((job) => (
                  <tr key={job.id ?? job.title}>
                    <td><strong>{job.title}</strong></td>
                    <td>{job.client ?? "Unassigned"}</td>
                    <td>{job.location ?? "Not specified"}</td>
                    <td>{job.employment_type ?? "-"}</td>
                    <td><span className={`badge ${job.status === "open" ? "green" : job.status === "draft" ? "blue" : "amber"}`}>{job.status.replace("_", " ")}</span></td>
                    <td>{(job.required_skills ?? []).slice(0, 3).join(", ") || "-"}</td>
                    <td><button className="btn" onClick={() => openDistribution(job)}>Distribute job</button></td>
                    <td><div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><button className="btn" onClick={() => openEdit(job)}>Edit</button><button className="btn" disabled={deletingId === job.id} onClick={() => deleteJob(job)}>{deletingId === job.id ? "..." : "Delete"}</button></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      {distributionJob && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal distribution-modal" role="dialog" aria-modal="true" aria-labelledby="distribution-title">
            <div className="card-head">
              <div><span className="card-title" id="distribution-title">Job distribution</span><div className="muted-small" style={{ marginTop: 5 }}>{distributionJob.title}</div></div>
              <button type="button" className="icon-button" aria-label="Close distribution settings" onClick={() => setDistributionJob(null)}>×</button>
            </div>
            <div className="notice">{distributionLoading ? "Loading saved channel preferences…" : API_BASE && distributionJob.id && !distributionJob.id.startsWith("demo-") && !distributionJob.id.startsWith("local-") ? "Channel preferences are saved per job in the organisation database. External publishing still requires configured partner APIs or feeds." : "Demo mode: channel choices persist in this browser. External publishing requires configured partner APIs or feeds."}</div>
            <div className="distribution-list">
              {distributionChannels.map((channel) => {
                const entry = distributionDraft[channel.id];
                return (
                  <label className="distribution-option" key={channel.id}>
                    <input
                      type="checkbox"
                      checked={entry.selected}
                      onChange={(event) => setDistributionDraft((current) => ({
                        ...current,
                        [channel.id]: {
                          ...current[channel.id],
                          selected: event.target.checked,
                          status: channel.kind === "native" ? "ready" : channel.kind === "discovery" ? "needs_public_page" : "integration_required",
                        },
                      }))}
                    />
                    <span className="distribution-option-main">
                      <strong>{channel.name}</strong>
                      <span className="muted-small">{channel.description}</span>
                      <span className={`distribution-status ${entry.selected && entry.status === "ready" ? "status-ready" : entry.selected ? "status-pending" : ""}`}>
                        {distributionStatusLabel(channel, entry)}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
            <div className="muted-small">Publishing, indexing and applicant synchronisation are not simulated as successful. The status labels indicate what setup is still required.</div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setDistributionJob(null)}>Cancel</button>
              <button type="button" className="btn primary" disabled={distributionLoading || distributionSaving} onClick={saveDistribution}>{distributionSaving ? "Saving…" : "Save distribution settings"}</button>
            </div>
          </section>
        </div>
      )}

      {showForm && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={saveJob}>
            <div className="card-head"><span className="card-title">{editingJob ? "Edit requisition" : "New requisition"}</span><button type="button" className="icon-button" onClick={() => setShowForm(false)}>×</button></div>
            <label>Job title<input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Senior Python Engineer" /></label>
            <label>Client<input value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} placeholder="Client name" /></label>
            <label>Location<input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="London, UK / Remote" /></label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label>Employment type<select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}><option>Permanent</option><option>Contract</option><option>Temporary</option><option>Part-time</option></select></label>
              <label>Work mode<select value={form.work_mode} onChange={(e) => setForm({ ...form, work_mode: e.target.value })}><option>Hybrid</option><option>Remote</option><option>On-site</option></select></label>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 100px", gap: 12 }}>
              <label>Min salary<input type="number" min="0" value={form.salary_min} onChange={(e) => setForm({ ...form, salary_min: e.target.value })} /></label>
              <label>Max salary<input type="number" min="0" value={form.salary_max} onChange={(e) => setForm({ ...form, salary_max: e.target.value })} /></label>
              <label>Currency<input maxLength={3} value={form.salary_currency} onChange={(e) => setForm({ ...form, salary_currency: e.target.value.toUpperCase() })} /></label>
            </div>
            <label>Status<select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as Job["status"] })}><option value="draft">Draft</option><option value="open">Open</option><option value="on_hold">On hold</option><option value="closed">Closed</option><option value="filled">Filled</option><option value="cancelled">Cancelled</option></select></label>
            <label>Required skills<input value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} placeholder="Python, FastAPI, PostgreSQL" /></label>
            <label>Description<textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Hiring requirements, responsibilities and notes..." rows={4} /></label>
            <div className="modal-actions"><button type="button" className="btn" onClick={() => setShowForm(false)}>Cancel</button><button className="btn primary" disabled={saving}>{saving ? "Saving..." : editingJob ? "Save changes" : "Create requisition"}</button></div>
          </form>
        </div>
      )}
    </div>
  );
}

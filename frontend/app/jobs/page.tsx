'use client';

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
const ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID;

type Job = {
  id?: string;
  title: string;
  client?: string;
  location?: string;
  status: "draft" | "open" | "on_hold" | "closed" | "filled" | "cancelled";
  employment_type?: string;
  required_skills?: string[];
};

const seedJobs: Job[] = [
  { id: "demo-1", title: "Senior Python Engineer", client: "Northstar Digital", location: "London, UK", status: "open", employment_type: "Permanent", required_skills: ["Python", "FastAPI", "PostgreSQL"] },
  { id: "demo-2", title: "Data Analyst", client: "Brightline Group", location: "Manchester, UK", status: "open", employment_type: "Permanent", required_skills: ["SQL", "Tableau", "Python"] },
  { id: "demo-3", title: "Full Stack Developer", client: "Vertex Systems", location: "Remote, UK", status: "open", employment_type: "Contract", required_skills: ["TypeScript", "React", "Node.js"] },
];

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>(API_BASE ? [] : seedJobs);
  const [loading, setLoading] = useState(Boolean(API_BASE));
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({ title: "", client: "", location: "", employment_type: "Permanent", skills: "" });

  useEffect(() => {
    if (!API_BASE || !ORGANIZATION_ID) return;
    let cancelled = false;
    async function loadJobs() {
      try {
        const response = await fetch(`${API_BASE}/api/jobs?organization_id=${encodeURIComponent(ORGANIZATION_ID)}`);
        if (!response.ok) throw new Error(`API returned ${response.status}`);
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
    const matchesQuery = `${job.title} ${job.client ?? ""} ${job.location ?? ""}`.toLowerCase().includes(query.toLowerCase());
    const matchesStatus = status === "all" || job.status === status;
    return matchesQuery && matchesStatus;
  }), [jobs, query, status]);

  async function createJob(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    const payload = {
      organization_id: ORGANIZATION_ID,
      title: form.title,
      location: form.location || null,
      employment_type: form.employment_type,
      required_skills: form.skills.split(",").map((s) => s.trim()).filter(Boolean),
      status: "draft",
    };

    try {
      if (!API_BASE || !ORGANIZATION_ID) {
        const demoJob: Job = {
          id: `local-${Date.now()}`,
          title: form.title,
          client: form.client || "Unassigned",
          location: form.location || "Not specified",
          employment_type: form.employment_type,
          required_skills: payload.required_skills,
          status: "draft",
        };
        setJobs((current) => [demoJob, ...current]);
        setMessage("Demo requisition created. Connect the FastAPI backend to persist production data.");
      } else {
        const response = await fetch(`${API_BASE}/api/jobs`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        const created = await response.json();
        setJobs((current) => [{ ...created, client: form.client }, ...current]);
        setMessage("Requisition created successfully.");
      }
      setForm({ title: "", client: "", location: "", employment_type: "Permanent", skills: "" });
      setShowForm(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create requisition.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">Talent<span>OS</span></Link>
        <div className="nav-label">Workspace</div>
        <Link href="/" className="nav-item"><span>⌂</span><span>Dashboard</span></Link>
        <div className="nav-item active"><span>▣</span><span>Jobs</span></div>
        {['Candidates','Submissions','Interviews','Clients','Vendors','Talent Bench','Onboarding','Placements','Leads','Reports'].map((item) => <div key={item} className="nav-item"><span>•</span><span>{item}</span></div>)}
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
            <button className="btn primary" onClick={() => setShowForm(true)}>+ New requisition</button>
          </div>

          <div className="card" style={{ marginBottom: 18 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <select className="filter" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="all">All statuses</option><option value="draft">Draft</option><option value="open">Open</option><option value="on_hold">On hold</option><option value="closed">Closed</option><option value="filled">Filled</option>
              </select>
              <span className="muted-small">{filtered.length} requisition{filtered.length === 1 ? "" : "s"}</span>
            </div>
          </div>

          {message && <div className="notice">{message}</div>}

          <div className="card">
            <div className="card-head"><span className="card-title">Requisitions</span><span className="muted-small">{API_BASE ? (loading ? "Loading..." : "Connected to API") : "Demo mode"}</span></div>
            <table className="table"><thead><tr><th>Position</th><th>Client</th><th>Location</th><th>Type</th><th>Status</th><th>Skills</th></tr></thead>
              <tbody>{loading ? <tr><td colSpan={6}>Loading requisitions...</td></tr> : filtered.map((job) => <tr key={job.id ?? job.title}><td><strong>{job.title}</strong></td><td>{job.client ?? "Unassigned"}</td><td>{job.location ?? "Not specified"}</td><td>{job.employment_type ?? "-"}</td><td><span className={`badge ${job.status === "open" ? "green" : job.status === "draft" ? "blue" : "amber"}`}>{job.status.replace("_", " ")}</span></td><td>{(job.required_skills ?? []).slice(0, 3).join(", ") || "-"}</td></tr>)}</tbody>
            </table>
          </div>
        </section>
      </main>

      {showForm && <div className="modal-backdrop"><form className="modal" onSubmit={createJob}><div className="card-head"><span className="card-title">New requisition</span><button type="button" className="icon-button" onClick={() => setShowForm(false)}>×</button></div><label>Job title<input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Senior Python Engineer" /></label><label>Client<input value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} placeholder="Client name" /></label><label>Location<input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="London, UK / Remote" /></label><label>Employment type<select value={form.employment_type} onChange={(e) => setForm({ ...form, employment_type: e.target.value })}><option>Permanent</option><option>Contract</option><option>Temporary</option><option>Part-time</option></select></label><label>Required skills<input value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} placeholder="Python, FastAPI, PostgreSQL" /></label><div className="modal-actions"><button type="button" className="btn" onClick={() => setShowForm(false)}>Cancel</button><button className="btn primary" disabled={saving}>{saving ? "Saving..." : "Create requisition"}</button></div></form></div>}
    </div>
  );
}

'use client';

import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { FormEvent, useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Candidate = {
  id: string;
  organization_id: string;
  first_name: string;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  city?: string | null;
  region?: string | null;
  country_code?: string | null;
  status: "active" | "inactive" | "placed" | "do_not_contact";
  current_title?: string | null;
  years_experience?: number | null;
  skills: string[];
  ai_summary?: string | null;
};

type CandidateForm = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  city: string;
  region: string;
  country_code: string;
  status: Candidate["status"];
  current_title: string;
  years_experience: string;
  skills: string;
};

const emptyForm: CandidateForm = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  city: "",
  region: "",
  country_code: "GB",
  status: "active",
  current_title: "",
  years_experience: "",
  skills: "",
};

function fullName(candidate: Candidate) {
  return [candidate.first_name, candidate.last_name].filter(Boolean).join(" ");
}

function formFromCandidate(candidate: Candidate): CandidateForm {
  return {
    first_name: candidate.first_name,
    last_name: candidate.last_name ?? "",
    email: candidate.email ?? "",
    phone: candidate.phone ?? "",
    city: candidate.city ?? "",
    region: candidate.region ?? "",
    country_code: candidate.country_code ?? "GB",
    status: candidate.status,
    current_title: candidate.current_title ?? "",
    years_experience: candidate.years_experience?.toString() ?? "",
    skills: candidate.skills.join(", "),
  };
}

export default function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(Boolean(API_BASE));
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [country, setCountry] = useState("all");
  const [sortBy, setSortBy] = useState<"name" | "title" | "location" | "status">("name");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkStatus, setBulkStatus] = useState<Candidate["status"]>("active");
  const [savedViews, setSavedViews] = useState<Array<{ name: string; query: string; status: string; country: string }>>([]);
  const [activeView, setActiveView] = useState("All candidates");
  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Candidate | null>(null);
  const [form, setForm] = useState<CandidateForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    try { const stored = window.localStorage.getItem("talentos_candidate_views"); if (stored) setSavedViews(JSON.parse(stored)); } catch { /* Ignore invalid saved view data. */ }
  }, []);

  useEffect(() => {
    const organizationId = typeof window !== "undefined" ? window.localStorage.getItem("talentos_active_org") || ORGANIZATION_ID : ORGANIZATION_ID;
    if (!API_BASE || !organizationId) { setLoading(false); return; }

    let cancelled = false;

    async function load() {
      try {
        const response = await apiFetch(
          API_BASE + "/api/candidates?organization_id=" + encodeURIComponent(organizationId)
        );
        if (!response.ok) throw new Error("API returned " + response.status);
        const data: Candidate[] = await response.json();
        if (!cancelled) setCandidates(data);
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : "Unable to load candidates.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => candidates.filter((candidate) => {
    const haystack = (
      fullName(candidate) + " " +
      (candidate.email ?? "") + " " +
      (candidate.current_title ?? "") + " " +
      (candidate.city ?? "") + " " +
      candidate.skills.join(" ")
    ).toLowerCase();

    return haystack.includes(query.toLowerCase()) && (status === "all" || candidate.status === status) && (country === "all" || (candidate.country_code ?? "").toUpperCase() === country);
  }).sort((a, b) => {
    const value = (candidate: Candidate) => sortBy === "title" ? candidate.current_title ?? "" : sortBy === "location" ? [candidate.city, candidate.region, candidate.country_code].filter(Boolean).join(", ") : sortBy === "status" ? candidate.status : fullName(candidate);
    const comparison = value(a).localeCompare(value(b), undefined, { sensitivity: "base" });
    return sortDirection === "asc" ? comparison : -comparison;
  }), [candidates, query, status, country, sortBy, sortDirection]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visibleCandidates = filtered.slice((page - 1) * pageSize, page * pageSize);
  const allVisibleSelected = visibleCandidates.length > 0 && visibleCandidates.every((candidate) => selectedIds.includes(candidate.id));
  function changeSort(field: typeof sortBy) { if (sortBy === field) setSortDirection((direction) => direction === "asc" ? "desc" : "asc"); else { setSortBy(field); setSortDirection("asc"); } }
  function saveCurrentView() {
    const name = window.prompt("Name this saved view"); if (!name?.trim()) return;
    const next = [...savedViews.filter((view) => view.name.toLowerCase() !== name.trim().toLowerCase()), { name: name.trim(), query, status, country }];
    setSavedViews(next); setActiveView(name.trim()); window.localStorage.setItem("talentos_candidate_views", JSON.stringify(next)); setMessage("View saved.");
  }
  function applyView(name: string) {
    setActiveView(name);
    if (name === "All candidates") { setQuery(""); setStatus("all"); setCountry("all"); }
    else { const view = savedViews.find((item) => item.name === name); if (view) { setQuery(view.query); setStatus(view.status); setCountry(view.country); } }
    setPage(1);
  }
  function exportCandidates() {
    const escapeCsv = (value: unknown) => '"' + String(value ?? "").replace(/"/g, '""') + '"';
    const rows = [["Candidate ID","First name","Last name","Email","Phone","City","Region","Country","Current title","Years experience","Skills","Status"], ...filtered.map((candidate) => [candidate.id,candidate.first_name,candidate.last_name,candidate.email,candidate.phone,candidate.city,candidate.region,candidate.country_code,candidate.current_title,candidate.years_experience,candidate.skills.join("; "),candidate.status])];
    const csv = rows.map((row) => row.map(escapeCsv).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" })); const link = document.createElement("a"); link.href = url; link.download = "talentos-candidates.csv"; link.click(); URL.revokeObjectURL(url);
  }
  async function applyBulkStatus() {
    if (!selectedIds.length) return; setSaving(true); setMessage("");
    try {
      const results = await Promise.all(selectedIds.map(async (id) => {
        const response = await apiFetch(API_BASE + "/api/candidates/" + id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: bulkStatus }) });
        if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(body?.detail || "Could not update every selected candidate."); }
        return await response.json() as Candidate;
      }));
      const byId = new Map(results.map((candidate) => [candidate.id, candidate])); setCandidates((current) => current.map((candidate) => byId.get(candidate.id) ?? candidate)); setSelectedIds([]); setMessage("Updated " + results.length + " candidate(s).");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Bulk update failed. Some updates may have succeeded; refresh to verify."); }
    finally { setSaving(false); }
  }

  function openCreate() {
    setEditing(null);
    setForm(emptyForm);
    setMessage("");
    setShowForm(true);
  }

  function openEdit(candidate: Candidate) {
    setEditing(candidate);
    setForm(formFromCandidate(candidate));
    setMessage("");
    setShowForm(true);
  }

  async function saveCandidate(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");

    const payload = {
      ...(editing ? {} : { organization_id: ORGANIZATION_ID }),
      first_name: form.first_name,
      last_name: form.last_name || null,
      email: form.email || null,
      phone: form.phone || null,
      city: form.city || null,
      region: form.region || null,
      country_code: form.country_code,
      status: form.status,
      current_title: form.current_title || null,
      years_experience: form.years_experience ? Number(form.years_experience) : null,
      skills: form.skills.split(",").map((skill) => skill.trim()).filter(Boolean),
    };

    try {
      if (!API_BASE || !ORGANIZATION_ID) {
        setMessage("API configuration is missing.");
        return;
      }

      const endpoint = editing
        ? API_BASE + "/api/candidates/" + editing.id
        : API_BASE + "/api/candidates";

      const response = await apiFetch(endpoint, {
        method: editing ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "API returned " + response.status);
      }

      const saved: Candidate = await response.json();
      setCandidates((current) =>
        editing
          ? current.map((item) => item.id === saved.id ? saved : item)
          : [saved, ...current]
      );
      setMessage(editing ? "Candidate updated successfully." : "Candidate created successfully.");
      setEditing(null);
      setForm(emptyForm);
      setShowForm(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save candidate.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteCandidate(candidate: Candidate) {
    if (!window.confirm("Delete " + fullName(candidate) + "? This cannot be undone.")) return;

    try {
      const response = await apiFetch(API_BASE + "/api/candidates/" + candidate.id, { method: "DELETE" });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || "API returned " + response.status);
      }
      setCandidates((current) => current.filter((item) => item.id !== candidate.id));
      setMessage("Candidate deleted.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to delete candidate.");
    }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand">Talent<span>OS</span></Link>
        <div className="nav-label">Workspace</div>
        <Link href="/" className="nav-item"><span>⌂</span><span>Dashboard</span></Link>
        <Link href="/jobs" className="nav-item"><span>▣</span><span>Jobs</span></Link>
        <div className="nav-item active"><span>●</span><span>Candidates</span></div>
        {["Submissions", "Interviews", "Clients", "Vendors", "Talent Bench", "Onboarding", "Placements", "Leads", "Reports"].map((item) => (
          <div key={item} className="nav-item"><span>•</span><span>{item}</span></div>
        ))}
        <div className="nav-label">Administration</div>
        <div className="nav-item"><span>⚙</span><span>Settings</span></div>
      </aside>

      <main className="main">
        <header className="topbar">
          <input className="search" placeholder="Search candidates, skills, titles..." value={query} onChange={(e) => { setQuery(e.target.value); setPage(1); }} />
          <div className="profile"><span>Acme Recruitment</span><div className="avatar">VG</div></div>
        </header>

        <section className="content">
          <div className="header-row">
            <div>
              <div className="eyebrow">Talent database</div>
              <h1>Candidates</h1>
              <p className="subtitle">Build and manage your searchable candidate pool.</p>
            </div>
            <button className="btn primary" onClick={openCreate}>+ Add candidate</button>
          </div>

          <div className="card" style={{ marginBottom: 18 }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <select className="filter" aria-label="Saved candidate views" value={activeView} onChange={(e) => applyView(e.target.value)}><option>All candidates</option>{savedViews.map((view) => <option key={view.name}>{view.name}</option>)}</select>
              <button className="btn" onClick={saveCurrentView}>Save view</button>
              <select className="filter" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="placed">Placed</option>
                <option value="do_not_contact">Do not contact</option>
              </select>
              <select className="filter" aria-label="Filter by country" value={country} onChange={(e) => { setCountry(e.target.value); setPage(1); }}><option value="all">All countries</option>{[...new Set(candidates.map((candidate) => (candidate.country_code ?? "").toUpperCase()).filter(Boolean))].sort().map((code) => <option key={code} value={code}>{code}</option>)}</select>
              <span className="muted-small">{filtered.length} candidate{filtered.length === 1 ? "" : "s"}</span><span style={{ flex: 1 }} /><button className="btn" onClick={exportCandidates}>Export CSV</button>
            </div>
          </div>

          {message && <div className="notice">{message}</div>}

          <div className="card">
            <div className="card-head" style={{ flexWrap: "wrap", gap: 10 }}>
              <span className="card-title">Candidate register</span><div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}><span className="muted-small">{API_BASE ? (loading ? "Loading..." : "Connected to API") : "API not configured"}</span><select className="filter" aria-label="Bulk status" value={bulkStatus} onChange={(e) => setBulkStatus(e.target.value as Candidate["status"])}><option value="active">Set Active</option><option value="inactive">Set Inactive</option><option value="placed">Set Placed</option><option value="do_not_contact">Set Do not contact</option></select><button className="btn" disabled={!selectedIds.length || saving} onClick={applyBulkStatus}>{saving ? "Updating..." : "Apply to " + selectedIds.length + " selected"}</button></div>
            </div>
            <div style={{ overflowX: "auto" }}><table className="table">
              <thead><tr><th><input type="checkbox" aria-label="Select all visible candidates" checked={allVisibleSelected} onChange={(e) => setSelectedIds((current) => e.target.checked ? [...new Set([...current, ...visibleCandidates.map((candidate) => candidate.id)])] : current.filter((id) => !visibleCandidates.some((candidate) => candidate.id === id)))} /></th><th><button className="table-sort" onClick={() => changeSort("name")}>Candidate {sortBy === "name" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th><button className="table-sort" onClick={() => changeSort("title")}>Current role {sortBy === "title" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th><button className="table-sort" onClick={() => changeSort("location")}>Location {sortBy === "location" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th>Experience</th><th>Skills</th><th><button className="table-sort" onClick={() => changeSort("status")}>Status {sortBy === "status" ? (sortDirection === "asc" ? "↑" : "↓") : ""}</button></th><th>Actions</th></tr></thead>
              <tbody>
                {loading ? (<tr><td colSpan={8}>Loading candidates...</td></tr>) : filtered.length === 0 ? (<tr><td colSpan={8}>No candidates match these filters. Adjust your search or add a candidate.</td></tr>) : visibleCandidates.map((candidate) => (
                  <tr key={candidate.id}>
                    <td><input type="checkbox" aria-label={"Select " + fullName(candidate)} checked={selectedIds.includes(candidate.id)} onChange={(e) => setSelectedIds((current) => e.target.checked ? [...current, candidate.id] : current.filter((id) => id !== candidate.id))} /></td>
                    <td>
                      <Link className="link" href={"/candidates/" + candidate.id}><strong>{fullName(candidate)}</strong></Link>
                      <div className="muted-small">{candidate.email ?? "No email"}</div>
                    </td>
                    <td>{candidate.current_title ?? "Not specified"}</td>
                    <td>{[candidate.city, candidate.region].filter(Boolean).join(", ") || "Not specified"}</td>
                    <td>{candidate.years_experience != null ? candidate.years_experience + " yrs" : "-"}</td>
                    <td>{candidate.skills.slice(0, 3).join(", ") || "-"}</td>
                    <td><span className={"badge " + (candidate.status === "active" ? "green" : candidate.status === "placed" ? "blue" : "amber")}>{candidate.status.replaceAll("_", " ")}</span></td>
                    <td>
                      <div style={{ display: "flex", gap: 6 }}>
                        <Link className="btn" href={"/candidates/" + candidate.id}>View</Link><button className="btn" onClick={() => openEdit(candidate)}>Edit</button>
                        <button className="btn" onClick={() => deleteCandidate(candidate)}>Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table></div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", paddingTop: 16 }}><span className="muted-small">Showing {filtered.length ? (page - 1) * pageSize + 1 : 0}–{Math.min(page * pageSize, filtered.length)} of {filtered.length}</span><div style={{ display: "flex", gap: 8, alignItems: "center" }}><button className="btn" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</button><span className="muted-small">Page {page} of {pageCount}</span><button className="btn" disabled={page >= pageCount} onClick={() => setPage((current) => Math.min(pageCount, current + 1))}>Next</button></div></div>
          </div>
        </section>
      </main>

      {showForm && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={saveCandidate}>
            <div className="card-head">
              <span className="card-title">{editing ? "Edit candidate" : "Add candidate"}</span>
              <button type="button" className="icon-button" onClick={() => setShowForm(false)}>×</button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label>First name<input required value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} /></label>
              <label>Last name<input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} /></label>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label>Email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
              <label>Phone<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
            </div>
            <label>Current title<input value={form.current_title} onChange={(e) => setForm({ ...form, current_title: e.target.value })} placeholder="e.g. Senior Python Developer" /></label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
              <label>City<input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></label>
              <label>Region<input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} /></label>
              <label>Country code<input required maxLength={2} pattern="[A-Za-z]{2}" value={form.country_code} onChange={(e) => setForm({ ...form, country_code: e.target.value.toUpperCase() })} placeholder="GB" /></label>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <label>Years of experience<input type="number" min="0" max="80" step="0.5" value={form.years_experience} onChange={(e) => setForm({ ...form, years_experience: e.target.value })} /></label>
              <label>Status<select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as Candidate["status"] })}><option value="active">Active</option><option value="inactive">Inactive</option><option value="placed">Placed</option><option value="do_not_contact">Do not contact</option></select></label>
            </div>
            <label>Skills<input value={form.skills} onChange={(e) => setForm({ ...form, skills: e.target.value })} placeholder="Python, SQL, FastAPI, PostgreSQL" /></label>

            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn primary" disabled={saving}>{saving ? "Saving..." : editing ? "Save changes" : "Create candidate"}</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

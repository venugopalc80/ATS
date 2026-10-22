"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";
type Application = { id: string; candidate_id: string; job_id: string; status: string };
type Candidate = { id: string; first_name: string; last_name?: string | null };
type Job = { id: string; title: string };
type Offer = {
  id: string; application_id: string; title: string; status: string; current_version?: number;
  employment_type?: string | null; start_date?: string | null; salary_amount?: number | null;
  salary_currency?: string | null; benefits?: string | null; expires_at?: string | null; notes?: string | null;
};
const name = (candidate?: Candidate) => candidate ? [candidate.first_name, candidate.last_name].filter(Boolean).join(" ") : "Unknown candidate";

export default function OffersPage() {
  const [items, setItems] = useState<Offer[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [saving, setSaving] = useState(false);
  const [applicationId, setApplicationId] = useState("");
  const [title, setTitle] = useState("");
  const [employmentType, setEmploymentType] = useState("Permanent");
  const [startDate, setStartDate] = useState("");
  const [salary, setSalary] = useState("");
  const [currency, setCurrency] = useState("GBP");
  const [benefits, setBenefits] = useState("");
  const [conditions, setConditions] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const org = getActiveOrganizationId(DEFAULT_ORG);
  const candidateMap = useMemo(() => new Map(candidates.map(c => [c.id, c])), [candidates]);
  const jobMap = useMemo(() => new Map(jobs.map(j => [j.id, j])), [jobs]);
  const appMap = useMemo(() => new Map(apps.map(a => [a.id, a])), [apps]);

  async function load() {
    try {
      const q = encodeURIComponent(org);
      const [offersResponse, appsResponse, candidatesResponse, jobsResponse] = await Promise.all([
        apiFetch(API_BASE + `/api/offers?organization_id=${q}`),
        apiFetch(API_BASE + `/api/applications?organization_id=${q}`),
        apiFetch(API_BASE + `/api/candidates?organization_id=${q}`),
        apiFetch(API_BASE + `/api/jobs?organization_id=${q}`),
      ]);
      if (![offersResponse, appsResponse, candidatesResponse, jobsResponse].every(r => r.ok)) throw new Error("Unable to load offer workspace.");
      setItems(await offersResponse.json()); setApps(await appsResponse.json());
      setCandidates(await candidatesResponse.json()); setJobs(await jobsResponse.json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load offers.");
    } finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);

  const label = (id: string) => {
    const application = appMap.get(id);
    return application ? `${name(candidateMap.get(application.candidate_id))} · ${jobMap.get(application.job_id)?.title ?? "Unknown job"}` : id;
  };

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!applicationId || !title.trim()) { setMessage("Select an application and enter an offer title."); return; }
    setSaving(true);
    try {
      const response = await apiFetch(API_BASE + "/api/offers", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          organization_id: org, application_id: applicationId, title: title.trim(), status: "draft",
          employment_type: employmentType, start_date: startDate || null,
          salary_amount: salary ? Number(salary) : null, salary_currency: currency,
          benefits: benefits || null, notes: conditions || null, expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        }),
      });
      if (!response.ok) { const data = await response.json().catch(() => null); throw new Error(data?.detail ?? "Unable to create offer."); }
      setShowCreate(false); setApplicationId(""); setTitle(""); setStartDate(""); setSalary("");
      setBenefits(""); setConditions(""); setExpiresAt(""); setMessage("Draft offer created. Submit it for approval when the terms are ready.");
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to create offer."); }
    finally { setSaving(false); }
  }

  async function action(item: Offer, actionName: string, body?: object) {
    setSaving(true); setMessage("");
    try {
      const response = await apiFetch(API_BASE + `/api/offers/${item.id}/${actionName}?organization_id=${encodeURIComponent(org)}`, {
        method: "POST", headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!response.ok) { const data = await response.json().catch(() => null); throw new Error(data?.detail ?? "Offer action failed."); }
      setMessage("Offer updated successfully."); await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Offer action failed."); }
    finally { setSaving(false); }
  }

  const statusStyle = (status: string) => status === "accepted" ? "text-green-700 bg-green-50" :
    status === "declined" || status === "withdrawn" || status === "expired" ? "text-gray-600 bg-gray-100" :
    status === "awaiting_approval" ? "text-amber-800 bg-amber-50" : "text-blue-700 bg-blue-50";

  return <main className="p-8">
    <div className="flex items-center justify-between gap-4">
      <div><h1 className="text-3xl font-semibold">Offer management</h1><p className="mt-2 text-sm text-gray-500">Prepare terms, request approval, issue approved offers and track candidate responses.</p></div>
      <button className="btn primary" onClick={() => setShowCreate(true)}>+ New offer</button>
    </div>
    {message && <div className="notice mt-4" role="status">{message}</div>}
    {showCreate && <div className="modal-backdrop"><form className="modal" onSubmit={create}>
      <div className="card-head"><span className="card-title">Prepare offer draft</span><button type="button" className="icon-button" onClick={() => setShowCreate(false)} aria-label="Close">×</button></div>
      <label>Application<select required value={applicationId} onChange={e => setApplicationId(e.target.value)}><option value="">Select candidate / job</option>{apps.filter(a => ["interview", "offer"].includes(a.status)).map(a => <option key={a.id} value={a.id}>{label(a.id)}</option>)}</select></label>
      <label>Offer title<input required value={title} onChange={e => setTitle(e.target.value)} placeholder="Senior Software Engineer" /></label>
      <label>Employment type<select value={employmentType} onChange={e => setEmploymentType(e.target.value)}><option>Permanent</option><option>Fixed-term</option><option>Contract</option><option>Part-time</option><option>Temporary</option><option>Internship</option></select></label>
      <div className="grid grid-cols-2 gap-3"><label>Start date<input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} /></label><label>Expiry date and time<input type="datetime-local" value={expiresAt} onChange={e => setExpiresAt(e.target.value)} /></label></div>
      <div className="grid grid-cols-2 gap-3"><label>Base salary<input type="number" min="0" step="0.01" value={salary} onChange={e => setSalary(e.target.value)} /></label><label>Currency<select value={currency} onChange={e => setCurrency(e.target.value)}><option>GBP</option><option>USD</option><option>INR</option><option>AUD</option></select></label></div>
      <label>Benefits<textarea value={benefits} onChange={e => setBenefits(e.target.value)} maxLength={8000} placeholder="Bonus, leave, pension, health benefits…" /></label>
      <label>Conditions and internal notes<textarea value={conditions} onChange={e => setConditions(e.target.value)} maxLength={8000} placeholder="Conditions precedent and notes for the approval process…" /></label>
      <div className="modal-actions"><button type="button" className="btn" onClick={() => setShowCreate(false)}>Cancel</button><button className="btn primary" disabled={saving}>{saving ? "Saving…" : "Create draft"}</button></div>
    </form></div>}
    <div className="mt-8 overflow-x-auto rounded-xl border"><table className="w-full text-left text-sm">
      <thead><tr className="border-b bg-gray-50"><th className="p-4">Candidate / job</th><th className="p-4">Offer</th><th className="p-4">Salary</th><th className="p-4">Start date</th><th className="p-4">Version</th><th className="p-4">Status / actions</th></tr></thead>
      <tbody>{loading ? <tr><td className="p-4" colSpan={6}>Loading offers…</td></tr> : items.map(item => <tr key={item.id} className="border-b align-top">
        <td className="p-4"><Link className="font-medium" href="/submissions">{label(item.application_id)}</Link></td>
        <td className="p-4"><div className="font-medium">{item.title}</div><div className="mt-1 text-xs text-gray-500">{item.employment_type || "Employment type not set"}</div></td>
        <td className="p-4">{item.salary_amount != null ? `${item.salary_currency || ""} ${item.salary_amount}` : "—"}</td>
        <td className="p-4">{item.start_date || "—"}</td>
        <td className="p-4">v{item.current_version ?? 1}</td>
        <td className="p-4"><span className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${statusStyle(item.status)}`}>{item.status.replaceAll("_", " ")}</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {item.status === "draft" && <button className="btn" disabled={saving} onClick={() => void action(item, "submit-for-approval")}>Request approval</button>}
            {item.status === "awaiting_approval" && <><button className="btn primary" disabled={saving} onClick={() => void action(item, "approval", { decision: "approved" })}>Approve</button><button className="btn" disabled={saving} onClick={() => { const comments = window.prompt("Reason for requesting changes (required for audit):"); if (comments?.trim()) void action(item, "approval", { decision: "changes_requested", comments }); }}>Request changes</button><button className="btn" disabled={saving} onClick={() => { const comments = window.prompt("Reason for rejection (required for audit):"); if (comments?.trim()) void action(item, "approval", { decision: "rejected", comments }); }}>Reject</button></>}
            {item.status === "approved" && <button className="btn primary" disabled={saving} onClick={() => void action(item, "issue")}>Issue offer</button>}
            {item.status === "issued" && <><button className="btn" disabled={saving} onClick={() => { const evidence_reference = window.prompt("Enter the reference to the recorded candidate acceptance evidence:"); if (evidence_reference?.trim()) void action(item, "record-candidate-response", { response: "accepted", evidence_reference }); }}>Record acceptance</button><button className="btn" disabled={saving} onClick={() => { const evidence_reference = window.prompt("Enter the reference to the recorded candidate decline evidence:"); if (evidence_reference?.trim()) void action(item, "record-candidate-response", { response: "declined", evidence_reference }); }}>Record decline</button></>}
          </div>
        </td>
      </tr>)}{!loading && !items.length && <tr><td className="p-4 text-gray-500" colSpan={6}>No offers yet. Create a draft linked to an existing application.</td></tr>}</tbody>
    </table></div>
    <p className="mt-4 text-xs text-gray-500">Candidate responses recorded here are staff-entered and require an evidence reference. Candidate self-service acceptance and secure offer-document delivery are separate release items.</p>
  </main>;
}

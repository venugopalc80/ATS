"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

type Client = { id: string; name: string };
type Job = { id: string; title: string; client_id?: string | null };
type RateCard = {
  id: string; client_id: string; job_id?: string | null; name: string;
  employment_type: "permanent" | "contract" | "temporary";
  rate_basis: "hourly" | "daily" | "annual_salary" | "fixed_fee" | "percentage_fee";
  currency: string; rate_amount?: number | null; fee_percentage?: number | null;
  effective_from: string; effective_to?: string | null;
  status: "draft" | "active" | "expired" | "archived"; version: number; notes?: string | null;
};
type Form = {
  client_id: string; job_id: string; name: string; employment_type: RateCard["employment_type"];
  rate_basis: RateCard["rate_basis"]; currency: string; rate_amount: string;
  fee_percentage: string; effective_from: string; effective_to: string; notes: string;
};
const blank: Form = {
  client_id: "", job_id: "", name: "", employment_type: "permanent",
  rate_basis: "percentage_fee", currency: "GBP", rate_amount: "", fee_percentage: "15",
  effective_from: new Date().toISOString().slice(0, 10), effective_to: "", notes: "",
};
const basisLabels: Record<RateCard["rate_basis"], string> = {
  hourly: "Hourly rate", daily: "Daily rate", annual_salary: "Annual salary", fixed_fee: "Fixed fee", percentage_fee: "Percentage fee",
};
const money = (value: number | null | undefined, currency: string) =>
  value == null ? "—" : new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value);

export default function RateCardsPage() {
  const org = getActiveOrganizationId(DEFAULT_ORG);
  const [cards, setCards] = useState<RateCard[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [form, setForm] = useState<Form>(blank);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const clientMap = useMemo(() => new Map(clients.map((client) => [client.id, client.name])), [clients]);
  const jobMap = useMemo(() => new Map(jobs.map((job) => [job.id, job.title])), [jobs]);
  const filtered = useMemo(() => cards.filter((card) => statusFilter === "all" || card.status === statusFilter), [cards, statusFilter]);

  async function load() {
    if (!API_BASE || !org) { setMessage("Choose an organisation and configure the API URL to use rate cards."); setLoading(false); return; }
    try {
      const q = encodeURIComponent(org);
      const results = await Promise.all([
        apiFetch(API_BASE + "/api/rate-cards?organization_id=" + q),
        apiFetch(API_BASE + "/api/clients?organization_id=" + q),
        apiFetch(API_BASE + "/api/jobs?organization_id=" + q),
      ]);
      if (results.some((response) => !response.ok)) throw new Error("Unable to load rate cards. Check your access and try again.");
      setCards(await results[0].json());
      setClients(await results[1].json());
      setJobs(await results[2].json());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load rate cards.");
    } finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);

  const eligibleJobs = useMemo(
    () => jobs.filter((job) => !form.client_id || !job.client_id || job.client_id === form.client_id),
    [jobs, form.client_id],
  );

  function setField<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    setMessage("");
    if (!form.client_id || !form.name.trim() || !form.effective_from) {
      setMessage("Select a client and provide a name and effective start date."); return;
    }
    if (form.rate_basis === "percentage_fee" ? !form.fee_percentage : !form.rate_amount) {
      setMessage("Enter the amount required by the selected rate basis."); return;
    }
    setSaving(true);
    try {
      const payload = {
        organization_id: org, client_id: form.client_id, job_id: form.job_id || null,
        name: form.name.trim(), employment_type: form.employment_type, rate_basis: form.rate_basis,
        currency: form.currency,
        rate_amount: form.rate_basis === "percentage_fee" ? null : Number(form.rate_amount),
        fee_percentage: form.rate_basis === "percentage_fee" ? Number(form.fee_percentage) : null,
        effective_from: form.effective_from, effective_to: form.effective_to || null,
        status: "draft", notes: form.notes.trim() || null,
      };
      const response = await apiFetch(API_BASE + "/api/rate-cards", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to create rate card.");
      setForm({ ...blank, client_id: form.client_id, currency: form.currency, effective_from: new Date().toISOString().slice(0, 10) });
      setShowForm(false);
      setMessage("Draft rate-card version created.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create rate card.");
    } finally { setSaving(false); }
  }

  async function changeStatus(card: RateCard, status: RateCard["status"]) {
    setMessage("");
    try {
      const response = await apiFetch(API_BASE + "/api/rate-cards/" + card.id + "?organization_id=" + encodeURIComponent(org), {
        method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Unable to update rate-card status.");
      setCards((current) => current.map((item) => item.id === card.id ? body : item));
      setMessage("Rate-card status updated.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to update rate-card status."); }
  }

  function startNewVersion(card: RateCard) {
    setForm({
      ...blank, client_id: card.client_id, job_id: card.job_id || "", name: card.name,
      employment_type: card.employment_type, rate_basis: card.rate_basis, currency: card.currency,
      rate_amount: card.rate_amount == null ? "" : String(card.rate_amount),
      fee_percentage: card.fee_percentage == null ? "" : String(card.fee_percentage),
      effective_from: card.effective_to || new Date().toISOString().slice(0, 10),
      effective_to: "", notes: card.notes || "",
    });
    setShowForm(true);
    setMessage("Review the copied terms and save as a new version.");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <main className="p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/clients" className="text-sm text-gray-500 hover:underline">← Clients</Link>
          <p className="mt-4 text-xs font-semibold uppercase tracking-widest text-gray-500">Commercial management</p>
          <h1 className="mt-2 text-3xl font-semibold">Rate cards</h1>
          <p className="mt-2 max-w-2xl text-gray-600">Versioned client pricing for permanent, contract and temporary recruitment. Draft new terms instead of rewriting active commercial history.</p>
        </div>
        <button className="btn primary" onClick={() => { setShowForm((value) => !value); setMessage(""); }}>
          {showForm ? "Cancel" : "＋ New rate card"}
        </button>
      </div>

      {message && <div className="notice mt-5" role="status">{message}</div>}

      {showForm && <form className="card mt-6 grid gap-4 md:grid-cols-2" onSubmit={create}>
        <label>Client
          <select required value={form.client_id} onChange={(e) => { setField("client_id", e.target.value); setField("job_id", ""); }}>
            <option value="">Select client</option>{clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
          </select>
        </label>
        <label>Related job (optional)
          <select value={form.job_id} onChange={(e) => setField("job_id", e.target.value)}>
            <option value="">Client-wide rate card</option>{eligibleJobs.map((job) => <option key={job.id} value={job.id}>{job.title}</option>)}
          </select>
        </label>
        <label className="md:col-span-2">Rate-card name
          <input required minLength={2} maxLength={200} value={form.name} onChange={(e) => setField("name", e.target.value)} placeholder="e.g. Permanent placements — standard terms" />
        </label>
        <label>Recruitment type
          <select value={form.employment_type} onChange={(e) => setField("employment_type", e.target.value as Form["employment_type"])}>
            <option value="permanent">Permanent</option><option value="contract">Contract</option><option value="temporary">Temporary</option>
          </select>
        </label>
        <label>Rate basis
          <select value={form.rate_basis} onChange={(e) => {
            const basis = e.target.value as Form["rate_basis"];
            setField("rate_basis", basis);
            setField("rate_amount", basis === "percentage_fee" ? "" : form.rate_amount);
            setField("fee_percentage", basis === "percentage_fee" ? (form.fee_percentage || "15") : "");
          }}>
            {Object.entries(basisLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <label>Currency
          <select value={form.currency} onChange={(e) => setField("currency", e.target.value)}>
            <option>GBP</option><option>USD</option><option>INR</option><option>AUD</option><option>EUR</option>
          </select>
        </label>
        {form.rate_basis === "percentage_fee" ? <label>Fee percentage
          <input required type="number" min="0.01" max="100" step="0.01" value={form.fee_percentage} onChange={(e) => setField("fee_percentage", e.target.value)} />
        </label> : <label>{basisLabels[form.rate_basis]} ({form.currency})
          <input required type="number" min="0" step="0.01" value={form.rate_amount} onChange={(e) => setField("rate_amount", e.target.value)} />
        </label>}
        <label>Effective from
          <input required type="date" value={form.effective_from} onChange={(e) => setField("effective_from", e.target.value)} />
        </label>
        <label>Effective to (optional)
          <input type="date" min={form.effective_from} value={form.effective_to} onChange={(e) => setField("effective_to", e.target.value)} />
        </label>
        <label className="md:col-span-2">Internal notes
          <textarea rows={3} maxLength={5000} value={form.notes} onChange={(e) => setField("notes", e.target.value)} placeholder="Context for this commercial version" />
        </label>
        <div className="flex items-center gap-3 md:col-span-2">
          <button className="btn primary" disabled={saving}>{saving ? "Saving…" : "Save draft version"}</button>
          <span className="text-sm text-gray-500">New versions start as drafts and require explicit activation.</span>
        </div>
      </form>}

      <section className="mt-7">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Commercial terms</h2>
          <select aria-label="Filter rate cards by status" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All current records</option><option value="draft">Draft</option><option value="active">Active</option><option value="expired">Expired</option><option value="archived">Archived</option>
          </select>
        </div>
        {loading ? <p className="text-gray-500">Loading rate cards…</p> : filtered.length === 0 ? (
          <div className="card py-12 text-center"><h3 className="font-semibold">No rate cards yet</h3><p className="mt-2 text-sm text-gray-500">Create a draft to record your first client commercial terms.</p></div>
        ) : <div className="grid gap-4">
          {filtered.map((card) => <article key={card.id} className="card">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{card.name}</h3><span className="rounded-full bg-gray-100 px-2 py-1 text-xs">{card.status}</span><span className="text-xs text-gray-500">Version {card.version}</span></div>
                <p className="mt-2 text-sm text-gray-600">{clientMap.get(card.client_id) || "Client"}{card.job_id ? " · " + (jobMap.get(card.job_id) || "Related job") : " · Client-wide"} · {card.employment_type}</p>
                <p className="mt-2 text-lg font-semibold">{card.rate_basis === "percentage_fee" ? String(card.fee_percentage) + "%" : money(card.rate_amount, card.currency)} <span className="text-sm font-normal text-gray-500">{basisLabels[card.rate_basis]}</span></p>
                <p className="mt-1 text-sm text-gray-500">Effective {card.effective_from}{card.effective_to ? " to " + card.effective_to : " onward"} · {card.currency}</p>
                {card.notes && <p className="mt-2 whitespace-pre-wrap text-sm text-gray-600">{card.notes}</p>}
              </div>
              <div className="flex flex-wrap gap-2">
                {card.status === "draft" && <button className="btn" onClick={() => void changeStatus(card, "active")}>Activate</button>}
                {card.status === "active" && <button className="btn" onClick={() => void changeStatus(card, "expired")}>Mark expired</button>}
                {card.status !== "archived" && <button className="btn" onClick={() => void changeStatus(card, "archived")}>Archive</button>}
                <button className="btn" onClick={() => startNewVersion(card)}>New version</button>
              </div>
            </div>
          </article>)}
        </div>}
      </section>
    </main>
  );
}

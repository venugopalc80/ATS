"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, apiFetch } from "@/lib/api";

type Kind = "employment" | "education" | "certifications" | "languages";
type Field = { key: string; label: string; required?: boolean; type?: "date" | "textarea" | "checkbox" | "select" | "url"; options?: string[] };
type RecordRow = { id: string; created_at?: string; updated_at?: string; [key: string]: unknown };
type Draft = Record<string, string | boolean>;

const CONFIG: Record<Kind, { title: string; fields: Field[]; summary: string[] }> = {
  employment: {
    title: "Employment history",
    fields: [
      { key: "employer_name", label: "Employer", required: true },
      { key: "job_title", label: "Job title", required: true },
      { key: "location", label: "Location" },
      { key: "employment_type", label: "Employment type" },
      { key: "start_date", label: "Start date", type: "date" },
      { key: "end_date", label: "End date", type: "date" },
      { key: "is_current", label: "Current role", type: "checkbox" },
      { key: "description", label: "Description", type: "textarea" },
    ],
    summary: ["job_title", "employer_name", "start_date", "end_date"],
  },
  education: {
    title: "Education",
    fields: [
      { key: "institution_name", label: "Institution", required: true },
      { key: "qualification", label: "Qualification" },
      { key: "field_of_study", label: "Field of study" },
      { key: "start_date", label: "Start date", type: "date" },
      { key: "end_date", label: "End date", type: "date" },
      { key: "grade", label: "Grade" },
      { key: "description", label: "Description", type: "textarea" },
    ],
    summary: ["institution_name", "qualification", "field_of_study"],
  },
  certifications: {
    title: "Certifications",
    fields: [
      { key: "name", label: "Certification", required: true },
      { key: "issuing_organisation", label: "Issuing organisation" },
      { key: "credential_id", label: "Credential ID" },
      { key: "credential_url", label: "Credential URL", type: "url" },
      { key: "issued_on", label: "Issue date", type: "date" },
      { key: "expires_on", label: "Expiry date", type: "date" },
    ],
    summary: ["name", "issuing_organisation", "expires_on"],
  },
  languages: {
    title: "Languages",
    fields: [
      { key: "language", label: "Language", required: true },
      { key: "proficiency", label: "Proficiency", type: "select", options: ["basic", "conversational", "professional", "fluent", "native"] },
    ],
    summary: ["language", "proficiency"],
  },
};

function blankDraft(kind: Kind): Draft {
  return Object.fromEntries(CONFIG[kind].fields.map((field) => [field.key, field.type === "checkbox" ? false : ""]));
}

function draftFromRecord(kind: Kind, row: RecordRow): Draft {
  return Object.fromEntries(CONFIG[kind].fields.map((field) => {
    const value = row[field.key];
    return [field.key, field.type === "checkbox" ? Boolean(value) : value == null ? "" : field.type === "date" ? String(value).slice(0, 10) : String(value)];
  }));
}

function payloadFromDraft(kind: Kind, draft: Draft) {
  return Object.fromEntries(CONFIG[kind].fields.map((field) => {
    const value = draft[field.key];
    if (field.type === "checkbox") return [field.key, Boolean(value)];
    if (typeof value !== "string" || value.trim() === "") return [field.key, null];
    return [field.key, value.trim()];
  }));
}

export default function CandidateProfileRecords({ candidateId }: { candidateId: string }) {
  const [records, setRecords] = useState<Record<Kind, RecordRow[]>>({
    employment: [], education: [], certifications: [], languages: [],
  });
  const [activeKind, setActiveKind] = useState<Kind | null>(null);
  const [editing, setEditing] = useState<RecordRow | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const kinds: Kind[] = ["employment", "education", "certifications", "languages"];
      const responses = await Promise.all(kinds.map((kind) =>
        apiFetch(API_BASE + "/api/candidates/" + encodeURIComponent(candidateId) + "/profile/" + kind)
      ));
      const failed = responses.find((response) => !response.ok);
      if (failed) throw new Error(failed.status === 401 ? "Please sign in again to load profile records." : "Could not load all candidate profile records.");
      const values = await Promise.all(responses.map((response) => response.json() as Promise<RecordRow[]>));
      setRecords({ employment: values[0], education: values[1], certifications: values[2], languages: values[3] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load candidate profile records.");
    } finally {
      setLoading(false);
    }
  }, [candidateId]);

  useEffect(() => { void load(); }, [load]);

  const openNew = (kind: Kind) => {
    setActiveKind(kind);
    setEditing(null);
    setDraft(blankDraft(kind));
    setError("");
    setNotice("");
  };

  const openEdit = (kind: Kind, row: RecordRow) => {
    setActiveKind(kind);
    setEditing(row);
    setDraft(draftFromRecord(kind, row));
    setError("");
    setNotice("");
  };

  const closeForm = () => { setActiveKind(null); setEditing(null); setDraft({}); };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!activeKind) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const path = API_BASE + "/api/candidates/" + encodeURIComponent(candidateId) + "/profile/" + activeKind;
      const response = await apiFetch(editing ? path + "/" + encodeURIComponent(editing.id) : path, {
        method: editing ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadFromDraft(activeKind, draft)),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail || (response.status === 401 ? "Please sign in again." : "Could not save this profile record."));
      }
      closeForm();
      setNotice(editing ? "Profile record updated." : "Profile record added.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save this profile record.");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (kind: Kind, row: RecordRow) => {
    if (!window.confirm("Delete this " + CONFIG[kind].title.toLowerCase() + " record?")) return;
    setError("");
    setNotice("");
    try {
      const response = await apiFetch(API_BASE + "/api/candidates/" + encodeURIComponent(candidateId) + "/profile/" + kind + "/" + encodeURIComponent(row.id), { method: "DELETE" });
      if (!response.ok) throw new Error(response.status === 404 ? "This record was not found. Refresh and try again." : "Could not delete this profile record.");
      setNotice("Profile record deleted.");
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this profile record.");
    }
  };

  const kinds = useMemo(() => Object.keys(CONFIG) as Kind[], []);

  return (
    <section className="card mt-5" aria-labelledby="candidate-profile-records-title">
      <div className="card-head">
        <div>
          <div id="candidate-profile-records-title" className="card-title">Candidate profile details</div>
          <p className="muted-small mt-1">Employment, education, certifications and languages</p>
        </div>
      </div>
      {error && <p role="alert" className="notice mt-3">{error}</p>}
      {notice && <p role="status" className="mt-3 text-sm text-green-700">{notice}</p>}
      {loading ? <p className="mt-4 text-sm text-gray-500">Loading profile details…</p> : (
        <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2">
          {kinds.map((kind) => {
            const config = CONFIG[kind];
            const rows = records[kind];
            return (
              <div key={kind} className="rounded-xl border border-gray-200 p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">{config.title}</h3>
                  <button type="button" className="btn" onClick={() => openNew(kind)}>Add</button>
                </div>
                {rows.length === 0 ? <p className="mt-3 text-sm text-gray-500">No records added yet.</p> : (
                  <ul className="mt-3 space-y-3">
                    {rows.map((row) => (
                      <li key={row.id} className="border-t border-gray-100 pt-3">
                        <div className="font-medium">{String(row[config.summary[0]] ?? "Profile record")}</div>
                        <div className="mt-1 text-sm text-gray-600">
                          {config.summary.slice(1).map((key) => row[key] != null && row[key] !== "" ? String(row[key]).replaceAll("_", " ") : "").filter(Boolean).join(" · ")}
                          {kind === "employment" && row.is_current ? " · Current role" : ""}
                        </div>
                        <div className="mt-2 flex gap-3">
                          <button type="button" className="text-sm font-medium underline" onClick={() => openEdit(kind, row)}>Edit</button>
                          <button type="button" className="text-sm text-red-700 underline" onClick={() => void remove(kind, row)}>Delete</button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}
      {activeKind && (
        <form onSubmit={submit} className="mt-5 rounded-xl border border-gray-200 p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h3 className="font-semibold">{editing ? "Edit" : "Add"} {CONFIG[activeKind].title.toLowerCase()}</h3>
            <button type="button" className="text-sm underline" onClick={closeForm}>Cancel</button>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {CONFIG[activeKind].fields.map((field) => (
              <label key={field.key} className={field.type === "textarea" ? "md:col-span-2 block text-sm font-medium" : "block text-sm font-medium"}>
                {field.type === "checkbox" ? (
                  <span className="flex items-center gap-2">
                    <input type="checkbox" checked={Boolean(draft[field.key])} onChange={(event) => setDraft((old) => ({ ...old, [field.key]: event.target.checked }))} />
                    {field.label}
                  </span>
                ) : (
                  <>
                    {field.label}{field.required ? " *" : ""}
                    {field.type === "textarea" ? (
                      <textarea className="mt-1 w-full rounded-lg border border-gray-300 p-2" rows={3} required={field.required} value={String(draft[field.key] ?? "")} onChange={(event) => setDraft((old) => ({ ...old, [field.key]: event.target.value }))} />
                    ) : field.type === "select" ? (
                      <select className="mt-1 w-full rounded-lg border border-gray-300 bg-white p-2" value={String(draft[field.key] ?? "")} onChange={(event) => setDraft((old) => ({ ...old, [field.key]: event.target.value }))}>
                        <option value="">Select proficiency</option>
                        {field.options?.map((option) => <option key={option} value={option}>{option}</option>)}
                      </select>
                    ) : (
                      <input className="mt-1 w-full rounded-lg border border-gray-300 p-2" type={field.type === "date" ? "date" : field.type === "url" ? "url" : "text"} required={field.required} value={String(draft[field.key] ?? "")} onChange={(event) => setDraft((old) => ({ ...old, [field.key]: event.target.value }))} />
                    )}
                  </>
                )}
              </label>
            ))}
          </div>
          {activeKind === "employment" && Boolean(draft.is_current) && <p className="mt-2 text-sm text-gray-500">For a current role, leave the end date empty.</p>}
          <div className="mt-4 flex gap-3">
            <button type="submit" className="btn primary" disabled={saving}>{saving ? "Saving…" : editing ? "Save changes" : "Add record"}</button>
            <button type="button" className="btn" onClick={closeForm} disabled={saving}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}

"use client";

import { useState } from "react";
import { API_BASE, apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

type Preview = {
  batch_id: string;
  filename: string;
  total_rows: number;
  valid_rows: number;
  duplicate_rows: number;
  rejected_rows: number;
  column_mapping: Record<string, string>;
  message: string;
};
type CommitResult = {
  id: string;
  status: string;
  total_rows: number;
  imported_rows: number;
  duplicate_rows: number;
  rejected_rows: number;
};

export default function CandidateImportsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [mappingText, setMappingText] = useState("");
  const [duplicatePolicy, setDuplicatePolicy] = useState<"review" | "skip" | "allow">("review");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  async function previewImport() {
    const organizationId = getActiveOrganizationId();
    if (!API_BASE || !organizationId || !file) {
      setMessage("Choose a CSV file and confirm an active organisation.");
      return;
    }
    setLoading(true);
    setMessage("");
    setResult(null);
    setPreview(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const params = new URLSearchParams({ organization_id: organizationId });
      if (mappingText.trim()) {
        JSON.parse(mappingText);
        params.set("column_mapping", mappingText.trim());
      }
      const response = await apiFetch(`${API_BASE}/api/imports/preview?${params.toString()}`, {
        method: "POST",
        body: form,
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "CSV preview failed.");
      setPreview(body);
      setMessage(body.message || "Preview ready. No candidate records have been created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "CSV preview failed.");
    } finally {
      setLoading(false);
    }
  }

  async function commitImport() {
    const organizationId = getActiveOrganizationId();
    if (!preview || !organizationId) return;
    setLoading(true);
    setMessage("");
    try {
      const params = new URLSearchParams({
        organization_id: organizationId,
        duplicate_policy: duplicatePolicy,
      });
      const response = await apiFetch(`${API_BASE}/api/imports/${preview.batch_id}/commit?${params.toString()}`, {
        method: "POST",
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Import could not be committed.");
      setResult(body);
      setMessage("Import processing finished.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Import could not be committed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Section 4 · Candidate sourcing</p>
          <h1>Candidate CSV imports</h1>
          <p className="subtitle">Preview and validate candidate data before creating records. The current endpoint accepts CSV files up to 5 MB and 1,000 data rows.</p>
        </div>
      </header>
      {message && <div className="notice" role="status" style={{ marginBottom: 16 }}>{message}</div>}
      <section className="card" style={{ marginBottom: 20 }}>
        <div className="card-head"><span className="card-title">Upload and map columns</span></div>
        <div className="notice" style={{ marginBottom: 16 }}>
          Only import candidate data your organisation is authorised to process. Review the relevant privacy notice, processing purpose and retention requirements first. The current implementation stores row snapshots and a file checksum, not the original CSV bytes.
        </div>
        <label style={{ display: "block", marginBottom: 12 }}>CSV file
          <input type="file" accept=".csv,text/csv" onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setPreview(null);
            setResult(null);
          }} />
        </label>
        <label style={{ display: "block", marginBottom: 12 }}>Optional column mapping JSON
          <textarea value={mappingText} onChange={(event) => setMappingText(event.target.value)} rows={3}
            placeholder={'{"first_name":"Given Name","email":"Email Address","skills":"Skills"}'} />
        </label>
        <p className="muted-small">Without a mapping, AQERITH recognises common header names. A first-name column is required. Supported fields include names, email, phone, location, country code, current title, experience, skills and status.</p>
        <button className="btn primary" disabled={loading || !file} onClick={() => void previewImport()}>{loading ? "Validating…" : "Preview CSV"}</button>
      </section>

      {preview && (
        <section className="card" style={{ marginBottom: 20 }}>
          <div className="card-head"><span className="card-title">Import preview</span><span className="muted-small">{preview.filename}</span></div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: 12, marginBottom: 16 }}>
            <div><strong>{preview.total_rows}</strong><div className="muted-small">Rows detected</div></div>
            <div><strong>{preview.valid_rows}</strong><div className="muted-small">Valid rows</div></div>
            <div><strong>{preview.duplicate_rows}</strong><div className="muted-small">Potential duplicates</div></div>
            <div><strong>{preview.rejected_rows}</strong><div className="muted-small">Rejected rows</div></div>
          </div>
          <div style={{ marginBottom: 16 }}>
            <strong>Column mapping</strong>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(preview.column_mapping, null, 2)}</pre>
          </div>
          <label style={{ display: "block", marginBottom: 12 }}>Duplicate handling
            <select value={duplicatePolicy} onChange={(event) => setDuplicatePolicy(event.target.value as typeof duplicatePolicy)}>
              <option value="review">Review and skip duplicates</option>
              <option value="skip">Skip duplicates</option>
              <option value="allow">Explicitly allow duplicate candidates</option>
            </select>
          </label>
          <p className="muted-small">Importing duplicate rows can create separate candidate records. Use Allow only when you have reviewed and intentionally want that outcome.</p>
          <button className="btn primary" disabled={loading} onClick={() => void commitImport()}>{loading ? "Importing…" : "Commit import"}</button>
        </section>
      )}

      {result && (
        <section className="card">
          <div className="card-head"><span className="card-title">Import result</span></div>
          <p>Status: <strong>{result.status}</strong></p>
          <p>Imported: {result.imported_rows} of {result.total_rows}</p>
          <p>Duplicates: {result.duplicate_rows} · Rejected: {result.rejected_rows}</p>
          <button className="btn" onClick={() => { setFile(null); setPreview(null); setResult(null); setMappingText(""); }}>Start another import</button>
        </section>
      )}
    </main>
  );
}

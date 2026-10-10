"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";
type Document = { id: string; original_filename: string; content_type: string; file_size_bytes: number; created_at?: string | null };

export default function CandidateDocuments({ candidateId }: { candidateId: string }) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const org = typeof window !== "undefined" ? window.localStorage.getItem("talentos_active_org") || DEFAULT_ORG : DEFAULT_ORG;

  async function load() {
    if (!API_BASE || !org) { setMessage("API or organisation configuration is missing."); setLoading(false); return; }
    try {
      const response = await apiFetch(API_BASE + "/api/documents?organization_id=" + encodeURIComponent(org) + "&candidate_id=" + encodeURIComponent(candidateId));
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Could not load CV documents.");
      setDocuments(await response.json());
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not load documents."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [candidateId]);

  async function upload(file?: File) {
    if (!file || !org) return;
    setMessage("");
    if (file.size > 5 * 1024 * 1024) { setMessage("CV files must be 5 MB or smaller."); return; }
    if (!/\.(pdf|docx)$/i.test(file.name)) { setMessage("Choose a PDF or DOCX file."); return; }
    setUploading(true);
    try {
      const body = new FormData(); body.append("file", file);
      const response = await apiFetch(API_BASE + "/api/documents?organization_id=" + encodeURIComponent(org) + "&candidate_id=" + encodeURIComponent(candidateId), { method: "POST", body });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "CV upload failed.");
      setMessage("CV uploaded securely.");
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "CV upload failed."); }
    finally { setUploading(false); }
  }
  async function download(document: Document) {
    try {
      const response = await apiFetch(API_BASE + "/api/documents/" + document.id + "/download?organization_id=" + encodeURIComponent(org), { method: "POST" });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Could not create download link.");
      const result = await response.json();
      window.open(result.url, "_blank", "noopener,noreferrer");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Download failed."); }
  }

  return <section className="card mt-5">
    <div className="card-head"><span className="card-title">CV & documents</span><span className="muted-small">Private storage · PDF/DOCX · 5 MB max</span></div>
    <p className="muted-small mb-3">Files are private and downloads use short-lived links. Upload only documents you are authorised to process.</p>
    <label className="btn inline-flex cursor-pointer">{uploading ? "Uploading..." : "↑ Upload CV"}<input className="sr-only" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={uploading} onChange={(event) => { void upload(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>
    {message && <p className="notice mt-3">{message}</p>}
    {loading ? <p className="muted-small mt-3">Loading documents...</p> : documents.length ? <div className="mt-3 space-y-3">{documents.map((doc) => <div key={doc.id} className="flex flex-wrap items-center justify-between gap-3 border-b pb-3"><div><strong>{doc.original_filename}</strong><div className="muted-small">{(doc.file_size_bytes / 1024).toFixed(0)} KB · {doc.created_at ? new Date(doc.created_at).toLocaleString() : "Uploaded"}</div></div><button className="btn" onClick={() => void download(doc)}>Secure download</button></div>)}</div> : <p className="muted-small mt-3">No CV documents uploaded yet.</p>}
  </section>;
}

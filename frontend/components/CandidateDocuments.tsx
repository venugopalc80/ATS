"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";
type Document = { id: string; original_filename: string; content_type: string; file_size_bytes: number; created_at?: string | null };
type Preview = { filename: string; kind: "pdf" | "text"; url?: string; text?: string };

export default function CandidateDocuments({ candidateId }: { candidateId: string }) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const org = typeof window !== "undefined" ? window.localStorage.getItem("aqerith_active_org") || window.localStorage.getItem("talentos_active_org") || DEFAULT_ORG : DEFAULT_ORG;

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
  async function openPreview(document: Document) {
    setMessage("");
    setPreviewLoading(document.id);
    try {
      const response = await apiFetch(API_BASE + "/api/documents/" + document.id + "/preview?organization_id=" + encodeURIComponent(org), { method: "POST" });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Could not preview this CV.");
      const result = await response.json();
      setPreview({ filename: result.filename || document.original_filename, kind: result.kind, url: result.url, text: result.text });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not preview this CV.");
    } finally {
      setPreviewLoading(null);
    }
  }

  async function downloadDocument(document: Document) {
    try {
      const response = await apiFetch(API_BASE + "/api/documents/" + document.id + "/download?organization_id=" + encodeURIComponent(org), { method: "POST" });
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Could not create download link.");
      const result = await response.json();
      const link = window.document.createElement("a");
      link.href = result.url;
      link.download = document.original_filename;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.click();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Download failed.");
    }
  }

  return <section className="card mt-5">
    <div className="card-head"><span className="card-title">CV & documents</span><span className="muted-small">Private storage · PDF/DOCX · 5 MB max</span></div>
    <p className="muted-small mb-3">Files are private and downloads use short-lived links. Upload only documents you are authorised to process.</p>
    <label className="btn inline-flex cursor-pointer">{uploading ? "Uploading..." : "↑ Upload CV"}<input className="sr-only" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" disabled={uploading} onChange={(event) => { void upload(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>
    {message && <div className="notice mt-3" role="status"><p>{message}</p><button className="btn mt-2" type="button" onClick={() => { setLoading(true); void load(); }}>Retry loading CVs</button></div>}
    {loading ? <p className="muted-small mt-3">Loading documents...</p> : documents.length ? <div className="mt-3 space-y-3">{documents.map((doc) => <div key={doc.id} className="flex flex-wrap items-center justify-between gap-3 border-b pb-3"><div><strong>{doc.original_filename}</strong><div className="muted-small">{(doc.file_size_bytes / 1024).toFixed(0)} KB · {doc.created_at ? new Date(doc.created_at).toLocaleString() : "Uploaded"}</div></div><div className="flex items-center gap-2"><button className="btn" type="button" aria-label={"Preview " + doc.original_filename} title="Preview CV" disabled={previewLoading === doc.id} onClick={() => void openPreview(doc)}><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M7 4h3l2 5 2-5h3l2 5v9a2 2 0 0 1-2 2h-2l-3-5-3 5H7a2 2 0 0 1-2-2V9z"/><circle cx="8.5" cy="13" r="2.5"/><circle cx="15.5" cy="13" r="2.5"/></svg> {previewLoading === doc.id ? "Opening..." : "Preview"}</button><button className="btn" type="button" onClick={() => void downloadDocument(doc)}>Download</button></div></div>)}</div> : <p className="muted-small mt-3">No CV documents uploaded yet.</p>}
    {preview && <div role="dialog" aria-modal="true" aria-label={"CV preview: " + preview.filename} onClick={(event) => { if (event.target === event.currentTarget) setPreview(null); }} style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(15, 23, 42, 0.72)", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px" }}>
      <div className="card" style={{ width: "min(1100px, 96vw)", height: "min(88vh, 900px)", display: "flex", flexDirection: "column", padding: 0, overflow: "hidden" }}>
        <div className="card-head" style={{ padding: "16px 20px", borderBottom: "1px solid #e5e7eb", flexShrink: 0 }}>
          <span className="card-title">{preview.filename}</span>
          <button type="button" className="btn" onClick={() => setPreview(null)} aria-label="Close CV preview">Close ✕</button>
        </div>
        {preview.kind === "pdf" && preview.url
          ? <iframe title={"CV preview: " + preview.filename} src={preview.url} style={{ border: 0, width: "100%", height: "100%", background: "#f8fafc" }} />
          : <div style={{ overflowY: "auto", padding: "28px 36px", whiteSpace: "pre-wrap", lineHeight: 1.65, textAlign: "left" }}>{preview.text || "No readable text is available for this CV."}</div>}
      </div>
    </div>}
  </section>;
}

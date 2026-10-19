"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getActiveOrganizationId } from "@/lib/organization";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const DEFAULT_ORG = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";
type Document = { id: string; original_filename: string; content_type: string; file_size_bytes: number; created_at?: string | null };
type Preview = { filename: string; kind: "pdf" | "text"; url?: string; text?: string };
type EmploymentSuggestion = { employer_name: string; job_title: string; location?: string | null; employment_type?: string | null; start_date?: string | null; end_date?: string | null; is_current?: boolean; description?: string | null };
type EducationSuggestion = { institution_name: string; qualification?: string | null; field_of_study?: string | null; start_date?: string | null; end_date?: string | null; grade?: string | null; description?: string | null };
type CertificationSuggestion = { name: string; issuing_organisation?: string | null; credential_id?: string | null; credential_url?: string | null; issued_on?: string | null; expires_on?: string | null };
type LanguageSuggestion = { language: string; proficiency?: string | null };
type ProfileSuggestion = { first_name?: string | null; last_name?: string | null; email?: string | null; phone?: string | null; skills?: string[]; current_title?: string | null; location?: { city?: string | null; region?: string | null; country?: string | null } | null; links?: { type: string; url: string }[]; employment?: EmploymentSuggestion[]; education?: EducationSuggestion[]; certifications?: CertificationSuggestion[]; languages?: LanguageSuggestion[]; review_required?: boolean; ocr_required?: boolean };

export default function CandidateDocuments({ candidateId }: { candidateId: string }) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [profileSuggestion, setProfileSuggestion] = useState<ProfileSuggestion | null>(null);
  const [applyingProfile, setApplyingProfile] = useState(false);
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const org = getActiveOrganizationId(DEFAULT_ORG);

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
      const uploaded = await response.json() as { extracted_profile?: ProfileSuggestion | null };
      // Always open the review panel after a successful upload. Older API deployments or
      // unexpected response shapes must not make the extraction workflow silently disappear.
      const suggestion = uploaded.extracted_profile ?? {
        first_name: "",
        last_name: "",
        email: "",
        phone: "",
        current_title: "",
        location: { city: "", region: "", country: "" },
        links: [],
        skills: [],
        employment: [], education: [], certifications: [], languages: [],
        review_required: true,
        ocr_required: true,
      };
      setProfileSuggestion(suggestion);
      setMessage(!uploaded.extracted_profile
        ? "CV uploaded, but the API did not return extracted profile details. You can enter the details manually below; check the staging API deployment."
        : uploaded.extracted_profile.ocr_required
          ? "CV uploaded securely, but no selectable text was found. Review the CV manually or use OCR."
          : "CV uploaded securely. Review the extracted details below before applying them.");
      await load();
    } catch (error) { setMessage(error instanceof Error ? error.message : "CV upload failed."); }
    finally { setUploading(false); }
  }
  async function applyExtractedProfile() {
    if (!profileSuggestion || !API_BASE || !org) return;
    const suggestion = profileSuggestion;
    const confirmed = window.confirm("Apply the extracted values to this candidate? Existing values may be updated, so review the fields before continuing.");
    if (!confirmed) return;
    setApplyingProfile(true);
    setMessage("");
    try {
      const payload: Record<string, unknown> = {};
      if (suggestion.first_name) payload.first_name = suggestion.first_name;
      if (suggestion.last_name) payload.last_name = suggestion.last_name;
      if (suggestion.email) payload.email = suggestion.email;
      if (suggestion.phone) payload.phone = suggestion.phone;
      if (suggestion.current_title) payload.current_title = suggestion.current_title;
      if (suggestion.location?.city) payload.city = suggestion.location.city;
      if (suggestion.location?.region) payload.region = suggestion.location.region;
      const countryCodes: Record<string, string> = {
        "united kingdom": "GB", "uk": "GB", "great britain": "GB",
        "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
        "india": "IN", "australia": "AU", "united states": "US",
        "united states of america": "US", "usa": "US",
      };
      const country = suggestion.location?.country?.trim().toLowerCase();
      if (country && countryCodes[country]) payload.country_code = countryCodes[country];
      if (suggestion.skills) payload.skills = suggestion.skills;
      if (suggestion.links) payload.profile_links = suggestion.links;
      const structuredCount = (suggestion.employment?.length || 0) + (suggestion.education?.length || 0) + (suggestion.certifications?.length || 0) + (suggestion.languages?.length || 0);
      if (!Object.keys(payload).length && !structuredCount) throw new Error("No profile fields could be extracted. This CV may need manual review or OCR.");
      if (Object.keys(payload).length) {
        const response = await apiFetch(API_BASE + "/api/candidates/" + encodeURIComponent(candidateId), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Could not update candidate profile.");
      }
      const profilePath = API_BASE + "/api/candidates/" + encodeURIComponent(candidateId) + "/profile/";
      const saveRows = async (kind: string, rows: Array<Record<string, unknown>>, required: string[]) => {
        for (const row of rows) {
          if (required.some((key) => !String(row[key] ?? "").trim())) continue;
          const response = await apiFetch(profilePath + kind, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(row) });
          if (!response.ok) {
            const body = await response.json().catch(() => null) as { detail?: string } | null;
            throw new Error(body?.detail || "Some profile details could not be saved. Refresh the profile and check for partial results.");
          }
        }
      };
      await saveRows("employment", (suggestion.employment || []) as unknown as Array<Record<string, unknown>>, ["employer_name", "job_title"]);
      await saveRows("education", (suggestion.education || []) as unknown as Array<Record<string, unknown>>, ["institution_name"]);
      await saveRows("certifications", (suggestion.certifications || []) as unknown as Array<Record<string, unknown>>, ["name"]);
      await saveRows("languages", (suggestion.languages || []) as unknown as Array<Record<string, unknown>>, ["language"]);
      setMessage("Reviewed CV details applied. Candidate profile and supported profile sections have been updated.");
      window.location.reload();
      setProfileSuggestion(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not apply extracted details.");
    } finally {
      setApplyingProfile(false);
    }
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

  async function deleteDocument(document: Document) {
    const confirmed = window.confirm(
      "Delete " + document.original_filename + "? This removes the document from this candidate's profile and starts private-storage cleanup."
    );
    if (!confirmed) return;
    setMessage("");
    setDeleting(document.id);
    try {
      const response = await apiFetch(
        API_BASE + "/api/documents/" + encodeURIComponent(document.id) + "?organization_id=" + encodeURIComponent(org),
        { method: "DELETE" }
      );
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail || "Could not delete this CV.");
      }
      if (preview?.filename === document.original_filename) setPreview(null);
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      setMessage("CV deleted. Private-storage cleanup was requested.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "CV deletion failed.");
      await load();
    } finally {
      setDeleting(null);
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
    {profileSuggestion && <div className="card mt-4" style={{ border: "1px solid #93c5fd" }}>
      <div className="card-head"><span className="card-title">Review extracted CV details</span><span className="muted-small">Please verify before applying</span></div>
      {profileSuggestion.ocr_required && <p className="notice mt-2">No selectable text was found. This may be a scanned CV and needs OCR or manual entry.</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        {([["first_name","First name"],["last_name","Last name"],["email","Email"],["phone","Phone"],["current_title","Current role"]] as const).map(([key,label]) => <label key={key} className="block text-sm">{label}<input className="input mt-1 w-full" value={(profileSuggestion[key] as string) || ""} onChange={(event) => setProfileSuggestion((current) => current ? { ...current, [key]: event.target.value } : current)} /></label>)}
        <label className="block text-sm">City<input className="input mt-1 w-full" value={profileSuggestion.location?.city || ""} onChange={(event) => setProfileSuggestion((current) => current ? { ...current, location: { ...current.location, city: event.target.value } } : current)} /></label>
        <label className="block text-sm">Region<input className="input mt-1 w-full" value={profileSuggestion.location?.region || ""} onChange={(event) => setProfileSuggestion((current) => current ? { ...current, location: { ...current.location, region: event.target.value } } : current)} /></label>
        <label className="block text-sm">Country<input className="input mt-1 w-full" value={profileSuggestion.location?.country || ""} onChange={(event) => setProfileSuggestion((current) => current ? { ...current, location: { ...current.location, country: event.target.value } } : current)} /></label>
      </div>
      <label className="block text-sm mt-3">Skills (comma-separated)
        <textarea className="input mt-1 w-full" rows={3} value={(profileSuggestion.skills || []).join(", ")} onChange={(event) => setProfileSuggestion((current) => current ? { ...current, skills: event.target.value.split(",").map((skill) => skill.trim()).filter(Boolean).slice(0, 30) } : current)} />
      </label>
      <div className="mt-3">
        <div className="flex items-center justify-between gap-2"><strong>Professional links</strong><button className="btn" type="button" disabled={(profileSuggestion.links || []).length >= 20} onClick={() => setProfileSuggestion((current) => current ? { ...current, links: [...(current.links || []), { type: "portfolio", url: "https://" }] } : current)}>Add link</button></div>
        {(profileSuggestion.links || []).map((link, index) => <div key={index} className="grid grid-cols-1 md:grid-cols-[140px_1fr_auto] gap-2 mt-2">
          <select className="input w-full" aria-label={"Link type " + (index + 1)} value={link.type} onChange={(event) => setProfileSuggestion((current) => current ? { ...current, links: (current.links || []).map((item, i) => i === index ? { ...item, type: event.target.value } : item) } : current)}>
            <option value="linkedin">LinkedIn</option><option value="github">GitHub</option><option value="portfolio">Portfolio / Other</option>
          </select>
          <input className="input w-full" type="url" aria-label={"Link URL " + (index + 1)} value={link.url} onChange={(event) => setProfileSuggestion((current) => current ? { ...current, links: (current.links || []).map((item, i) => i === index ? { ...item, url: event.target.value } : item) } : current)} />
          <button className="btn" type="button" aria-label={"Remove link " + (index + 1)} onClick={() => setProfileSuggestion((current) => current ? { ...current, links: (current.links || []).filter((_, i) => i !== index) } : current)}>Remove</button>
        </div>)}
        <p className="muted-small mt-2">Review links carefully. Only valid HTTP or HTTPS links can be saved.</p>
      </div>
      <div className="flex gap-2 mt-4"><button className="btn" type="button" disabled={applyingProfile} onClick={() => void applyExtractedProfile()}>{applyingProfile ? "Applying..." : "Apply to candidate profile"}</button><button className="btn" type="button" disabled={applyingProfile} onClick={() => setProfileSuggestion(null)}>Dismiss</button></div>
    </div>}
    {loading ? <p className="muted-small mt-3">Loading documents...</p> : documents.length ? <div className="mt-3 space-y-3">{documents.map((doc) => <div key={doc.id} className="flex flex-wrap items-center justify-between gap-3 border-b pb-3"><div><strong>{doc.original_filename}</strong><div className="muted-small">{(doc.file_size_bytes / 1024).toFixed(0)} KB · {doc.created_at ? new Date(doc.created_at).toLocaleString() : "Uploaded"}</div></div><div className="flex items-center gap-2"><button className="btn" type="button" aria-label={"Preview " + doc.original_filename} title="Preview CV" disabled={previewLoading === doc.id} onClick={() => void openPreview(doc)}><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M7 4h3l2 5 2-5h3l2 5v9a2 2 0 0 1-2 2h-2l-3-5-3 5H7a2 2 0 0 1-2-2V9z"/><circle cx="8.5" cy="13" r="2.5"/><circle cx="15.5" cy="13" r="2.5"/></svg> {previewLoading === doc.id ? "Opening..." : "Preview"}</button><button className="btn" type="button" onClick={() => void downloadDocument(doc)}>Download</button><button className="btn" type="button" aria-label={"Delete " + doc.original_filename} disabled={deleting === doc.id} onClick={() => void deleteDocument(doc)}>{deleting === doc.id ? "Deleting..." : "Delete"}</button></div></div>)}</div> : <p className="muted-small mt-3">No CV documents uploaded yet.</p>}
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

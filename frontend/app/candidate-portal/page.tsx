"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { supabase } from "@/lib/supabase";

type Profile = {
  first_name: string;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  city?: string | null;
  region?: string | null;
  country_code?: string | null;
  current_title?: string | null;
  years_experience?: number | null;
  skills?: string[];
};
type Application = {
  id: string;
  status: string;
  created_at: string;
  updated_at?: string;
  job_title: string;
  location?: string | null;
  country_code?: string | null;
  employment_type?: string | null;
  work_mode?: string | null;
};
type CandidateDocument = {
  id: string;
  document_type: string;
  original_filename: string;
  content_type: string;
  file_size_bytes: number;
  created_at?: string;
};

export default function CandidatePortalPage() {
  const [organizationId, setOrganizationId] = useState(process.env.NEXT_PUBLIC_ORGANIZATION_ID || "");
  const [email, setEmail] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [signedIn, setSignedIn] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [applications, setApplications] = useState<Application[]>([]);
  const [documents, setDocuments] = useState<CandidateDocument[]>([]);
  const [downloading, setDownloading] = useState<string | null>(null);

  const loadPortal = useCallback(async () => {
    if (!organizationId || !API_BASE) {
      setNotice("The candidate portal is not configured for this careers site.");
      setLoading(false);
      return;
    }
    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    if (!data.session) {
      setSignedIn(false);
      setLoading(false);
      return;
    }
    setSignedIn(true);
    const headers = { Authorization: "Bearer " + data.session.access_token };
    const base = API_BASE + "/api/candidate-portal";
    const linkResponse = await fetch(base + "/link?organization_id=" + encodeURIComponent(organizationId), {
      method: "POST", headers,
    });
    if (!linkResponse.ok) {
      const body = await linkResponse.json().catch(() => null);
      throw new Error(body?.detail || "We could not verify your candidate account.");
    }
    const [profileResponse, applicationsResponse, documentsResponse] = await Promise.all([
      fetch(base + "/me?organization_id=" + encodeURIComponent(organizationId), { headers }),
      fetch(base + "/applications?organization_id=" + encodeURIComponent(organizationId), { headers }),
      fetch(base + "/documents?organization_id=" + encodeURIComponent(organizationId), { headers }),
    ]);
    if (profileResponse.status === 404 || applicationsResponse.status === 404) {
      setProfile(null); setApplications([]); setDocuments([]);
      setNotice("We couldn't find a candidate application linked to this verified email for this organisation. Check that you used the email address on your application.");
      return;
    }
    if (!profileResponse.ok || !applicationsResponse.ok || !documentsResponse.ok) {
      throw new Error("Your portal information could not be loaded. Please try again.");
    }
    const [profileData, applicationData, documentData] = await Promise.all([
      profileResponse.json(), applicationsResponse.json(), documentsResponse.json(),
    ]);
    setProfile(profileData.profile);
    setApplications(applicationData.applications || []);
    setDocuments(documentData.documents || []);
    setNotice("");
  }, [organizationId]);

  useEffect(() => {
    const requestedOrganization = new URLSearchParams(window.location.search).get("organization_id");
    if (requestedOrganization) setOrganizationId(requestedOrganization);
  }, []);

  useEffect(() => {
    let active = true;
    async function initialise() {
      try {
        await loadPortal();
      } catch (error) {
        if (active) setNotice(error instanceof Error ? error.message : "Unable to load the candidate portal.");
      } finally {
        if (active) setLoading(false);
      }
    }
    void initialise();
    return () => { active = false; };
  }, [loadPortal]);

  async function requestSignIn(event: FormEvent) {
    event.preventDefault();
    if (!organizationId) {
      setNotice("This careers site has not supplied an organisation reference. Please return to the job page and use its candidate portal link.");
      return;
    }
    setBusy(true); setNotice("");
    try {
      const redirect = new URL("/candidate-portal", window.location.origin);
      redirect.searchParams.set("organization_id", organizationId);
      const { error } = await supabase.auth.signInWithOtp({
        email: email.trim().toLowerCase(),
        options: { emailRedirectTo: redirect.toString(), shouldCreateUser: true },
      });
      if (error) throw error;
      setNotice("Check your inbox for a secure sign-in link. Open it on this device to continue.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "We couldn't send your sign-in link.");
    } finally {
      setBusy(false);
    }
  }

  async function downloadDocument(document: CandidateDocument) {
    setDownloading(document.id); setNotice("");
    try {
      const { data, error } = await supabase.auth.getSession();
      if (error || !data.session) throw new Error("Your session has expired. Sign in again.");
      const response = await fetch(
        API_BASE + "/api/candidate-portal/documents/" + encodeURIComponent(document.id) +
        "/download?organization_id=" + encodeURIComponent(organizationId),
        { method: "POST", headers: { Authorization: "Bearer " + data.session.access_token } },
      );
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || "Unable to download this document.");
      const result = await response.json();
      window.location.assign(result.url);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to download this document.");
    } finally {
      setDownloading(null);
    }
  }

  async function signOut() {
    await supabase.auth.signOut();
    setSignedIn(false); setProfile(null); setApplications([]); setDocuments([]);
    setNotice("You have been signed out.");
  }

  return (
    <main className="candidate-portal-page">
      <header className="candidate-portal-header">
        <a href="/careers" className="candidate-portal-brand">AQERITH <span>CAREERS</span></a>
        {signedIn && <button type="button" className="candidate-portal-signout" onClick={signOut}>Sign out</button>}
      </header>
      <section className="candidate-portal-shell">
        <div className="candidate-portal-heading">
          <p className="careers-eyebrow">YOUR CANDIDATE SPACE</p>
          <h1>Stay connected to your applications.</h1>
          <p>Sign in securely to review your applications and access documents associated with them.</p>
        </div>
        {loading ? <div className="candidate-portal-panel"><p>Checking your secure session…</p></div> :
          !signedIn ? (
            <section className="candidate-portal-panel">
              <h2>Sign in with your email</h2>
              <p>We'll send you a one-time secure sign-in link. Use the same email address you provided when applying.</p>
              <form onSubmit={requestSignIn} className="candidate-portal-form">
                <label htmlFor="candidate-email">Email address</label>
                <input id="candidate-email" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} />
                <button type="submit" disabled={busy || !email.trim()}>{busy ? "Sending link…" : "Email me a sign-in link"}</button>
              </form>
            </section>
          ) : profile ? (
            <div className="candidate-portal-content">
              <section className="candidate-portal-panel candidate-portal-profile">
                <div><span className="candidate-portal-label">SIGNED IN AS</span><h2>{[profile.first_name, profile.last_name].filter(Boolean).join(" ")}</h2><p>{profile.email}</p></div>
                <div className="candidate-portal-profile-meta">{[profile.current_title, profile.city, profile.country_code].filter(Boolean).join(" · ")}</div>
              </section>
              <section className="candidate-portal-panel">
                <div className="candidate-portal-section-heading"><div><span className="candidate-portal-label">APPLICATION TRACKER</span><h2>Your applications</h2></div><span>{applications.length} total</span></div>
                {applications.length ? <div className="candidate-portal-list">{applications.map(application => (
                  <article className="candidate-portal-application" key={application.id}>
                    <div><h3>{application.job_title}</h3><p>{[application.location, application.work_mode, application.employment_type].filter(Boolean).join(" · ") || "Application received"}</p><small>Applied {new Date(application.created_at).toLocaleDateString()}</small></div>
                    <span className="candidate-portal-status">{application.status.replace(/_/g, " ")}</span>
                  </article>
                ))}</div> : <p className="candidate-portal-empty">No applications are currently linked to this account.</p>}
              </section>
              <section className="candidate-portal-panel">
                <div className="candidate-portal-section-heading"><div><span className="candidate-portal-label">YOUR FILES</span><h2>Documents</h2></div><span>{documents.length} files</span></div>
                {documents.length ? <div className="candidate-portal-list">{documents.map(document => (
                  <article className="candidate-portal-document" key={document.id}>
                    <div><strong>{document.original_filename}</strong><p>{document.document_type.replace(/_/g, " ")} · {(document.file_size_bytes / 1024).toFixed(0)} KB</p></div>
                    <button type="button" disabled={downloading === document.id} onClick={() => void downloadDocument(document)}>{downloading === document.id ? "Preparing…" : "Download"}</button>
                  </article>
                ))}</div> : <p className="candidate-portal-empty">No documents are available yet.</p>}
              </section>
            </div>
          ) : <section className="candidate-portal-panel"><h2>We couldn't match your application</h2><p>Use the verified email address you entered when applying. If the issue continues, contact the recruitment team.</p><button type="button" className="candidate-portal-secondary" onClick={signOut}>Sign out and try another email</button></section>
        }
        {notice && <div className="candidate-portal-notice" role="status">{notice}</div>}
        <p className="candidate-portal-footnote">Your information is shown only to your authenticated account. Application decisions remain with the recruiting organisation.</p>
      </section>
      <footer className="careers-footer">Powered by AQERITH · Recruitment, made clearer.</footer>
    </main>
  );
}

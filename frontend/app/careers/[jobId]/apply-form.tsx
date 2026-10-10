"use client";

import { FormEvent, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
const ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

export default function PublicApplyForm({ jobId }: { jobId: string }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const params = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
    const source = params.get("utm_source") || params.get("source") || "careers_page";
    try {
      const response = await fetch(`${API_BASE}/api/public/jobs/${encodeURIComponent(jobId)}/applications?organization_id=${encodeURIComponent(ORGANIZATION_ID)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: String(form.get("first_name") || "").trim(),
          last_name: String(form.get("last_name") || "").trim(),
          email: String(form.get("email") || "").trim(),
          phone: String(form.get("phone") || "").trim() || null,
          consent: form.get("consent") === "on",
          source,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || "We couldn't submit your application. Please try again.");
      setSuccess(true);
      setMessage("Application received. Thank you for your interest.");
      formElement.reset();
    } catch (error) {
      setSuccess(false);
      setMessage(error instanceof Error ? error.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="public-apply" aria-labelledby="apply-title">
      <h2 id="apply-title">Apply for this role</h2>
      <p>Share your details to submit your application to the recruitment team.</p>
      <form className="public-apply-form" onSubmit={submit}>
        <div className="public-apply-fields">
          <label>First name<input name="first_name" autoComplete="given-name" maxLength={100} required /></label>
          <label>Last name<input name="last_name" autoComplete="family-name" maxLength={100} /></label>
          <label>Email address<input name="email" type="email" autoComplete="email" maxLength={320} required /></label>
          <label>Phone (optional)<input name="phone" type="tel" autoComplete="tel" maxLength={50} /></label>
        </div>
        <label className="public-consent">
          <input type="checkbox" name="consent" required />
          <span>I agree that my details may be processed to assess this application and contact me about this role. Read the <a href="/careers/privacy" target="_blank" rel="noreferrer">applicant privacy notice</a>. I understand I can request access or deletion subject to applicable legal requirements.</span>
        </label>
        <button className="public-apply-button" type="submit" disabled={busy}>{busy ? "Submitting…" : "Submit application"}</button>
        {message ? <p role="status" className={success ? "public-apply-message success" : "public-apply-message"}>{message}</p> : null}
        <p className="public-privacy-note">Please submit only information relevant to this application. Please read the privacy notice before submitting. Resume upload is not enabled yet.</p>
      </form>
    </section>
  );
}

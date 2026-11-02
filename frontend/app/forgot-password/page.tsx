"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    setErrorMessage("");

    try {
      const redirectTo = new URL("/reset-password", window.location.origin).toString();
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo });
      if (error) throw error;
      setMessage("If an account exists for that email address, a password reset link will be sent. Please check your inbox and spam folder.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "We couldn't request a password reset. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand-lockup">
          <div className="auth-brand-wordmark">AQERITH</div>
          <div className="auth-tagline">THE INTELLIGENCE OF HUMAN POTENTIAL</div>
        </div>
        <div className="eyebrow">Account recovery</div>
        <h1>Reset your password</h1>
        <p className="subtitle">Enter the email address associated with your AQERITH workspace. We'll send you a secure reset link.</p>
        <form onSubmit={submit} className="auth-form">
          <label>Email<input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          <button className="btn primary auth-submit" disabled={busy}>{busy ? "Sending..." : "Send reset link"}</button>
        </form>
        {message && <div className="notice" role="status">{message}</div>}
        {errorMessage && <div className="notice" role="alert">{errorMessage}</div>}
        <Link href="/login" className="auth-switch">Back to sign in</Link>
      </section>
    </main>
  );
}

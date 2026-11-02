"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    supabase.auth.getSession().then(({ data, error }) => {
      if (!active) return;
      if (error || !data.session) {
        setErrorMessage("This reset link is invalid or has expired. Please request a new password reset link.");
      }
      setSessionReady(true);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (!active) return;
      if (event === "PASSWORD_RECOVERY" && session) {
        setErrorMessage("");
        setSessionReady(true);
      }
    });
    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setErrorMessage("");
    if (password.length < 8) {
      setErrorMessage("Your password must contain at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMessage("The passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      const { data } = await supabase.auth.getSession();
      if (!data.session) throw new Error("Your reset session has expired. Please request a new reset link.");
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      setMessage("Your password has been updated. You can now sign in with your new password.");
      setPassword("");
      setConfirmPassword("");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "We couldn't update your password. Please request a new reset link.");
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
        <div className="eyebrow">Secure account recovery</div>
        <h1>Choose a new password</h1>
        <p className="subtitle">Use at least 8 characters. Choose a password you haven't used before.</p>
        {sessionReady && !errorMessage && !message && (
          <form onSubmit={submit} className="auth-form">
            <label>New password<input required minLength={8} type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
            <label>Confirm new password<input required minLength={8} type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
            <button className="btn primary auth-submit" disabled={busy}>{busy ? "Updating..." : "Update password"}</button>
          </form>
        )}
        {message && <div className="notice" role="status">{message}</div>}
        {errorMessage && <div className="notice" role="alert">{errorMessage}</div>}
        {(message || errorMessage) && <Link href="/login" className="auth-switch">Back to sign in</Link>}
      </section>
    </main>
  );
}

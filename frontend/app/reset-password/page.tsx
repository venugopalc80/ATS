"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [success, setSuccess] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    if (password !== confirmPassword) {
      setMessage("The passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      setSuccess(true);
      setMessage("Your password has been updated. You can now sign in with your new password.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "This reset link may have expired. Request a new one from the sign-in page.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand-wordmark">AQERITH</div>
        <div className="auth-tagline">THE INTELLIGENCE OF HUMAN POTENTIAL</div>
        <div className="eyebrow">Account security</div>
        <h1>Choose a new password</h1>
        <p className="subtitle">Use at least 8 characters. Choose a password you have not used elsewhere.</p>
        <form onSubmit={submit} className="auth-form">
          <label>New password
            <span className="auth-password-control">
              <input required minLength={8} type={showPassword ? "text" : "password"} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
              <button type="button" className="auth-password-toggle" onClick={() => setShowPassword((value) => !value)}>{showPassword ? "Hide" : "Show"}</button>
            </span>
          </label>
          <label>Confirm new password<input required minLength={8} type={showPassword ? "text" : "password"} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
          <button className="btn primary auth-submit" disabled={busy || success}>{busy ? "Updating..." : "Update password"}</button>
        </form>
        {message && <div className={success ? "notice" : "dashboard-error"} role={success ? "status" : "alert"}>{message}</div>}
        {success && <button className="btn primary auth-submit" onClick={() => router.replace("/login")}>Return to sign in</button>}
      </section>
    </main>
  );
}

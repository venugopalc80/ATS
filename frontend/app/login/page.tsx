"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error">("success");
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendAvailableAt, setResendAvailableAt] = useState(0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");

    try {
      if (mode === "signup") {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { full_name: name } },
        });
        if (error) throw error;

        if (!data.session) {
          setMessageType("success");
          setMessage("Account created. Check your inbox for the confirmation email. If it doesn't arrive, use Resend confirmation email below.");
        } else {
          router.replace("/onboarding");
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.replace("/dashboard");
      }
    } catch (error) {
      setMessageType("error");
      setMessage(error instanceof Error ? error.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  async function resendConfirmation() {
    if (!email.trim()) {
      setMessageType("error");
      setMessage("Enter your email address first, then request another confirmation email.");
      return;
    }
    if (Date.now() < resendAvailableAt) {\n      const seconds = Math.ceil((resendAvailableAt - Date.now()) / 1000);\n      setMessageType("error");\n      setMessage(`Please wait ${seconds} seconds before requesting another email.`);\n      return;\n    }

    setResending(true);
    setMessage("");
    try {
      const { error } = await supabase.auth.resend({ type: "signup", email: email.trim() });
      if (error) throw error;
      setResendAvailableAt(Date.now() + 60000);
      setMessageType("success");
      setMessage("If this address has an account awaiting confirmation, a new confirmation email has been requested. Check your inbox and spam folder.");
    } catch (error) {
      setMessageType("error");
      setMessage(error instanceof Error ? error.message : "Unable to request a confirmation email. Please try again later.");
    } finally {
      setResending(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand-lockup" aria-label="AQERITH — The Intelligence of Human Potential">
          <svg className="auth-brand-symbol" viewBox="0 0 240 160" role="img" aria-label="AQERITH people symbol">
            <defs>
              <linearGradient id="aqerith-blue" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#00C8F5" />
                <stop offset="48%" stopColor="#086BFF" />
                <stop offset="100%" stopColor="#A348FF" />
              </linearGradient>
              <linearGradient id="aqerith-orange" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#FFC400" />
                <stop offset="60%" stopColor="#FF7915" />
                <stop offset="100%" stopColor="#FF4B23" />
              </linearGradient>
              <linearGradient id="aqerith-overlap" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#7A35FF" />
                <stop offset="100%" stopColor="#E12D9B" />
              </linearGradient>
            </defs>
            <circle cx="69" cy="28" r="22" fill="url(#aqerith-blue)" />
            <circle cx="171" cy="28" r="22" fill="url(#aqerith-orange)" />
            <path d="M16 137 C30 112 39 78 61 72 C80 66 101 83 120 101 C139 83 160 66 179 72 C201 78 210 112 224 137 C207 151 181 150 164 137 C148 125 138 103 120 101 C102 103 92 125 76 137 C59 150 33 151 16 137Z" fill="url(#aqerith-blue)" />
            <path d="M120 101 C139 83 160 66 179 72 C201 78 210 112 224 137 C207 151 181 150 164 137 C148 125 138 103 120 101Z" fill="url(#aqerith-orange)" />
            <path d="M120 101 C102 83 80 66 61 72 C80 75 99 90 120 115 C141 90 160 75 179 72 C160 66 139 83 120 101Z" fill="url(#aqerith-overlap)" opacity=".92" />
          </svg>
          <div className="auth-brand-wordmark">AQERITH</div>
          <div className="auth-tagline">THE INTELLIGENCE OF HUMAN POTENTIAL</div>
        </div>
        <div className="eyebrow">Recruitment intelligence</div>
        <h1>{mode === "signin" ? "Welcome back" : "Create your workspace"}</h1>
        <p className="subtitle">
          {mode === "signin" ? "Sign in to your AQERITH workspace." : "Start your recruitment workspace in minutes."}
        </p>

        <form onSubmit={submit} className="auth-form">
          {mode === "signup" && <label>Full name<input required value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>}
          <label>Email<input required type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>
            Password
            <span className="auth-password-control">
              <input required minLength={8} type={showPassword ? "text" : "password"} autoComplete={mode === "signin" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="button" className="auth-password-toggle" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </span>
          </label>
          <button className="btn primary auth-submit" disabled={busy}>{busy ? "Please wait..." : mode === "signin" ? "Sign in" : "Create account"}</button>
        </form>

        {message && <div className={messageType === "error" ? "dashboard-error" : "notice"} role={messageType === "error" ? "alert" : "status"}>{message}</div>}

        {mode === "signin" && (
          <div className="auth-recovery-actions">
            <button type="button" className="auth-switch" onClick={resendConfirmation} disabled={resending}>
              {resending ? "Requesting email..." : "Resend confirmation email"}
            </button>
            <p className="muted-small">Use the email address entered above. Check your spam folder if the message is missing.</p>
          </div>
        )}

        <button type="button" className="auth-switch" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setMessage(""); setShowPassword(false); }}>
          {mode === "signin" ? "Need an account? Create one" : "Already have an account? Sign in"}
        </button>
      </section>
    </main>
  );
}

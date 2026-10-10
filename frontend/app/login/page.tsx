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
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

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
          setMessage("Account created. Check your email to confirm your account, then sign in.");
        } else {
          router.replace("/onboarding");
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        router.replace("/");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed.");
    } finally {
      setBusy(false);
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
          {mode === "signup" && <label>Full name<input required value={name} onChange={(e) => setName(e.target.value)} /></label>}
          <label>Email<input required type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Password<input required minLength={8} type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          <button className="btn primary auth-submit" disabled={busy}>{busy ? "Please wait..." : mode === "signin" ? "Sign in" : "Create account"}</button>
        </form>

        {message && <div className="notice" role="status">{message}</div>}

        <button type="button" className="auth-switch" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setMessage(""); }}>
          {mode === "signin" ? "Need an account? Create one" : "Already have an account? Sign in"}
        </button>
      </section>
    </main>
  );
}

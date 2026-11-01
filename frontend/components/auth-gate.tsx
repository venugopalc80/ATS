"use client";

import { FormEvent, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiFetch, API_BASE } from "@/lib/api";
import { supabase } from "@/lib/supabase";

type MfaChallenge = {
  factorId: string;
  challengeId: string;
  factorLabel: string;
};

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [authError, setAuthError] = useState("");
  const [mfaChallenge, setMfaChallenge] = useState<MfaChallenge | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaError, setMfaError] = useState("");

  useEffect(() => {
    let active = true;
    const publicRoute =
      pathname === "/" ||
      pathname === "/login" ||
      pathname === "/careers" ||
      pathname.startsWith("/careers/");

    if (publicRoute) {
      setAuthorized(true);
      setReady(true);
      setAuthError("");
      setMfaChallenge(null);
      return () => { active = false; };
    }

    setReady(false);
    setAuthorized(false);
    setAuthError("");
    setMfaChallenge(null);
    setMfaError("");

    async function check() {
      try {
        const { data, error } = await supabase.auth.getSession();
        if (error) throw error;

        if (!data.session) {
          // Fail closed: never render a protected route without a session.
          if (active) window.location.replace("/login");
          return;
        }

        // If a verified factor is enrolled, require the second factor before
        // rendering any protected AQERITH route.
        const { data: assurance, error: assuranceError } =
          await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
        if (assuranceError) throw assuranceError;

        if (assurance.nextLevel === "aal2" && assurance.currentLevel !== "aal2") {
          const { data: factorData, error: factorsError } =
            await supabase.auth.mfa.listFactors();
          if (factorsError) throw factorsError;

          const factor = [
            ...factorData.totp.filter((item) => item.status === "verified"),
            ...factorData.phone.filter((item) => item.status === "verified"),
          ][0];

          if (!factor) {
            throw new Error("Multi-factor authentication is required, but no verified authenticator is available. Contact your administrator.");
          }

          const { data: challenge, error: challengeError } =
            await supabase.auth.mfa.challenge({ factorId: factor.id });
          if (challengeError) throw challengeError;

          if (active) {
            setMfaChallenge({
              factorId: factor.id,
              challengeId: challenge.id,
              factorLabel: factor.friendly_name || (factor.factor_type === "phone" ? "your phone" : "your authenticator app"),
            });
          }
          return;
        }

        if (!API_BASE) {
          throw new Error("The AQERITH API is not configured. Please try again later.");
        }

        const response = await apiFetch(API_BASE + "/api/me", {
          signal: AbortSignal.timeout(10000),
        });

        if (response.status === 401 || response.status === 403) {
          await supabase.auth.signOut();
          if (active) router.replace("/login");
          return;
        }

        if (!response.ok) {
          throw new Error("AQERITH could not verify your access (HTTP " + response.status + ").");
        }

        const context = await response.json();
        const firstOrg = context.organizations?.[0];

        if (!firstOrg && pathname !== "/onboarding") {
          if (active) router.replace("/onboarding");
          return;
        }

        if (firstOrg) {
          window.localStorage.setItem("aqerith_active_org", firstOrg.id);
          // Keep the legacy key aligned for older components.
          window.localStorage.setItem("talentos_active_org", firstOrg.id);
        }

        if (active) setAuthorized(true);
      } catch (error) {
        console.error("AQERITH auth check failed:", error);
        if (active) {
          setAuthError(error instanceof Error ? error.message : "Unable to verify your access.");
          setAuthorized(false);
        }
      } finally {
        if (active) setReady(true);
      }
    }

    void check();
    return () => { active = false; };
  }, [pathname, router]);

  async function verifySecondFactor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!mfaChallenge || !/^\d{6,8}$/.test(mfaCode.trim())) {
      setMfaError("Enter the current verification code from your authenticator.");
      return;
    }

    setMfaBusy(true);
    setMfaError("");
    try {
      const { error } = await supabase.auth.mfa.verify({
        factorId: mfaChallenge.factorId,
        challengeId: mfaChallenge.challengeId,
        code: mfaCode.trim(),
      });
      if (error) throw error;
      // Supabase refreshes the session after successful verification. Reload
      // so AuthGate repeats the assurance check before rendering the workspace.
      window.location.reload();
    } catch (error) {
      setMfaError(error instanceof Error ? error.message : "The verification code could not be confirmed.");
    } finally {
      setMfaBusy(false);
    }
  }

  if (!ready) {
    return <div className="auth-loading">Verifying AQERITH access...</div>;
  }

  if (mfaChallenge) {
    return (
      <main className="auth-loading" style={{ minHeight: "100vh", display: "grid", placeContent: "center", gap: 16, padding: 24, background: "#f5f7fb" }}>
        <section style={{ width: "min(100%, 440px)", background: "#fff", border: "1px solid #e2e8f0", borderRadius: 16, padding: 28, boxShadow: "0 18px 50px rgba(20, 38, 62, .08)" }}>
          <p style={{ margin: "0 0 8px", color: "#d36b32", fontSize: 11, fontWeight: 800, letterSpacing: ".14em" }}>ACCOUNT PROTECTION</p>
          <h1 style={{ margin: 0, color: "#182230", fontSize: 25 }}>Verify it’s you</h1>
          <p style={{ color: "#66758a", lineHeight: 1.6, fontSize: 14 }}>Enter the current code from {mfaChallenge.factorLabel} to continue to AQERITH.</p>
          {mfaError && <div role="alert" style={{ background: "#fff1f0", color: "#9d3028", padding: 11, borderRadius: 8, marginBottom: 12, fontSize: 13 }}>{mfaError}</div>}
          <form onSubmit={verifySecondFactor}>
            <label htmlFor="aqerith-mfa-code" style={{ display: "block", color: "#34445a", fontSize: 13, fontWeight: 700, marginBottom: 7 }}>Verification code</label>
            <input id="aqerith-mfa-code" autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={mfaCode} onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, "").slice(0, 8))} placeholder="Enter code" style={{ width: "100%", boxSizing: "border-box", border: "1px solid #d8e0e9", borderRadius: 9, padding: "12px 13px", fontSize: 18, letterSpacing: ".18em", color: "#182230" }} />
            <button type="submit" disabled={mfaBusy} style={{ width: "100%", marginTop: 14, border: 0, background: "#172b48", color: "#fff", borderRadius: 9, padding: 13, cursor: mfaBusy ? "wait" : "pointer", fontWeight: 800 }}>{mfaBusy ? "Verifying…" : "Verify and continue"}</button>
          </form>
          <button type="button" onClick={async () => { await supabase.auth.signOut(); window.location.replace("/login"); }} style={{ marginTop: 14, border: 0, background: "transparent", color: "#66758a", cursor: "pointer", fontSize: 13 }}>Sign out</button>
        </section>
      </main>
    );
  }

  if (!authorized) {
    return (
      <main className="auth-loading" role="alert" style={{ minHeight: "100vh", display: "grid", placeContent: "center", gap: 12, padding: 24 }}>
        <strong>AQERITH could not verify your access.</strong>
        <span>{authError || "Redirecting to sign in..."}</span>
        <button type="button" onClick={() => router.replace("/login")}>Return to sign in</button>
      </main>
    );
  }

  return <>{children}</>;
}

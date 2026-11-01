"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getSupabaseClient } from "@/lib/supabase";

type Factor = {
  id: string;
  friendly_name?: string | null;
  status: string;
  factor_type: string;
  created_at?: string;
};

type SetupFactor = {
  id: string;
  qrCode: string;
  secret: string;
  uri: string;
  friendlyName: string;
};

export default function SecurityPage() {
  const [factors, setFactors] = useState<Factor[]>([]);
  const [assurance, setAssurance] = useState({ current: "aal1", next: "aal1" });
  const [setup, setSetup] = useState<SetupFactor | null>(null);
  const [setupCode, setSetupCode] = useState("");
  const [removeFactor, setRemoveFactor] = useState<Factor | null>(null);
  const [removeChallengeId, setRemoveChallengeId] = useState("");
  const [removeCode, setRemoveCode] = useState("");
  const [friendlyName, setFriendlyName] = useState("My authenticator");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadSecurity = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const client = getSupabaseClient();
      const [factorResult, assuranceResult] = await Promise.all([
        client.auth.mfa.listFactors(),
        client.auth.mfa.getAuthenticatorAssuranceLevel(),
      ]);
      if (factorResult.error) throw factorResult.error;
      if (assuranceResult.error) throw assuranceResult.error;
      const allFactors = [
        ...factorResult.data.totp.map((factor) => ({ ...factor, factor_type: "totp" })),
        ...factorResult.data.phone.map((factor) => ({ ...factor, factor_type: "phone" })),
      ];
      setFactors(allFactors);
      setAssurance({
        current: assuranceResult.data.currentLevel ?? "aal1",
        next: assuranceResult.data.nextLevel ?? "aal1",
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load your security settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSecurity();
  }, [loadSecurity]);

  async function startEnrollment() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { data, error: enrollError } = await getSupabaseClient().auth.mfa.enroll({
        factorType: "totp",
        friendlyName: friendlyName.trim() || "My authenticator",
      });
      if (enrollError) throw enrollError;
      setSetup({
        id: data.id,
        qrCode: data.totp.qr_code,
        secret: data.totp.secret,
        uri: data.totp.uri,
        friendlyName: data.friendly_name ?? friendlyName.trim(),
      });
      setSetupCode("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start authenticator setup.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyEnrollment() {
    if (!setup || !/^\d{6,8}$/.test(setupCode.trim())) {
      setError("Enter the current verification code from your authenticator app.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const client = getSupabaseClient();
      const { data: challenge, error: challengeError } = await client.auth.mfa.challenge({
        factorId: setup.id,
      });
      if (challengeError) throw challengeError;
      const { error: verifyError } = await client.auth.mfa.verify({
        factorId: setup.id,
        challengeId: challenge.id,
        code: setupCode.trim(),
      });
      if (verifyError) throw verifyError;
      setSetup(null);
      setSetupCode("");
      setNotice("Two-factor authentication is now enabled for this account.");
      await loadSecurity();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The verification code could not be confirmed.");
    } finally {
      setBusy(false);
    }
  }

  async function signOutOtherSessions() {
    const confirmed = window.confirm("Sign out this AQERITH account from all other devices and browsers? This device will remain signed in.");
    if (!confirmed) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { error: signOutError } = await getSupabaseClient().auth.signOut({ scope: "others" });
      if (signOutError) throw signOutError;
      setNotice("Other refresh-token sessions have been revoked. Existing access tokens may remain valid until they expire.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Other sessions could not be revoked.");
    } finally {
      setBusy(false);
    }
  }

  async function beginRemoval(factor: Factor) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { data, error: challengeError } = await getSupabaseClient().auth.mfa.challenge({
        factorId: factor.id,
      });
      if (challengeError) throw challengeError;
      setRemoveFactor(factor);
      setRemoveChallengeId(data.id);
      setRemoveCode("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start factor removal.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmRemoval() {
    if (!removeFactor || !/^\d{6,8}$/.test(removeCode.trim())) {
      setError("Enter the current code from the authenticator you are removing.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const client = getSupabaseClient();
      const { error: verifyError } = await client.auth.mfa.verify({
        factorId: removeFactor.id,
        challengeId: removeChallengeId,
        code: removeCode.trim(),
      });
      if (verifyError) throw verifyError;
      const { error: unenrollError } = await client.auth.mfa.unenroll({
        factorId: removeFactor.id,
      });
      if (unenrollError) throw unenrollError;
      setRemoveFactor(null);
      setRemoveChallengeId("");
      setRemoveCode("");
      setNotice("Authenticator removed. Your account's assurance level may have changed.");
      await loadSecurity();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The authenticator could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  const verifiedFactors = factors.filter((factor) => factor.status === "verified");

  return (
    <main style={{ minHeight: "100vh", background: "#f5f7fb", color: "#182230", padding: "32px 20px 64px" }}>
      <div style={{ maxWidth: 1040, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap", marginBottom: 28 }}>
          <div>
            <Link href="/dashboard" style={{ color: "#52647a", textDecoration: "none", fontSize: 14 }}>← Back to dashboard</Link>
            <p style={{ margin: "20px 0 6px", color: "#d36b32", fontSize: 12, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase" }}>Account protection</p>
            <h1 style={{ margin: 0, fontSize: 32, letterSpacing: "-0.04em" }}>Security settings</h1>
            <p style={{ color: "#66758a", margin: "8px 0 0", maxWidth: 640, lineHeight: 1.6 }}>Manage the additional sign-in protection on your AQERITH account.</p>
          </div>
          <Link href="/dashboard" style={{ border: "1px solid #d9e0e9", background: "#fff", borderRadius: 10, padding: "10px 14px", color: "#34445a", textDecoration: "none", fontSize: 14, fontWeight: 700 }}>Workspace</Link>
        </div>

        {error && <div role="alert" style={{ background: "#fff1f0", border: "1px solid #f3c4bf", color: "#9d3028", borderRadius: 10, padding: 14, marginBottom: 16 }}>{error}</div>}
        {notice && <div role="status" style={{ background: "#eef8f2", border: "1px solid #c5e7d1", color: "#21643b", borderRadius: 10, padding: 14, marginBottom: 16 }}>{notice}</div>}

        <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14, marginBottom: 18 }}>
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14, padding: 20 }}>
            <p style={{ margin: 0, color: "#718096", fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em" }}>Current session</p>
            <strong style={{ display: "block", fontSize: 24, marginTop: 10 }}>{assurance.current.toUpperCase()}</strong>
            <p style={{ margin: "6px 0 0", color: "#66758a", fontSize: 13 }}>Verified assurance level for this sign-in.</p>
          </div>
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14, padding: 20 }}>
            <p style={{ margin: 0, color: "#718096", fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".08em" }}>Account factors</p>
            <strong style={{ display: "block", fontSize: 24, marginTop: 10 }}>{verifiedFactors.length} verified</strong>
            <p style={{ margin: "6px 0 0", color: "#66758a", fontSize: 13 }}>Registered second-factor authenticators.</p>
          </div>
        </section>

        <section style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14, padding: 22, marginBottom: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 19 }}>Two-factor authentication</h2>
              <p style={{ color: "#66758a", margin: "7px 0 0", lineHeight: 1.55, maxWidth: 650 }}>Use an authenticator app such as Google Authenticator, Microsoft Authenticator, 1Password or Apple Passwords to add a time-based verification code.</p>
            </div>
            <span style={{ borderRadius: 999, padding: "6px 10px", background: verifiedFactors.length ? "#eaf7ef" : "#fff4e8", color: verifiedFactors.length ? "#247342" : "#9a5a1b", fontSize: 12, fontWeight: 800 }}>{verifiedFactors.length ? "Protection enabled" : "Not enabled"}</span>
          </div>

          {loading ? <p style={{ color: "#66758a" }}>Loading security settings…</p> : (
            <div style={{ marginTop: 20 }}>
              {factors.length === 0 ? <p style={{ color: "#66758a", fontSize: 14 }}>No authenticator factors are registered yet.</p> : (
                <div style={{ display: "grid", gap: 10 }}>
                  {factors.map((factor) => (
                    <div key={factor.id} style={{ border: "1px solid #e7ebf1", borderRadius: 10, padding: 14, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                      <div>
                        <strong>{factor.friendly_name || (factor.factor_type === "totp" ? "Authenticator app" : "Phone factor")}</strong>
                        <p style={{ margin: "4px 0 0", color: "#718096", fontSize: 12 }}>{factor.factor_type.toUpperCase()} · {factor.status}</p>
                      </div>
                      <button type="button" disabled={busy || factor.status !== "verified"} onClick={() => void beginRemoval(factor)} style={{ border: "1px solid #e4c6c3", background: "#fff", color: "#a23d35", borderRadius: 8, padding: "8px 12px", cursor: "pointer", fontWeight: 700 }}>Remove</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!setup && !removeFactor && (
            <div style={{ marginTop: 22, borderTop: "1px solid #edf0f4", paddingTop: 18 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 700, marginBottom: 7 }} htmlFor="factor-name">Authenticator name</label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input id="factor-name" value={friendlyName} onChange={(event) => setFriendlyName(event.target.value)} maxLength={80} style={{ flex: "1 1 240px", minWidth: 0, border: "1px solid #d8e0e9", borderRadius: 9, padding: "11px 12px", color: "#182230" }} />
                <button type="button" disabled={busy} onClick={() => void startEnrollment()} style={{ border: 0, background: "#172b48", color: "#fff", borderRadius: 9, padding: "11px 16px", cursor: "pointer", fontWeight: 700 }}>{busy ? "Please wait…" : "Set up authenticator"}</button>
              </div>
            </div>
          )}

          {setup && (
            <div style={{ marginTop: 22, borderTop: "1px solid #edf0f4", paddingTop: 20 }}>
              <h3 style={{ margin: "0 0 8px", fontSize: 16 }}>Connect your authenticator</h3>
              <p style={{ color: "#66758a", fontSize: 14, lineHeight: 1.55 }}>Scan this QR code with your authenticator app. If scanning is unavailable, enter the setup key manually. This secret is shown only during setup.</p>
              <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: 12 }}>
                  <img src={"data:image/svg+xml;utf8," + encodeURIComponent(setup.qrCode)} alt="Authenticator setup QR code" width="190" height="190" />
                </div>
                <div style={{ flex: "1 1 280px" }}>
                  <p style={{ fontSize: 12, fontWeight: 800, color: "#66758a", textTransform: "uppercase", letterSpacing: ".08em" }}>Manual setup key</p>
                  <code style={{ display: "block", overflowWrap: "anywhere", background: "#f3f5f8", padding: 12, borderRadius: 8, fontSize: 13 }}>{setup.secret}</code>
                  <p style={{ color: "#8a5a21", fontSize: 12, lineHeight: 1.5 }}>Treat this key like a password. Do not share it or store it in an unsecured location.</p>
                </div>
              </div>
              <label htmlFor="setup-code" style={{ display: "block", fontSize: 13, fontWeight: 700, margin: "18px 0 7px" }}>6-digit verification code</label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input id="setup-code" inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={setupCode} onChange={(event) => setSetupCode(event.target.value.replace(/\D/g, "").slice(0, 8))} placeholder="Enter code" style={{ border: "1px solid #d8e0e9", borderRadius: 9, padding: "11px 12px", width: 180, color: "#182230" }} />
                <button type="button" disabled={busy} onClick={() => void verifyEnrollment()} style={{ border: 0, background: "#172b48", color: "#fff", borderRadius: 9, padding: "11px 16px", cursor: "pointer", fontWeight: 700 }}>Verify and enable</button>
                <button type="button" disabled={busy} onClick={() => { setSetup(null); setSetupCode(""); }} style={{ border: "1px solid #d8e0e9", background: "#fff", color: "#34445a", borderRadius: 9, padding: "11px 16px", cursor: "pointer" }}>Cancel</button>
              </div>
            </div>
          )}

          {removeFactor && (
            <div style={{ marginTop: 22, borderTop: "1px solid #edf0f4", paddingTop: 20 }}>
              <h3 style={{ margin: "0 0 8px", fontSize: 16 }}>Confirm authenticator removal</h3>
              <p style={{ color: "#66758a", fontSize: 14 }}>Enter a fresh code from <strong>{removeFactor.friendly_name || "this authenticator"}</strong> to verify your identity before removing it.</p>
              <label htmlFor="remove-code" style={{ display: "block", fontSize: 13, fontWeight: 700, marginBottom: 7 }}>Verification code</label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input id="remove-code" inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={removeCode} onChange={(event) => setRemoveCode(event.target.value.replace(/\D/g, "").slice(0, 8))} placeholder="Enter code" style={{ border: "1px solid #d8e0e9", borderRadius: 9, padding: "11px 12px", width: 180, color: "#182230" }} />
                <button type="button" disabled={busy} onClick={() => void confirmRemoval()} style={{ border: 0, background: "#a23d35", color: "#fff", borderRadius: 9, padding: "11px 16px", cursor: "pointer", fontWeight: 700 }}>Verify and remove</button>
                <button type="button" disabled={busy} onClick={() => { setRemoveFactor(null); setRemoveChallengeId(""); setRemoveCode(""); }} style={{ border: "1px solid #d8e0e9", background: "#fff", color: "#34445a", borderRadius: 9, padding: "11px 16px", cursor: "pointer" }}>Cancel</button>
              </div>
            </div>
          )}
        </section>

        <section style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14, padding: 22, marginBottom: 18 }}>
          <h2 style={{ margin: "0 0 8px", fontSize: 19 }}>Other signed-in devices</h2>
          <p style={{ margin: "0 0 16px", color: "#66758a", fontSize: 14, lineHeight: 1.6 }}>End other refresh-token sessions for this account while keeping this device signed in. Supabase does not expose a safe per-device session inventory through the current browser client, so AQERITH does not display guessed device or location details.</p>
          <button type="button" disabled={busy} onClick={() => void signOutOtherSessions()} style={{ border: "1px solid #e4c6c3", background: "#fff", color: "#a23d35", borderRadius: 9, padding: "10px 14px", cursor: "pointer", fontWeight: 700 }}>Sign out other sessions</button>
          <p style={{ margin: "10px 0 0", color: "#8a6b4c", fontSize: 12, lineHeight: 1.5 }}>Revoked refresh tokens stop future session renewal. Previously issued access tokens can remain valid until their short expiry unless the API checks the session identifier against the Auth session table.</p>
        </section>

        <section style={{ background: "#fffaf2", border: "1px solid #f1dfc4", borderRadius: 14, padding: 18 }}>
          <h2 style={{ margin: "0 0 8px", fontSize: 16, color: "#744a1d" }}>Recovery and account access</h2>
          <p style={{ margin: 0, color: "#775d3d", fontSize: 13, lineHeight: 1.6 }}>AQERITH currently uses Supabase Auth TOTP factors. Recovery codes are not provided by this MFA flow. For resilience, consider enrolling a second authenticator on a separate device and keep its access secure. Removing your only verified factor can reduce your account protection.</p>
        </section>
      </div>
    </main>
  );
}

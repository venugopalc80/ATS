"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, API_BASE } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function AcceptInvitationPage() {
  const router = useRouter();
  const [status, setStatus] = useState("Checking your invitation...");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function accept() {
      const params = new URLSearchParams(window.location.search);
      const invitationId = params.get("invitation_id");
      const token = params.get("token");

      if (!invitationId || !token) {
        if (active) {
          setError("This invitation link is incomplete. Ask your organisation administrator to send a new invitation.");
          setStatus("");
        }
        return;
      }

      try {
        const { data, error: sessionError } = await supabase.auth.getSession();
        if (sessionError) throw sessionError;
        if (!data.session) {
          throw new Error("The invitation link has not established a sign-in session. Open the link from your invitation email again, or sign in using the invited email address.");
        }

        const response = await apiFetch(API_BASE + "/api/me/invitations/accept", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ invitation_id: invitationId, token }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail || "We could not accept this invitation.");
        }

        const result = await response.json();
        window.localStorage.setItem("aqerith_active_org", result.organization.id);
        window.localStorage.setItem("talentos_active_org", result.organization.id);
        if (active) {
          setStatus("Invitation accepted. Opening your workspace...");
          router.replace("/dashboard");
        }
      } catch (err) {
        if (active) {
          setStatus("");
          setError(err instanceof Error ? err.message : "Unable to accept this invitation.");
        }
      }
    }

    void accept();
    return () => { active = false; };
  }, [router]);

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand-wordmark">AQERITH</div>
        <div className="auth-tagline">THE INTELLIGENCE OF HUMAN POTENTIAL</div>
        <div className="eyebrow">Organisation invitation</div>
        <h1>Join your team</h1>
        {status && <p className="subtitle" role="status">{status}</p>}
        {error && <div className="dashboard-error" role="alert">{error}</div>}
        {error && <button className="btn primary auth-submit" onClick={() => router.replace("/login?next=" + encodeURIComponent(window.location.pathname + window.location.search))}>Go to sign in</button>}
      </section>
    </main>
  );
}

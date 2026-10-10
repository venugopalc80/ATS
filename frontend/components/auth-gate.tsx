"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiFetch, API_BASE } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    let active = true;
    const publicRoute =
      pathname === "/login" ||
      pathname === "/careers" ||
      pathname.startsWith("/careers/");

    if (publicRoute) {
      setAuthorized(true);
      setReady(true);
      setAuthError("");
      return () => { active = false; };
    }

    setReady(false);
    setAuthorized(false);
    setAuthError("");

    async function check() {
      try {
        const { data, error } = await supabase.auth.getSession();
        if (error) throw error;

        if (!data.session) {
          // Fail closed: never render a protected route without a session.
          if (active) window.location.replace("/login");
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

  if (!ready) {
    return <div className="auth-loading">Verifying AQERITH access...</div>;
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

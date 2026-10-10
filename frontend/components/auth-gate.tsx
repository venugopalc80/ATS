"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { apiFetch, API_BASE } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    const publicRoute =
      pathname === "/login" ||
      pathname === "/careers" ||
      pathname.startsWith("/careers/");

    if (publicRoute) {
      setReady(true);
      return () => {
        active = false;
      };
    }

    setReady(false);

    async function check() {
      try {
        const { data, error } = await supabase.auth.getSession();
        if (error) throw error;

        if (!data.session) {
          router.replace("/login");
          return;
        }

        if (API_BASE) {
          const response = await apiFetch(API_BASE + "/api/me", {
            signal: AbortSignal.timeout(10000),
          });

          if (response.status === 401) {
            await supabase.auth.signOut();
            router.replace("/login");
            return;
          }

          if (response.ok) {
            const context = await response.json();
            const firstOrg = context.organizations?.[0];

            if (!firstOrg && pathname !== "/onboarding") {
              router.replace("/onboarding");
              return;
            }

            if (firstOrg) {
              window.localStorage.setItem("talentos_active_org", firstOrg.id);
            }
          }
        }
      } catch (error) {
        // Do not leave the whole application permanently hidden if auth/API is unavailable.
        console.error("TalentOS auth check failed:", error);
      } finally {
        if (active) setReady(true);
      }
    }

    void check();

    // Avoid calling getSession() again from onAuthStateChange; doing so can
    // deadlock Supabase's auth lock in some browser/session timing scenarios.
    return () => {
      active = false;
    };
  }, [pathname, router]);

  if (!ready) {
    return <div className="auth-loading">Loading TalentOS...</div>;
  }

  return <>{children}</>;
}

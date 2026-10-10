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

    async function check() {
      const { data } = await supabase.auth.getSession();

      if (pathname === "/login" || pathname === "/careers" || pathname.startsWith("/careers/")) {
        if (active) setReady(true);
        return;
      }

      if (!data.session) {
        router.replace("/login");
        return;
      }

      const response = await apiFetch(API_BASE + "/api/me");
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

      if (active) setReady(true);
    }

    check();
    const { data: listener } = supabase.auth.onAuthStateChange(() => {
      check();
    });

    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, [pathname, router]);

  if (!ready && pathname !== "/login" && pathname !== "/careers" && !pathname.startsWith("/careers/")) {
    return <div className="auth-loading">Loading TalentOS...</div>;
  }

  return <>{children}</>;
}

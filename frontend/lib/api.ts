import { supabase } from "./supabase";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", "Bearer " + token);

  let url = input.toString();
  const activeOrg = typeof window !== "undefined"
    ? window.localStorage.getItem("talentos_active_org")
    : null;

  if (activeOrg) {
    url = url.replace(/organization_id=[^&]+/g, "organization_id=" + encodeURIComponent(activeOrg));
  }

  let body = init.body;
  if (activeOrg && typeof body === "string" && headers.get("content-type")?.includes("application/json")) {
    try {
      const parsed = JSON.parse(body);
      if (parsed && typeof parsed === "object" && "organization_id" in parsed) {
        parsed.organization_id = activeOrg;
        body = JSON.stringify(parsed);
      }
    } catch {
      // Keep non-JSON bodies unchanged.
    }
  }

  return fetch(url, { ...init, headers, body });
}

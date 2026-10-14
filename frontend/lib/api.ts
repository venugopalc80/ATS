import { supabase } from "./supabase";
import { getExplicitActiveOrganizationId } from "./organization";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  options: { preserveOrganization?: boolean } = {},
) {
  const { data, error } = await supabase.auth.getSession();
  if (error) throw error;
  const token = data.session?.access_token;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", "Bearer " + token);

  let url = input.toString();
  // Prefer the current AQERITH key. The TalentOS key is retained only for
  // older browser sessions and should never override the new key.
  const activeOrg = getExplicitActiveOrganizationId();

  if (activeOrg && !options.preserveOrganization) {
    url = url.replace(/organization_id=[^&]+/g, "organization_id=" + encodeURIComponent(activeOrg));
  }

  let body = init.body;
  if (activeOrg && !options.preserveOrganization && typeof body === "string" && headers.get("content-type")?.includes("application/json")) {
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

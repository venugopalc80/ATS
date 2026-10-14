const DEFAULT_ORGANIZATION_ID = process.env.NEXT_PUBLIC_ORGANIZATION_ID ?? "";

/**
 * Resolve the active organisation consistently across all workspace screens.
 * AQERITH is the current storage key; TalentOS remains a migration fallback.
 */
export function getActiveOrganizationId(fallback = DEFAULT_ORGANIZATION_ID): string {
  if (typeof window === "undefined") return fallback;
  return window.localStorage.getItem("aqerith_active_org")
    || window.localStorage.getItem("talentos_active_org")
    || fallback;
}

/** Return only an explicitly selected organisation, for request rewriting. */
export function getExplicitActiveOrganizationId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("aqerith_active_org")
    || window.localStorage.getItem("talentos_active_org")
    || null;
}

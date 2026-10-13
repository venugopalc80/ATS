import { createClient } from "@supabase/supabase-js";

/** Create the browser Supabase client only when a caller needs it.
 * Keeping this lazy avoids requiring public Supabase environment variables
 * during Next.js build-time prerendering of routes that do not use auth.
 */
export function getSupabaseClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    throw new Error("Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.");
  }
  return createClient(url, key);
}

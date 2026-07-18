// Supabase client — created ONLY when the project env is present. With NEXT_PUBLIC_SUPABASE_URL /
// _ANON_KEY unset (local/offline dev) this stays null and the app runs exactly as before, unauthenticated
// (the backend then scopes everything to the single 'local' user). Set both and the app gains sign-in.
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();

export const supabaseEnabled = Boolean(URL && ANON);

let _client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient | null {
  if (!supabaseEnabled) return null;
  if (!_client) {
    _client = createClient(URL!, ANON!, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
  }
  return _client;
}

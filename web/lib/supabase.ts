import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Lazily create the browser client on first use. This keeps build-time prerendering
// (which doesn't run client effects) from constructing the client and throwing when
// env vars aren't inlined yet. The NEXT_PUBLIC_* vars must still be set in the
// deployment for the app to work at runtime.
let _client: SupabaseClient | null = null;

function getClient(): SupabaseClient {
  if (_client) return _client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY. " +
        "Set them in your environment (.env.local) or Vercel project settings."
    );
  }
  _client = createClient(url, anonKey);
  return _client;
}

// Proxy so existing `supabase.from(...)` / `supabase.auth` calls keep working, but the
// underlying client is only built on first property access (always client-side).
export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop, receiver) {
    const client = getClient();
    const value = Reflect.get(client as object, prop, receiver);
    return typeof value === "function" ? value.bind(client) : value;
  },
});

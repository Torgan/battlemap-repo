import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

// Single browser client. Public reads use the anon role (RLS limits to approved maps);
// admin actions work after an authenticated session is established via supabase.auth.
export const supabase = createClient(url, anonKey);

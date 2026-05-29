"use client";

import { useState } from "react";
import { supabase } from "@/lib/supabase";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setError(error.message);
    setBusy(false);
  }

  return (
    <div className="panel" style={{ maxWidth: 380, margin: "40px auto" }}>
      <h2 style={{ marginTop: 0 }}>Admin sign in</h2>
      <form onSubmit={signIn} className="row" style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
        <input type="email" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
      {error && <p style={{ color: "var(--red)" }}>{error}</p>}
      <p className="muted" style={{ fontSize: 13 }}>
        Create your admin user in Supabase → Authentication → Users (or enable email signups).
      </p>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import Login from "./Login";
import Queue from "./Queue";
import Sources from "./Sources";

export default function AdminPage() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<"queue" | "sources">("queue");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  if (!ready) return <p className="muted">Loading…</p>;
  if (!session) return <Login />;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <div className="row">
          <button className={tab === "queue" ? "primary" : ""} onClick={() => setTab("queue")}>
            Moderation queue
          </button>
          <button className={tab === "sources" ? "primary" : ""} onClick={() => setTab("sources")}>
            Sources
          </button>
        </div>
        <div className="row">
          <span className="muted">{session.user.email}</span>
          <button onClick={() => supabase.auth.signOut()}>Sign out</button>
        </div>
      </div>
      {tab === "queue" ? <Queue /> : <Sources />}
    </>
  );
}

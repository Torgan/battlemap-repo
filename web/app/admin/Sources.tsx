"use client";

import { useCallback, useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { SourceRow } from "@/lib/types";

export default function Sources() {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [sub, setSub] = useState("");

  const load = useCallback(() => {
    supabase.from("sources").select("*").order("subreddit").then(({ data }) =>
      setSources((data as SourceRow[]) ?? [])
    );
  }, []);
  useEffect(load, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    const name = sub.trim().replace(/^r\//, "");
    if (!name) return;
    await supabase.from("sources").upsert({ subreddit: name }, { onConflict: "subreddit" });
    setSub("");
    load();
  }

  async function patch(id: number, fields: Partial<SourceRow>) {
    await supabase.from("sources").update(fields).eq("id", id);
    load();
  }

  async function remove(id: number) {
    await supabase.from("sources").delete().eq("id", id);
    load();
  }

  return (
    <>
      <form onSubmit={add} className="toolbar">
        <input placeholder="subreddit (e.g. battlemaps)" value={sub} onChange={(e) => setSub(e.target.value)} />
        <button className="primary">Add source</button>
      </form>

      <table>
        <thead>
          <tr>
            <th>Subreddit</th><th>Enabled</th><th>Sort</th><th>Time</th><th>Min score</th><th>Last run</th><th></th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id}>
              <td>r/{s.subreddit}</td>
              <td>
                <input type="checkbox" checked={s.enabled}
                       onChange={(e) => patch(s.id, { enabled: e.target.checked })} />
              </td>
              <td>
                <select value={s.sort} onChange={(e) => patch(s.id, { sort: e.target.value as SourceRow["sort"] })}>
                  <option value="top">top</option>
                  <option value="hot">hot</option>
                  <option value="new">new</option>
                </select>
              </td>
              <td>
                <select value={s.time_filter} onChange={(e) => patch(s.id, { time_filter: e.target.value })}>
                  {["hour", "day", "week", "month", "year", "all"].map((t) => <option key={t}>{t}</option>)}
                </select>
              </td>
              <td>
                <input type="number" value={s.min_score} style={{ width: 70 }}
                       onChange={(e) => patch(s.id, { min_score: Number(e.target.value) })} />
              </td>
              <td className="muted">{s.last_run_at ? new Date(s.last_run_at).toLocaleString() : "—"}</td>
              <td><button className="red" onClick={() => remove(s.id)}>Delete</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

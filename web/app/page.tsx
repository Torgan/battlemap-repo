"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { GridKind, MapRow } from "@/lib/types";

interface GalleryMap extends MapRow {
  tags: string[];
}

export default function Gallery() {
  const [maps, setMaps] = useState<GalleryMap[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [grid, setGrid] = useState<"" | GridKind>("");
  const [tag, setTag] = useState("");

  useEffect(() => {
    // Reads the approved_maps view (RLS: approved only). tags is an aggregated array.
    supabase
      .from("approved_maps")
      .select("*")
      .order("created_utc", { ascending: false })
      .limit(500)
      .then(({ data, error }) => {
        if (error) setError(error.message);
        else setMaps((data as GalleryMap[]) ?? []);
        setLoading(false);
      });
  }, []);

  const allTags = useMemo(() => {
    const s = new Set<string>();
    maps.forEach((m) => m.tags?.forEach((t) => s.add(t)));
    return Array.from(s).sort();
  }, [maps]);

  const filtered = maps.filter((m) => {
    if (q && !m.title.toLowerCase().includes(q.toLowerCase())) return false;
    if (grid && m.grid_type !== grid) return false;
    if (tag && !m.tags?.includes(tag)) return false;
    return true;
  });

  if (loading) return <p className="muted">Loading maps…</p>;
  if (error) return <p className="muted">Error: {error}. Did you set the Supabase env vars and run schema.sql?</p>;

  return (
    <>
      <div className="toolbar">
        <input placeholder="Search title…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={grid} onChange={(e) => setGrid(e.target.value as GridKind | "")}>
          <option value="">Any grid</option>
          <option value="grid">Grid</option>
          <option value="gridless">Gridless</option>
          <option value="unknown">Unknown</option>
        </select>
        <select value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">Any tag</option>
          {allTags.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="muted" style={{ alignSelf: "center" }}>{filtered.length} map(s)</span>
      </div>

      {filtered.length === 0 ? (
        <p className="muted">No approved maps yet. Run the scraper, then approve maps in the admin.</p>
      ) : (
        <div className="grid">
          {filtered.map((m) => (
            <Link key={m.id} href={`/map/${m.id}`} className="card">
              {m.thumb_url && <img src={m.thumb_url} alt={m.title} loading="lazy" />}
              <div className="body">
                <p className="title">{m.title}</p>
                <div className="tags">
                  {m.dimensions && <span className="tag">{m.dimensions}</span>}
                  {m.tags?.slice(0, 4).map((t) => <span key={t} className="tag">{t}</span>)}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}

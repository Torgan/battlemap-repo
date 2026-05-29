"use client";

import { useCallback, useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { MapRow, MapStatus } from "@/lib/types";

interface AdminMap extends MapRow {
  map_tags: { tags: { id: number; name: string } | null }[];
}

const STATUSES: MapStatus[] = ["pending", "approved", "hidden", "rejected", "removed"];

export default function Queue() {
  const [status, setStatus] = useState<MapStatus>("pending");
  const [maps, setMaps] = useState<AdminMap[]>([]);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState<string | null>(null);

  // Close the lightbox on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setZoom(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    supabase
      .from("maps")
      .select("*, map_tags(tags(id, name))")
      .eq("status", status)
      .order("created_utc", { ascending: false })
      .limit(300)
      .then(({ data }) => {
        setMaps((data as AdminMap[]) ?? []);
        setLoading(false);
      });
  }, [status]);

  useEffect(load, [load]);

  async function setMapStatus(id: string, s: MapStatus) {
    await supabase.from("maps").update({ status: s }).eq("id", id);
    setMaps((prev) => prev.filter((m) => m.id !== id));
  }

  // Bulk-approve every map currently in this status (whole DB, not just the loaded page).
  async function approveAll() {
    if (!confirm(`Approve ALL "${status}" maps? This affects every map with that status.`)) return;
    setLoading(true);
    await supabase.from("maps").update({ status: "approved" }).eq("status", status);
    load();
  }

  return (
    <>
      <div className="toolbar">
        {STATUSES.map((s) => (
          <button key={s} className={status === s ? "primary" : ""} onClick={() => setStatus(s)}>
            {s}
          </button>
        ))}
        <span className="muted" style={{ alignSelf: "center" }}>
          {loading ? "…" : `${maps.length} map(s)`}
        </span>
        {(status === "pending" || status === "hidden") && maps.length > 0 && (
          <button className="green" style={{ marginLeft: "auto" }} onClick={approveAll}>
            ✓ Approve all
          </button>
        )}
      </div>

      {maps.map((m) => (
        <MapEditor key={m.id} map={m} onStatus={setMapStatus} onZoom={setZoom} />
      ))}
      {!loading && maps.length === 0 && <p className="muted">Nothing here.</p>}

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={zoom} alt="full map" onClick={(e) => e.stopPropagation()} />
          <span className="lightbox-hint">click anywhere or press Esc to close</span>
        </div>
      )}
    </>
  );
}

function MapEditor({
  map,
  onStatus,
  onZoom,
}: {
  map: AdminMap;
  onStatus: (id: string, s: MapStatus) => void;
  onZoom: (url: string) => void;
}) {
  const [description, setDescription] = useState(map.description ?? "");
  const [tags, setTags] = useState(
    (map.map_tags ?? []).map((mt) => mt.tags?.name).filter(Boolean).join(", ")
  );
  const [saved, setSaved] = useState(false);

  async function save() {
    await supabase.from("maps").update({ description }).eq("id", map.id);
    await saveTags(map.id, tags);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  return (
    <div className="panel">
      <div className="row" style={{ alignItems: "flex-start" }}>
        {map.thumb_url && (
          <img src={map.thumb_url} alt={map.title}
               title="Click to view full image"
               onClick={() => onZoom(map.image_url ?? map.thumb_url!)}
               style={{ width: 160, height: 160, objectFit: "cover", borderRadius: 8, cursor: "zoom-in" }} />
        )}
        <div style={{ flex: 1, minWidth: 280 }}>
          <p style={{ margin: "0 0 4px", fontWeight: 600 }}>{map.title}</p>
          <p className="muted" style={{ margin: "0 0 8px", fontSize: 13 }}>
            r/{map.source_subreddit} · {map.reddit_author ? `u/${map.reddit_author}` : "?"} ·{" "}
            {map.dimensions ?? "—"} · {map.grid_type} ·{" "}
            <a href={map.permalink} target="_blank" rel="noreferrer">source</a>
          </p>
          <textarea rows={2} placeholder="Description" value={description}
                    onChange={(e) => setDescription(e.target.value)} style={{ width: "100%" }} />
          <input placeholder="comma, separated, tags" value={tags}
                 onChange={(e) => setTags(e.target.value)} style={{ width: "100%", marginTop: 8 }} />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="green" onClick={() => onStatus(map.id, "approved")}>Approve</button>
            <button onClick={() => onStatus(map.id, "hidden")}>Hide</button>
            <button className="red" onClick={() => onStatus(map.id, "rejected")}>Reject</button>
            <button className="red" onClick={() => onStatus(map.id, "removed")}>Takedown</button>
            <button onClick={save}>{saved ? "Saved ✓" : "Save edits"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Replace a map's tags with the given comma-separated names.
async function saveTags(mapId: string, csv: string) {
  const names = Array.from(
    new Set(csv.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean))
  );
  await supabase.from("map_tags").delete().eq("map_id", mapId);
  if (names.length === 0) return;

  await supabase.from("tags").upsert(names.map((name) => ({ name, category: "other" })),
    { onConflict: "name", ignoreDuplicates: true });
  const { data: tagRows } = await supabase.from("tags").select("id, name").in("name", names);
  const links = (tagRows ?? []).map((t) => ({ map_id: mapId, tag_id: t.id }));
  if (links.length) await supabase.from("map_tags").upsert(links);
}

"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import type { MapRow } from "@/lib/types";

interface DetailMap extends MapRow {
  tags: string[];
}

export default function MapDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [map, setMap] = useState<DetailMap | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase
      .from("approved_maps")
      .select("*")
      .eq("id", id)
      .single()
      .then(({ data }) => {
        setMap(data as DetailMap);
        setLoading(false);
      });
  }, [id]);

  if (loading) return <p className="muted">Loading…</p>;
  if (!map) return <p className="muted">Map not found (or not approved). <Link href="/">Back to gallery</Link></p>;

  return (
    <>
      <p><Link href="/">← Back to gallery</Link></p>
      <h1>{map.title}</h1>
      <div className="row" style={{ marginBottom: 16 }}>
        {map.dimensions && <span className="badge">{map.dimensions}</span>}
        <span className="badge">{map.grid_type}</span>
        {map.width && map.height && <span className="muted">{map.width}×{map.height}px</span>}
        <span className="muted">r/{map.source_subreddit}</span>
      </div>

      {map.image_url && <img className="detail-img" src={map.image_url} alt={map.title} />}

      {map.description && <p style={{ marginTop: 16 }}>{map.description}</p>}

      <div className="tags" style={{ margin: "12px 0" }}>
        {map.tags?.map((t) => <span key={t} className="tag">{t}</span>)}
      </div>

      <div className="panel">
        <div className="row">
          {map.image_url && (
            <a className="badge" href={map.image_url} download target="_blank" rel="noreferrer">
              ⬇ Download full image
            </a>
          )}
          <a className="badge" href={map.permalink} target="_blank" rel="noreferrer">
            View original post
          </a>
        </div>
        <p className="muted" style={{ marginTop: 10, marginBottom: 0 }}>
          Original art by {map.reddit_author ? `u/${map.reddit_author}` : "unknown"} via r/{map.source_subreddit}.
        </p>
      </div>
    </>
  );
}

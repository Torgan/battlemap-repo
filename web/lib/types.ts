export type MapStatus = "pending" | "approved" | "rejected" | "hidden" | "removed";
export type GridKind = "grid" | "gridless" | "unknown";

export interface MapRow {
  id: string;
  reddit_post_id: string;
  source_subreddit: string;
  title: string;
  reddit_author: string | null;
  permalink: string;
  image_url: string | null;
  thumb_url: string | null;
  width: number | null;
  height: number | null;
  grid_type: GridKind;
  grid_size: number | null;
  dimensions: string | null;
  description: string | null;
  score: number | null;
  status: MapStatus;
  created_utc: string | null;
}

export interface Tag {
  id: number;
  name: string;
  category: string;
}

export interface SourceRow {
  id: number;
  subreddit: string;
  enabled: boolean;
  sort: "top" | "hot" | "new";
  time_filter: string;
  min_score: number;
  last_run_at: string | null;
}

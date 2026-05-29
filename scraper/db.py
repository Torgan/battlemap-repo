"""Supabase data access for the scraper (uses the service-role key)."""
from __future__ import annotations

from typing import Any

from supabase import Client, create_client

from config import Config


class DB:
    def __init__(self, cfg: Config):
        self.client: Client = create_client(cfg.supabase_url, cfg.supabase_service_key)

    # ---- sources ----
    def enabled_sources(self) -> list[dict[str, Any]]:
        res = self.client.table("sources").select("*").eq("enabled", True).execute()
        return res.data or []

    def touch_source(self, source_id: int) -> None:
        self.client.table("sources").update({"last_run_at": "now()"}).eq("id", source_id).execute()

    # ---- maps ----
    def post_exists(self, reddit_post_id: str) -> bool:
        res = (self.client.table("maps").select("id")
               .eq("reddit_post_id", reddit_post_id).limit(1).execute())
        return bool(res.data)

    def recent_phashes(self, limit: int = 2000) -> list[str]:
        res = (self.client.table("maps").select("phash")
               .order("scraped_at", desc=True).limit(limit).execute())
        return [row["phash"] for row in (res.data or []) if row.get("phash")]

    def insert_map(self, row: dict[str, Any]) -> str:
        res = self.client.table("maps").insert(row).execute()
        return res.data[0]["id"]

    def all_maps(self) -> list[dict[str, Any]]:
        res = (self.client.table("maps")
               .select("id,title,source_subreddit,reddit_author,dimensions,grid_type,"
                       "permalink,thumb_url,image_url,status")
               .execute())
        return res.data or []

    def update_map(self, map_id: str, fields: dict[str, Any]) -> None:
        self.client.table("maps").update(fields).eq("id", map_id).execute()

    def clear_tags(self, map_id: str) -> None:
        self.client.table("map_tags").delete().eq("map_id", map_id).execute()

    def maps_to_purge(self) -> list[dict[str, Any]]:
        """Rejected/removed maps that still have R2 objects to delete."""
        res = (self.client.table("maps")
               .select("id,image_key,thumb_key")
               .in_("status", ["rejected", "removed"])
               .execute())
        return [r for r in (res.data or []) if r.get("image_key") or r.get("thumb_key")]

    # ---- tags ----
    def upsert_tag(self, name: str, category: str) -> int:
        # tags.name is unique; upsert then read back the id.
        self.client.table("tags").upsert(
            {"name": name, "category": category}, on_conflict="name"
        ).execute()
        res = self.client.table("tags").select("id").eq("name", name).limit(1).execute()
        return res.data[0]["id"]

    def link_tags(self, map_id: str, tag_ids: list[int]) -> None:
        if not tag_ids:
            return
        rows = [{"map_id": map_id, "tag_id": tid} for tid in tag_ids]
        self.client.table("map_tags").upsert(rows).execute()

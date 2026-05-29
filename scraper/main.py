"""Scraper entrypoint.

Usage:
    python main.py                          # all enabled sources
    python main.py --subreddit battlemaps   # one subreddit
    python main.py --limit 5                # cap posts per source (great for testing)
    python main.py --dry-run                # fetch + tag, but don't upload or write DB
"""
from __future__ import annotations

import argparse
import logging
import sys

from config import Config
from db import DB
from dedupe import is_near_duplicate, phash_hex
from extract import extract_images
from reddit_client import iter_submissions, make_reddit
from storage import R2, download_and_process
from tagging import TagResult, build_description, heuristic_tags

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scraper")


def merge_tags(base: TagResult, extra: TagResult | None) -> TagResult:
    if not extra:
        return base
    seen = {name for name, _ in base.tags}
    for name, cat in extra.tags:
        if name not in seen:
            base.tags.append((name, cat))
            seen.add(name)
    if base.grid_type == "unknown" and extra.grid_type != "unknown":
        base.grid_type = extra.grid_type
    base.dimensions = base.dimensions or extra.dimensions
    base.description = extra.description or base.description
    return base


def process_source(cfg: Config, db: DB, r2: R2, reddit, source: dict, limit: int, dry: bool) -> int:
    sub = source["subreddit"]
    log.info("Scraping r/%s (sort=%s, time=%s, limit=%d)", sub, source["sort"],
             source["time_filter"], limit)
    known_hashes = [] if dry else db.recent_phashes()
    added = 0

    for sub_post in iter_submissions(reddit, sub, source["sort"], source["time_filter"], limit):
        # RSS doesn't expose score (reads as 0); the feed is already sorted by popularity,
        # so only apply min_score when a real score is present.
        score = getattr(sub_post, "score", 0)
        if score and source.get("min_score", 0) and score < source["min_score"]:
            continue

        images = extract_images(sub_post)
        if not images:
            log.debug("skip %s: no supported image (%s)", sub_post.id, sub_post.url)
            continue

        # Tags + description are computed once per post and shared across gallery images.
        flair = getattr(sub_post, "link_flair_text", None)
        body = getattr(sub_post, "selftext", "")
        author = getattr(sub_post.author, "name", None) if sub_post.author else None
        tags = heuristic_tags(sub_post.title, body, flair)
        tags.description = build_description(
            sub_post.title, tags.tags, tags.dimensions, tags.grid_type, sub, author
        )
        permalink = sub_post.permalink
        if not permalink.startswith("http"):
            permalink = f"https://www.reddit.com{permalink}"
        multi = len(images) > 1

        for img in images:
            # Composite id per image so gallery entries are distinct (e.g. abc123_2).
            rid = f"{sub_post.id}{img.suffix}"
            if not dry and db.post_exists(rid):
                continue
            try:
                processed = download_and_process(img.url, img.ext, cfg.reddit_user_agent)
            except Exception as e:  # noqa: BLE001 - keep the run going
                log.warning("skip %s: download/process failed: %s", rid, e)
                continue

            ph = phash_hex(processed.pil_image)
            if is_near_duplicate(ph, known_hashes, cfg.phash_max_distance):
                log.info("skip %s: near-duplicate (phash)", rid)
                continue

            post_tags = tags
            if cfg.ai_tagging:
                try:
                    from ai_tagging import ai_tags
                    post_tags = merge_tags(tags, ai_tags(cfg, sub_post.title, processed.pil_image))
                except Exception as e:  # noqa: BLE001
                    log.warning("AI tagging failed for %s: %s", rid, e)

            if dry:
                log.info("[dry] %s | %dx%d | grid=%s dims=%s | tags=%s",
                         (sub_post.title + img.suffix)[:60], processed.width, processed.height,
                         post_tags.grid_type, post_tags.dimensions, [t[0] for t in post_tags.tags])
                known_hashes.append(ph)
                added += 1
                continue

            image_key = f"maps/{rid}{img.ext}"
            thumb_key = f"thumbs/{rid}.webp"
            image_url = r2.upload(image_key, processed.image_bytes, processed.content_type)
            thumb_url = r2.upload(thumb_key, processed.thumb_bytes, "image/webp")

            title = f"{sub_post.title} ({img.suffix.lstrip('_')})" if multi else sub_post.title
            map_id = db.insert_map({
                "reddit_post_id": rid,
                "source_subreddit": sub,
                "title": title,
                "reddit_author": author,
                "permalink": permalink,
                "image_key": image_key,
                "thumb_key": thumb_key,
                "image_url": image_url,
                "thumb_url": thumb_url,
                "width": processed.width,
                "height": processed.height,
                "file_size": len(processed.image_bytes),
                "phash": ph,
                "grid_type": post_tags.grid_type,
                "dimensions": post_tags.dimensions,
                "description": post_tags.description,
                "score": score,
                "created_utc": _utc(sub_post.created_utc),
                "status": "pending",
            })
            tag_ids = [db.upsert_tag(name, cat) for name, cat in post_tags.tags]
            db.link_tags(map_id, tag_ids)

            known_hashes.append(ph)
            added += 1
            log.info("added %s (%s)", rid, title[:60])

    if not dry:
        db.touch_source(source["id"])
    return added


def _utc(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def cleanup_removed(db: DB, r2: R2) -> int:
    """Delete R2 objects for rejected/removed maps to reclaim storage.

    The DB row is kept (as a tombstone) so the post isn't re-scraped; only the R2
    objects are deleted and the key/url columns are nulled.
    """
    rows = db.maps_to_purge()
    purged = 0
    for r in rows:
        for key in (r.get("image_key"), r.get("thumb_key")):
            if key:
                try:
                    r2.delete(key)
                except Exception as e:  # noqa: BLE001
                    log.warning("R2 delete failed for %s: %s", key, e)
        db.update_map(r["id"], {"image_key": None, "thumb_key": None,
                                "image_url": None, "thumb_url": None})
        purged += 1
    if purged:
        log.info("Purged R2 objects for %d rejected/removed map(s).", purged)
    return purged


def retag_existing(db: DB) -> int:
    """Recompute heuristic tags + templated descriptions for maps already in the DB.

    Uses only stored metadata (title, dimensions, etc.) — no re-download. Also repairs
    any malformed permalinks.
    """
    maps = db.all_maps()
    log.info("Re-tagging %d existing map(s)…", len(maps))
    for m in maps:
        title = m.get("title") or ""
        tags = heuristic_tags(title)
        # Keep already-detected dimensions/grid if the title alone can't recover them.
        dims = m.get("dimensions") or tags.dimensions
        grid = tags.grid_type if tags.grid_type != "unknown" else (m.get("grid_type") or "unknown")
        author = m.get("reddit_author")
        sub = m.get("source_subreddit") or "reddit"
        description = build_description(title, tags.tags, dims, grid, sub, author)

        fields = {"description": description, "dimensions": dims, "grid_type": grid}
        permalink = m.get("permalink") or ""
        fixed = permalink[permalink.index("http", 1):] if permalink.count("http") > 1 else permalink
        if fixed != permalink:
            fields["permalink"] = fixed
        db.update_map(m["id"], fields)

        db.clear_tags(m["id"])
        tag_ids = [db.upsert_tag(name, cat) for name, cat in tags.tags]
        db.link_tags(m["id"], tag_ids)
    log.info("Re-tagged %d map(s).", len(maps))
    return len(maps)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape battlemaps from Reddit.")
    parser.add_argument("--subreddit", help="Only scrape this subreddit (must be enabled or seeded).")
    parser.add_argument("--limit", type=int, help="Max posts per source.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + tag but don't upload/write.")
    parser.add_argument("--retag", action="store_true",
                        help="Recompute tags/descriptions for maps already in the DB, then exit.")
    parser.add_argument("--cleanup", action="store_true",
                        help="Only delete R2 objects for rejected/removed maps, then exit.")
    args = parser.parse_args()

    if args.retag:
        return 0 if retag_existing(DB(Config.load())) >= 0 else 1

    if args.cleanup:
        cfg = Config.load()
        cleanup_removed(DB(cfg), R2(cfg))
        return 0

    cfg = Config.load(require_cloud=not args.dry_run)
    reddit = make_reddit(cfg)

    def adhoc(sub: str) -> dict:
        return {"id": -1, "subreddit": sub, "sort": "top", "time_filter": "month", "min_score": 0}

    if args.dry_run:
        # No DB/cloud needed: use the requested subreddit or sensible defaults.
        db = None
        subs = [args.subreddit] if args.subreddit else ["battlemaps", "dndmaps", "FantasyMaps"]
        sources = [adhoc(s) for s in subs]
    else:
        db = DB(cfg)
        sources = db.enabled_sources()
        if args.subreddit:
            sources = [s for s in sources if s["subreddit"].lower() == args.subreddit.lower()]
            if not sources:
                sources = [adhoc(args.subreddit)]  # allow a subreddit not in the DB

    r2 = None if args.dry_run else R2(cfg)
    limit = args.limit or cfg.default_fetch_limit
    total = 0
    for source in sources:
        total += process_source(cfg, db, r2, reddit, source, limit, args.dry_run)

    # Reclaim storage from any maps moderated as rejected/removed since the last run.
    if not args.dry_run:
        cleanup_removed(db, r2)

    log.info("Done. %d map(s) %s.", total, "previewed" if args.dry_run else "added")
    return 0


if __name__ == "__main__":
    sys.exit(main())

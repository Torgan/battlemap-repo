"""Read-only Reddit access via the public RSS feeds (no OAuth/app required).

Reddit blocks the unauthenticated `.json` API (403) for many networks, but still serves
the Atom RSS feeds (e.g. https://www.reddit.com/r/<sub>/top.rss?t=month&limit=100). We
parse those and resolve each post's full-resolution image:

  * direct image posts -> the submitted i.redd.it URL is already full-res
  * gallery posts      -> derive i.redd.it/<id>.<ext> from the preview.redd.it thumbnail
                          (gets the first image of the gallery at full resolution)

A descriptive User-Agent and a polite delay keep this low-volume and well-behaved.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Iterator

import requests

from config import Config

log = logging.getLogger("scraper.reddit")

BASE = "https://www.reddit.com"
ATOM = "{http://www.w3.org/2005/Atom}"
MAX_PER_FEED = 100          # RSS feeds cap out around 100 entries
REQUEST_DELAY = 1.5         # seconds between subreddit feeds
MAX_RETRIES = 4
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

_LINK_RE = re.compile(r'<a href="([^"]+)">\[link\]</a>')
_PREVIEW_RE = re.compile(r'<img src="(https://preview\.redd\.it/[^"?]+)')
_ID_RE = re.compile(r"/comments/([a-z0-9]+)/")
_BODY_RE = re.compile(r'<!-- SC_OFF -->(.*?)<!-- SC_ON -->', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _body_text(content: str) -> str:
    """Extract the post's self-text (markdown body) from an RSS entry's HTML content."""
    m = _BODY_RE.search(content)
    if not m:
        return ""
    import html as _html
    text = _TAG_RE.sub(" ", m.group(1))
    return _html.unescape(re.sub(r"\s+", " ", text)).strip()


def _ext(url: str) -> str | None:
    low = url.lower().split("?")[0]
    for e in IMAGE_EXTS:
        if low.endswith(e):
            return e
    return None


def _resolve_image(submitted: str | None, preview: str | None) -> str | None:
    """Return a full-res direct image URL, or None if not an image post we can use."""
    if submitted and _ext(submitted):
        return submitted  # direct i.redd.it image, already full-res
    if preview and preview.startswith("https://preview.redd.it/") and _ext(preview):
        # gallery / crosspost: the preview id maps to the original on i.redd.it
        return preview.replace("https://preview.redd.it/", "https://i.redd.it/")
    return None


class _Author:
    def __init__(self, name: str) -> None:
        self.name = name


class Post:
    """Thin stand-in for a Reddit submission, built from an RSS entry.

    `url` is pre-resolved to a direct full-res image URL (or "" if none was found),
    so extract.extract_image() handles it via the direct-image path.
    """

    def __init__(self, *, post_id: str, title: str, author: str | None, permalink: str,
                 url: str, created_utc: float, is_gallery: bool, body: str = "") -> None:
        self.id = post_id
        self.title = title
        self.author = _Author(author) if author else None
        self.permalink = permalink
        self.url = url
        self.created_utc = created_utc
        self.is_gallery = is_gallery
        self.selftext = body
        self.score = 0               # not available via RSS
        self.media_metadata = None   # resolution already done in the client
        self.gallery_data = None
        self.link_flair_text = None


class RedditRSS:
    def __init__(self, user_agent: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def get_feed(self, path: str, params: dict) -> bytes:
        url = f"{BASE}{path}"
        for attempt in range(MAX_RETRIES):
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code in (429, 503):
                wait = 5 * (attempt + 1)
                log.warning("%d from Reddit; backing off %ds", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.content
        raise RuntimeError(f"Reddit rate-limited after {MAX_RETRIES} retries: {url}")


def make_reddit(cfg: Config) -> RedditRSS:
    return RedditRSS(cfg.reddit_user_agent)


def _parse_published(entry: ET.Element) -> float:
    el = entry.find(f"{ATOM}published") or entry.find(f"{ATOM}updated")
    if el is None or not el.text:
        return datetime.now(tz=timezone.utc).timestamp()
    try:
        return datetime.fromisoformat(el.text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return datetime.now(tz=timezone.utc).timestamp()


def iter_submissions(
    client: RedditRSS,
    subreddit: str,
    sort: str = "top",
    time_filter: str = "month",
    limit: int = 50,
) -> Iterator[Post]:
    """Yield up to `limit` image posts from a subreddit's RSS feed."""
    if sort not in ("top", "hot", "new"):
        raise ValueError(f"Unknown sort: {sort}")

    params: dict = {"limit": min(limit, MAX_PER_FEED)}
    if sort == "top":
        params["t"] = time_filter

    raw = client.get_feed(f"/r/{subreddit}/{sort}.rss", params)
    root = ET.fromstring(raw)

    yielded = 0
    for entry in root.findall(f"{ATOM}entry"):
        if yielded >= limit:
            break
        link_el = entry.find(f"{ATOM}link")
        title_el = entry.find(f"{ATOM}title")
        permalink = link_el.get("href") if link_el is not None else ""
        m = _ID_RE.search(permalink or "")
        if not m:
            continue
        post_id = m.group(1)

        content = (entry.findtext(f"{ATOM}content") or "")
        submitted_m = _LINK_RE.search(content)
        preview_m = _PREVIEW_RE.search(content)
        submitted = submitted_m.group(1) if submitted_m else None
        preview = preview_m.group(1) if preview_m else None

        image_url = _resolve_image(submitted, preview)
        if not image_url:
            log.debug("skip %s: no resolvable image", post_id)
            continue

        author_el = entry.find(f"{ATOM}author/{ATOM}name")
        author = author_el.text.replace("/u/", "") if author_el is not None and author_el.text else None

        yield Post(
            post_id=post_id,
            title=title_el.text if title_el is not None and title_el.text else "",
            author=author,
            permalink=permalink,
            url=image_url,
            created_utc=_parse_published(entry),
            is_gallery=bool(submitted and "/gallery/" in submitted),
            body=_body_text(content),
        )
        yielded += 1

    time.sleep(REQUEST_DELAY)

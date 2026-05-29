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
    """Thin stand-in for a Reddit submission.

    For RSS, `url` is pre-resolved to a single direct image and media_metadata is None.
    For OAuth (`from_json`), media_metadata/gallery_data are populated so extract_images()
    can expand galleries to every image.
    """

    def __init__(self, *, post_id: str, title: str, author: str | None, permalink: str,
                 url: str, created_utc: float, is_gallery: bool, body: str = "",
                 score: int = 0, media_metadata=None, gallery_data=None,
                 link_flair_text: str | None = None) -> None:
        self.id = post_id
        self.title = title
        self.author = _Author(author) if author else None
        self.permalink = permalink
        self.url = url
        self.created_utc = created_utc
        self.is_gallery = is_gallery
        self.selftext = body
        self.score = score
        self.media_metadata = media_metadata
        self.gallery_data = gallery_data
        self.link_flair_text = link_flair_text

    @classmethod
    def from_json(cls, d: dict) -> "Post":
        author = d.get("author")
        return cls(
            post_id=d.get("id", ""),
            title=d.get("title", ""),
            author=author if author and author != "[deleted]" else None,
            permalink=d.get("permalink", ""),
            url=d.get("url_overridden_by_dest") or d.get("url", ""),
            created_utc=d.get("created_utc", 0.0),
            is_gallery=bool(d.get("is_gallery", False)),
            body=d.get("selftext", "") or "",
            score=d.get("score", 0),
            media_metadata=d.get("media_metadata"),
            gallery_data=d.get("gallery_data"),
            link_flair_text=d.get("link_flair_text"),
        )


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


class RedditOAuth:
    """Authenticated app-only (userless) access via oauth.reddit.com.

    Uses the client_credentials grant — only client id/secret are needed, no Reddit
    username/password. Returns full JSON including media_metadata (so galleries expand).
    """

    OAUTH = "https://oauth.reddit.com"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": cfg.reddit_user_agent})
        self._authenticate()

    def _authenticate(self) -> None:
        resp = requests.post(
            f"{BASE}/api/v1/access_token",
            auth=(self.cfg.reddit_client_id, self.cfg.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": self.cfg.reddit_user_agent},
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.session.headers.update({"Authorization": f"bearer {token}"})
        log.info("Reddit OAuth token acquired (app-only).")

    def get_listing(self, path: str, params: dict) -> dict:
        url = f"{self.OAUTH}{path}"
        for attempt in range(MAX_RETRIES):
            resp = self.session.get(url, params={**params, "raw_json": 1}, timeout=30)
            if resp.status_code in (429, 503):
                wait = 5 * (attempt + 1)
                log.warning("%d from Reddit; backing off %ds", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Reddit rate-limited after {MAX_RETRIES} retries: {url}")


def make_reddit(cfg: Config):
    """Prefer authenticated OAuth (full galleries) when credentials are present."""
    if cfg.reddit_client_id and cfg.reddit_client_secret:
        try:
            return RedditOAuth(cfg)
        except Exception as e:  # noqa: BLE001 - fall back to RSS if auth fails
            log.warning("Reddit OAuth failed (%s); falling back to RSS.", e)
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
    client,
    subreddit: str,
    sort: str = "top",
    time_filter: str = "month",
    limit: int = 50,
) -> Iterator[Post]:
    """Yield up to `limit` posts. OAuth client -> JSON (full galleries); else RSS."""
    if sort not in ("top", "hot", "new"):
        raise ValueError(f"Unknown sort: {sort}")

    if isinstance(client, RedditOAuth):
        yield from _iter_oauth(client, subreddit, sort, time_filter, limit)
        return

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


def _iter_oauth(
    client: RedditOAuth, subreddit: str, sort: str, time_filter: str, limit: int
) -> Iterator[Post]:
    """Page through oauth.reddit.com JSON listings, yielding full Post objects."""
    fetched = 0
    after: str | None = None
    while fetched < limit:
        params: dict = {"limit": min(100, limit - fetched)}
        if sort == "top":
            params["t"] = time_filter
        if after:
            params["after"] = after

        data = client.get_listing(f"/r/{subreddit}/{sort}", params).get("data", {})
        children = data.get("children", [])
        if not children:
            break
        for child in children:
            yield Post.from_json(child.get("data", {}))
            fetched += 1
            if fetched >= limit:
                break
        after = data.get("after")
        if not after:
            break
        time.sleep(REQUEST_DELAY)

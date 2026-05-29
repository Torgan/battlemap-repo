"""Resolve image URLs from Reddit submissions.

Supported sources, in priority order:
  * Direct i.redd.it / direct image URLs (.png/.jpg/.jpeg/.webp)
  * Reddit galleries (media_metadata) -> first image
Unsupported hosts (imgur albums, external sites, videos) are skipped with a reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from reddit_client import Post

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass
class ExtractedImage:
    url: str
    ext: str


def _ext_from_url(url: str) -> str | None:
    path = urlparse(url).path.lower()
    for ext in IMAGE_EXTS:
        if path.endswith(ext):
            return ext
    return None


def extract_image(submission: "Post") -> ExtractedImage | None:
    """Return the best image for a submission, or None if unsupported."""
    url = getattr(submission, "url", "") or ""

    # 1. Direct image link
    ext = _ext_from_url(url)
    if ext:
        return ExtractedImage(url=url, ext=ext)

    # 2. Reddit gallery: use media_metadata for the first valid image
    if getattr(submission, "is_gallery", False):
        media = getattr(submission, "media_metadata", None) or {}
        gallery = getattr(submission, "gallery_data", None) or {}
        order = [item["media_id"] for item in gallery.get("items", [])]
        for media_id in order or media.keys():
            meta = media.get(media_id)
            if not meta or meta.get("status") != "valid":
                continue
            mime = meta.get("m", "")  # e.g. "image/png"
            ext = "." + mime.split("/")[-1].replace("jpeg", "jpg") if "/" in mime else None
            src = (meta.get("s") or {}).get("u")  # full-size source URL
            if src and ext in IMAGE_EXTS:
                # media_metadata URLs are HTML-escaped
                return ExtractedImage(url=src.replace("&amp;", "&"), ext=ext)

    return None

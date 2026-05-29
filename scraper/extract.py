"""Resolve image URLs from a Reddit post.

Returns a LIST of images so gallery posts can yield every image, not just the first:
  * Reddit gallery (media_metadata, OAuth only)  -> every valid image, suffixes _1.._n
  * direct image URL (.png/.jpg/.jpeg/.webp)     -> single image, no suffix
  * RSS posts carry a pre-resolved single `url`  -> single image
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
    suffix: str = ""  # "" for a single image; "_1".."_n" for gallery items


def _ext_from_url(url: str) -> str | None:
    path = urlparse(url).path.lower()
    for ext in IMAGE_EXTS:
        if path.endswith(ext):
            return ext
    return None


def _ext_from_mime(mime: str) -> str | None:
    if "/" not in mime:
        return None
    ext = "." + mime.split("/")[-1].replace("jpeg", "jpg")
    return ext if ext in IMAGE_EXTS else None


def extract_images(post: "Post") -> list[ExtractedImage]:
    """Return every usable image for a post (galleries expand to all images)."""
    media = getattr(post, "media_metadata", None)
    gallery = getattr(post, "gallery_data", None)

    # Reddit gallery (only available with OAuth/JSON, which carries media_metadata)
    if getattr(post, "is_gallery", False) and media and gallery:
        out: list[ExtractedImage] = []
        for i, item in enumerate(gallery.get("items", []), start=1):
            meta = media.get(item.get("media_id"))
            if not meta or meta.get("status") != "valid":
                continue
            ext = _ext_from_mime(meta.get("m", ""))
            src = (meta.get("s") or {}).get("u")  # full-size source URL
            if src and ext:
                out.append(ExtractedImage(src.replace("&amp;", "&"), ext, f"_{i}"))
        if out:
            return out

    # Single direct image (RSS pre-resolves post.url to this; OAuth uses the submitted URL)
    url = getattr(post, "url", "") or ""
    ext = _ext_from_url(url)
    if ext:
        return [ExtractedImage(url, ext, "")]

    return []

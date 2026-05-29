"""Cloudflare R2 (S3-compatible) upload + image processing."""
from __future__ import annotations

import io
from dataclasses import dataclass

import boto3
import requests
from botocore.config import Config as BotoConfig
from PIL import Image

from config import Config

# Battlemaps are legitimately huge (often >100MP). Raise Pillow's decompression-bomb
# guard well above typical map sizes; source is trusted (personal use).
Image.MAX_IMAGE_PIXELS = 400_000_000

THUMB_MAX = 512  # longest edge, px
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass
class ProcessedImage:
    image_bytes: bytes
    content_type: str
    width: int
    height: int
    thumb_bytes: bytes
    pil_image: Image.Image  # kept for hashing


class R2:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{cfg.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=cfg.r2_access_key_id,
            aws_secret_access_key=cfg.r2_secret_access_key,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )

    def upload(self, key: str, data: bytes, content_type: str) -> str:
        self.client.put_object(
            Bucket=self.cfg.r2_bucket, Key=key, Body=data, ContentType=content_type
        )
        return f"{self.cfg.r2_public_base_url}/{key}"

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.cfg.r2_bucket, Key=key)


def download_and_process(url: str, ext: str, user_agent: str) -> ProcessedImage:
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=60)
    resp.raise_for_status()
    raw = resp.content

    img = Image.open(io.BytesIO(raw))
    img.load()
    width, height = img.size

    # Build a webp thumbnail (longest edge THUMB_MAX)
    thumb = img.convert("RGB")
    thumb.thumbnail((THUMB_MAX, THUMB_MAX), Image.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="WEBP", quality=80)

    return ProcessedImage(
        image_bytes=raw,
        content_type=CONTENT_TYPES.get(ext, "application/octet-stream"),
        width=width,
        height=height,
        thumb_bytes=buf.getvalue(),
        pil_image=img,
    )

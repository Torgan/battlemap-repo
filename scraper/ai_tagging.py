"""Optional Claude-vision tagging. Disabled unless AI_TAGGING=1.

Sends a downscaled image + title to Claude and asks for tags + a short description.
Cheap with Haiku (~$0.003/map). Merges its tags with the heuristic ones.
"""
from __future__ import annotations

import base64
import io
import json

from PIL import Image

from config import Config
from tagging import TagResult

_AI_MAX = 1024  # downscale longest edge before sending (cheaper tokens)

_PROMPT = """You are tagging a TTRPG battlemap image for a personal map library.
Reddit post title: "{title}"

Return STRICT JSON only, no prose:
{{
  "tags": ["lowercase", "single-or-two-word", "tags"],
  "grid_type": "grid" | "gridless" | "unknown",
  "dimensions": "WxH or null",
  "description": "one or two sentence factual description of the map"
}}
Tags should cover terrain, setting, and notable features. Max 8 tags."""


def _encode(img: Image.Image) -> tuple[str, str]:
    thumb = img.convert("RGB")
    thumb.thumbnail((_AI_MAX, _AI_MAX), Image.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


def ai_tags(cfg: Config, title: str, img: Image.Image) -> TagResult | None:
    if not cfg.ai_tagging or not cfg.anthropic_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    b64, media_type = _encode(img)

    msg = client.messages.create(
        model=cfg.anthropic_model,
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                              "media_type": media_type, "data": b64}},
                {"type": "text", "text": _PROMPT.format(title=title)},
            ],
        }],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    result = TagResult()
    for name in data.get("tags", [])[:8]:
        if isinstance(name, str) and name.strip():
            result.tags.append((name.strip().lower(), "other"))
    gt = data.get("grid_type")
    if gt in ("grid", "gridless", "unknown"):
        result.grid_type = gt
    dims = data.get("dimensions")
    if isinstance(dims, str) and dims.lower() != "null":
        result.dimensions = dims
    desc = data.get("description")
    if isinstance(desc, str) and desc.strip():
        result.description = desc.strip()
    return result

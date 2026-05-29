"""Optional AI vision tagging. Looks at the map image + title and returns rich tags + a
description. Two providers:

  * "gemini"    — Google Gemini (free tier: ~1500 req/day). Default/recommended.
  * "anthropic" — Claude (paid, ~$0.003/map).

Selected via AI_PROVIDER. Disabled when unset or the matching API key is missing.
Merged with the heuristic tags by the caller.
"""
from __future__ import annotations

import base64
import io
import json

import requests
from PIL import Image

from config import Config
from tagging import TagResult

_MAX_EDGE = 768  # downscale longest edge before sending (cheaper/faster, plenty for tagging)

_PROMPT = """You are tagging a TTRPG battlemap image for a personal map library.
Reddit post title: "{title}"

Return STRICT JSON only (no markdown, no prose):
{{
  "tags": ["lowercase", "one-or-two-word", "tags"],
  "grid_type": "grid" | "gridless" | "unknown",
  "dimensions": "WxH or null",
  "description": "one or two factual sentences describing the map"
}}
Tags should cover terrain, setting, and notable features. Max 8 tags."""


def _encode(img: Image.Image) -> tuple[str, str]:
    thumb = img.convert("RGB")
    thumb.thumbnail((_MAX_EDGE, _MAX_EDGE), Image.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


def _to_result(data: dict) -> TagResult:
    result = TagResult()
    for name in data.get("tags", [])[:8]:
        if isinstance(name, str) and name.strip():
            result.tags.append((name.strip().lower(), "other"))
    gt = data.get("grid_type")
    if gt in ("grid", "gridless", "unknown"):
        result.grid_type = gt
    dims = data.get("dimensions")
    if isinstance(dims, str) and dims.lower() != "null" and dims.strip():
        result.dimensions = dims.strip()
    desc = data.get("description")
    if isinstance(desc, str) and desc.strip():
        result.description = desc.strip()
    return result


def _strip_fence(text: str) -> str:
    return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def ai_tags(cfg: Config, title: str, img: Image.Image) -> TagResult | None:
    if cfg.ai_provider == "openai" and cfg.openai_api_key:
        return _openai_tags(cfg, title, img)
    if cfg.ai_provider == "gemini" and cfg.gemini_api_key:
        return _gemini_tags(cfg, title, img)
    if cfg.ai_provider == "anthropic" and cfg.anthropic_api_key:
        return _claude_tags(cfg, title, img)
    return None


def _openai_tags(cfg: Config, title: str, img: Image.Image) -> TagResult | None:
    """OpenAI-compatible chat completions with an image. Works with Groq, OpenRouter,
    Mistral, Together, etc. via OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL."""
    b64, mime = _encode(img)
    url = cfg.openai_base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": cfg.openai_model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _PROMPT.format(title=title)},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "max_tokens": 400,
        "temperature": 0.2,
    }
    resp = requests.post(url, json=body,
                         headers={"Authorization": f"Bearer {cfg.openai_api_key}"}, timeout=60)
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"]
    return _to_result(json.loads(_strip_fence(text)))


def _gemini_tags(cfg: Config, title: str, img: Image.Image) -> TagResult | None:
    b64, mime = _encode(img)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{cfg.gemini_model}:generateContent?key={cfg.gemini_api_key}")
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": b64}},
            {"text": _PROMPT.format(title=title)},
        ]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "temperature": 0.2, "maxOutputTokens": 400},
    }
    resp = requests.post(url, json=body, timeout=60)
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return _to_result(json.loads(_strip_fence(text)))


def _claude_tags(cfg: Config, title: str, img: Image.Image) -> TagResult | None:
    try:
        import anthropic
    except ImportError:
        return None
    b64, mime = _encode(img)
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    msg = client.messages.create(
        model=cfg.anthropic_model,
        max_tokens=400,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
            {"type": "text", "text": _PROMPT.format(title=title)},
        ]}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return _to_result(json.loads(_strip_fence(text)))

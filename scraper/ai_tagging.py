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
import logging
import time
from dataclasses import dataclass

import requests
from PIL import Image

from config import Config
from tagging import TagResult

log = logging.getLogger("scraper.ai")
_announced: set[str] = set()  # fallback endpoints already logged this run

_MAX_EDGE = 768  # downscale longest edge before sending (cheaper/faster, plenty for tagging)

_PROMPT = """You are tagging a TTRPG map image for a personal map library.
Reddit post title: "{title}"

Return STRICT JSON only (no markdown, no prose):
{{
  "tags": ["lowercase", "one-or-two-word", "tags"],
  "grid_type": "grid" | "gridless" | "unknown",
  "dimensions": "WxH or null",
  "scale": "battlemap" | "region" | "world",
  "description": "one or two factual sentences describing the map"
}}
Tags should cover terrain, setting, and notable features. Max 8 tags.
For "scale", judge the zoom level:
  - "battlemap": a tactical encounter map where you'd place character tokens and fight
    (a building/interior, a room, a clearing, a ship deck, a street — token scale).
  - "region": an overland/travel-scale map of a region, country, city-from-above,
    province, or a hex/wilderness map.
  - "world": a map of an entire world, continent, or planet."""


def _encode(img: Image.Image) -> tuple[str, str]:
    thumb = img.convert("RGB")
    thumb.thumbnail((_MAX_EDGE, _MAX_EDGE), Image.LANCZOS)
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


def _to_result(data: dict | list) -> TagResult:
    if isinstance(data, list):  # some models wrap the object in a list: [{...}]
        data = next((d for d in data if isinstance(d, dict)), {})
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
    scale = data.get("scale")
    if scale in ("battlemap", "region", "world"):
        result.scale = scale
    return result


def _strip_fence(text: str) -> str:
    return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def ai_tags(cfg: Config, title: str, img: Image.Image) -> TagResult | None:
    if cfg.ai_provider == "openai" and cfg.openai_api_key:
        primary = _Endpoint(cfg.openai_base_url, cfg.openai_api_key, cfg.openai_model)
        try:
            return _openai_tags(primary, title, img)
        except Exception as e:  # noqa: BLE001
            # Optional second OpenAI-compatible provider whenever the primary fails — its
            # quota is gone (daily for Groq, monthly for Mistral) or it's erroring.
            # Unset OPENAI_FALLBACK_API_KEY = no fallback.
            if not cfg.openai_fallback_api_key:
                raise
            fallback = _Endpoint(cfg.openai_fallback_base_url, cfg.openai_fallback_api_key,
                                 cfg.openai_fallback_model)
            if isinstance(e, QuotaExhausted):
                if fallback.base_url not in _announced:
                    _announced.add(fallback.base_url)
                    log.info("Primary AI quota exhausted (%s) — using fallback %s (%s)",
                             e, fallback.base_url, fallback.model)
            else:
                log.warning("Primary AI failed (%s) — trying fallback %s", e, fallback.base_url)
            return _openai_tags(fallback, title, img)
    if cfg.ai_provider == "gemini" and cfg.gemini_api_key:
        return _gemini_tags(cfg, title, img)
    if cfg.ai_provider == "anthropic" and cfg.anthropic_api_key:
        return _claude_tags(cfg, title, img)
    return None


class QuotaExhausted(RuntimeError):
    """The provider's daily quota is used up; further calls this run would just be refused."""


@dataclass(frozen=True)
class _Endpoint:
    base_url: str
    api_key: str
    model: str


# Per-endpoint (keyed by base URL) state, so Groq's quota never blocks the fallback.
_quota: dict[str, float] = {}  # base_url -> monotonic time the daily quota frees up


def _error_message(resp: requests.Response) -> str:
    try:
        body = resp.json()
        # Groq/OpenAI: {"error": {"message": ...}}; Mistral: {"message": ...}
        msg = (body.get("error") or {}).get("message") or body.get("message")
    except (ValueError, AttributeError):
        msg = None
    return f"{resp.request.url.split('/')[2] if resp.request else ''} {msg or f'HTTP {resp.status_code}'}".strip()


def _openai_tags(ep: _Endpoint, title: str, img: Image.Image) -> TagResult | None:
    """OpenAI-compatible chat completions with an image. Works with Groq, OpenRouter,
    Mistral, Together, etc. via OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL."""
    if time.monotonic() < _quota.get(ep.base_url, 0.0):
        raise QuotaExhausted(f"daily AI quota for {ep.base_url} used up earlier this run")
    limits = _limits.setdefault(ep.base_url, {"remaining": None, "reset_at": 0.0})
    b64, mime = _encode(img)
    url = ep.base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": ep.model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _PROMPT.format(title=title)},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "max_tokens": 400,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {ep.api_key}"}
    for attempt in range(4):
        _pace(limits)
        resp = requests.post(url, json=body, headers=headers, timeout=60)
        _note_limits(limits, resp)
        if resp.status_code == 429:
            retry_after = _duration(resp.headers.get("retry-after")) or 0.0
            no_quota = (resp.headers.get("x-should-retry") == "false"
                        # Mistral: a workspace without an active plan has a 0 req/min limit
                        or resp.headers.get("x-ratelimit-limit-req-minute") == "0")
            if retry_after > _MAX_WAIT or no_quota:
                # Daily quota (Groq free tier: 200k tokens/day ~ 85 maps), not the per-minute
                # window. Stop calling the API for the rest of this run.
                _quota[ep.base_url] = time.monotonic() + retry_after
                raise QuotaExhausted(_error_message(resp))
            wait = max(retry_after, _duration(resp.headers.get("x-ratelimit-reset-tokens")) or 0.0)
            time.sleep(min((wait or 5 * (attempt + 1)) + 1, _MAX_WAIT))
            limits["remaining"] = None  # just waited for the reset; don't pace again
            continue
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return _to_result(json.loads(_strip_fence(text)))
    # Surface it: this used to fail silently and left most maps with title-only tags.
    raise RuntimeError(f"still rate-limited by {ep.base_url} after 4 attempts")


# ---- client-side pacing for per-minute token limits (Groq free tier: 8k tokens/min) ----
# One image call costs ~2.2k tokens. Rather than burst into 429s (which Groq punishes with
# long Retry-After penalties), wait for the window to reset when the next call won't fit.
_CALL_TOKENS = 2500
_MAX_WAIT = 65  # the token window is one minute
_limits: dict[str, dict] = {}  # base_url -> {"remaining": tokens, "reset_at": monotonic}


def _duration(value: str | None) -> float | None:
    """Parse Groq/OpenAI durations: '54.58s', '4m19.2s', '120ms', or plain seconds."""
    if not value:
        return None
    total, num = 0.0, ""
    try:
        i = 0
        while i < len(value):
            ch = value[i]
            if ch.isdigit() or ch == ".":
                num += ch
            elif value.startswith("ms", i):
                total += float(num) / 1000; num = ""; i += 1
            elif ch in "hms":
                total += float(num) * {"h": 3600, "m": 60, "s": 1}[ch]; num = ""
            i += 1
        return total + (float(num) if num else 0.0)
    except ValueError:
        return None


def _note_limits(limits: dict, resp: requests.Response) -> None:
    try:
        limits["remaining"] = int(resp.headers["x-ratelimit-remaining-tokens"])
    except (KeyError, ValueError):
        return
    reset = _duration(resp.headers.get("x-ratelimit-reset-tokens")) or 0.0
    limits["reset_at"] = time.monotonic() + reset


def _pace(limits: dict) -> None:
    remaining = limits["remaining"]
    if remaining is not None and remaining < _CALL_TOKENS:
        wait = limits["reset_at"] - time.monotonic()
        if wait > 0:
            time.sleep(min(wait + 0.5, _MAX_WAIT))
        limits["remaining"] = None  # unknown until the next response


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

"""Environment-backed configuration for the scraper."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load ../.env (repo root) if present; in CI the env is provided directly.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _req(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


@dataclass(frozen=True)
class Config:
    # Reddit. A User-Agent is always needed. If client id/secret are set, the scraper
    # uses authenticated OAuth (oauth.reddit.com) — full galleries, more robust. Without
    # them it falls back to the public RSS feeds.
    reddit_user_agent: str
    reddit_client_id: str | None
    reddit_client_secret: str | None
    # Supabase
    supabase_url: str
    supabase_service_key: str
    # R2
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str
    r2_public_base_url: str
    # AI tagging (optional). Provider: "" (off) | "gemini" (free tier) | "anthropic".
    ai_provider: str
    gemini_api_key: str | None
    gemini_model: str
    anthropic_api_key: str | None
    anthropic_model: str
    # Tuning
    default_fetch_limit: int
    phash_max_distance: int

    @classmethod
    def load(cls, require_cloud: bool = True) -> "Config":
        # require_cloud=False allows a credential-free --dry-run (only Reddit is needed).
        cloud = _req if require_cloud else (lambda n: os.getenv(n, ""))
        return cls(
            reddit_user_agent=os.getenv(
                "REDDIT_USER_AGENT", "battlemap-repo/0.1 (personal map archive)"
            ),
            reddit_client_id=os.getenv("REDDIT_CLIENT_ID") or None,
            reddit_client_secret=os.getenv("REDDIT_CLIENT_SECRET") or None,
            supabase_url=cloud("SUPABASE_URL"),
            supabase_service_key=cloud("SUPABASE_SERVICE_KEY"),
            r2_account_id=cloud("R2_ACCOUNT_ID"),
            r2_access_key_id=cloud("R2_ACCESS_KEY_ID"),
            r2_secret_access_key=cloud("R2_SECRET_ACCESS_KEY"),
            r2_bucket=os.getenv("R2_BUCKET", "battlemaps"),
            r2_public_base_url=cloud("R2_PUBLIC_BASE_URL").rstrip("/"),
            ai_provider=os.getenv("AI_PROVIDER", "").lower().strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            default_fetch_limit=int(os.getenv("DEFAULT_FETCH_LIMIT", "50")),
            phash_max_distance=int(os.getenv("PHASH_MAX_DISTANCE", "4")),
        )

    @property
    def ai_tagging(self) -> bool:
        """True when an AI provider is selected and its API key is present."""
        if self.ai_provider == "gemini":
            return bool(self.gemini_api_key)
        if self.ai_provider == "anthropic":
            return bool(self.anthropic_api_key)
        return False

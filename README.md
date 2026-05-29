# Battlemap Repository

A personal repository of TTRPG battlemaps sourced from Reddit. A Python scraper pulls
maps from battlemap subreddits, downloads + thumbnails them, tags and describes them, and
stores everything in a free cloud stack. A Next.js web app provides a public gallery and
an auth-gated admin. A FoundryVTT module (built last) browses the library and imports maps
as Scenes.

> Personal, non-distributed use. Only public subreddit data is read, via Reddit's official
> API, within rate limits. Each map links back to its original Reddit post and author.

## Architecture

```
Reddit API ──(PRAW)──> Scraper (Python, GitHub Actions cron)
                          ├──> Cloudflare R2        (full image + thumbnail)
                          └──> Supabase Postgres    (metadata, tags, status=pending)
                                      │
        Supabase Auth ── Next.js web app (Vercel): public gallery + admin
                                      │
        FoundryVTT module ──(Supabase PostgREST + R2 URLs)──> import map as a Scene
```

| Concern        | Service            | Free tier                                  |
| -------------- | ------------------ | ------------------------------------------ |
| Metadata/auth  | Supabase Postgres  | 500 MB DB, 50k MAU; pauses after 1wk idle  |
| Image files    | Cloudflare R2      | 10 GB storage, **no egress fees**          |
| Web app        | Vercel             | Hobby                                       |
| Scraper schedule | GitHub Actions   | Cron (also keeps Supabase from pausing)    |

## Repository layout

- `db/schema.sql` — Postgres tables, indexes, RLS policies, seed sources.
- `scraper/` — Python scraper (PRAW → R2 + Supabase).
- `web/` — Next.js gallery + admin.
- `foundry-module/` — FoundryVTT module (final phase).
- `.github/workflows/scrape.yml` — scheduled scrape.

## One-time account setup

1. **Reddit** — no app or OAuth needed. The scraper reads Reddit's public JSON endpoints
   (e.g. `https://www.reddit.com/r/battlemaps/top.json`) with a descriptive User-Agent and
   polite rate-limiting. Just set `REDDIT_USER_AGENT` in `.env`.
2. **Supabase** — create a project. From *Project Settings → API* copy `SUPABASE_URL`,
   the **anon** key, and the **service_role** key. Then run `db/schema.sql` in the SQL
   editor.
3. **Cloudflare R2** — create a bucket (default name `battlemaps`), enable public access
   (r2.dev or a custom domain) and copy that base URL into `R2_PUBLIC_BASE_URL`. Create an
   R2 API token for the access key id/secret. Account id is in the dashboard URL.
4. **Vercel** — import the repo, set root to `web/`, add `NEXT_PUBLIC_SUPABASE_URL` and
   `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

Copy `.env.example` → `.env` and fill it in for local runs.

## Quick start (local)

```bash
# --- scraper ---
cd scraper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # then edit ../.env
python main.py --subreddit battlemaps --limit 5    # dry test

# --- web ---
cd ../web
npm install
npm run dev    # http://localhost:3000
```

## Status

See `db/schema.sql` for the data model. Maps land as `pending`; approve them in the admin
to make them public. The Foundry module reads only `approved` maps via the Supabase anon
key (enforced by RLS).

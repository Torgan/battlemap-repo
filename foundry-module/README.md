# Battlemap Repository — FoundryVTT module

Browse your battlemap repository inside Foundry and import maps as Scenes. It reads the
**approved** maps from your Supabase project (the `approved_maps` view via PostgREST) using
the public **anon** key — Row Level Security guarantees only approved maps are returned.

## Install (local dev)

1. Copy/symlink this `foundry-module/` folder into your Foundry data dir as
   `Data/modules/battlemap-repo` (the folder name must match the `id` in `module.json`).
   ```bash
   ln -s "$(pwd)" "$HOME/Library/Application Support/FoundryVTT/Data/modules/battlemap-repo"
   ```
2. Launch Foundry → enable **Battlemap Repository** in *Manage Modules*.
3. Open *Configure Settings → Battlemap Repository* and set:
   - **Supabase URL** — `https://yourproject.supabase.co`
   - **Supabase anon key** — the public anon key
   - **Default grid size** — px per square (default 100)

## Use

- A **Battlemap Repository** button appears at the top of the *Scenes* sidebar (GM only).
- Click it to open the browser, search by title/tag/subreddit, and **Import as Scene**.
- The imported Scene uses the public R2 image URL as its background; grid type/size come
  from the map metadata (gridless maps import with no grid).

## Distribution (later)

To install via manifest URL instead of symlink, host this folder (e.g. a GitHub release
zip) and fill in the `url` / `manifest` / `download` fields in `module.json`.

> Compatibility: verified on Foundry v13, minimum v12. Uses the v12+ Scene schema
> (`background.src`, `grid` object). The launcher uses the classic `Application` API;
> migrate to `ApplicationV2` if targeting v14+.

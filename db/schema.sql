-- Battlemap Repository — Supabase Postgres schema
-- Run this in the Supabase SQL editor. Safe to re-run (idempotent where practical).

create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists pg_trgm;       -- trigram search on title

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
do $$ begin
  create type map_status as enum ('pending','approved','rejected','hidden','removed');
exception when duplicate_object then null; end $$;

do $$ begin
  create type grid_kind as enum ('grid','gridless','unknown');
exception when duplicate_object then null; end $$;

do $$ begin
  create type tag_category as enum ('terrain','setting','grid','feature','other');
exception when duplicate_object then null; end $$;

do $$ begin
  create type source_sort as enum ('top','hot','new');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- Sources: which subreddits to scrape and how
-- ---------------------------------------------------------------------------
create table if not exists sources (
  id           bigint generated always as identity primary key,
  subreddit    text not null,
  enabled      boolean not null default true,
  sort         source_sort not null default 'top',
  time_filter  text not null default 'month',   -- for 'top': hour|day|week|month|year|all
  min_score    int not null default 0,
  last_run_at  timestamptz,
  unique (subreddit, sort)                       -- allow e.g. both top and hot per subreddit
);

-- ---------------------------------------------------------------------------
-- Maps
-- ---------------------------------------------------------------------------
create table if not exists maps (
  id               uuid primary key default gen_random_uuid(),
  reddit_post_id   text not null unique,
  source_subreddit text not null,
  title            text not null,
  reddit_author    text,
  permalink        text not null,          -- https://reddit.com/...
  image_key        text,                   -- R2 object key (full image)
  thumb_key        text,                   -- R2 object key (thumbnail)
  image_url        text,                   -- public R2 URL (full)
  thumb_url        text,                   -- public R2 URL (thumb)
  width            int,
  height           int,
  file_size        bigint,
  phash            text,                   -- perceptual hash (hex) for dedupe
  grid_type        grid_kind not null default 'unknown',
  grid_size        int,                    -- pixels per square, if known
  dimensions       text,                   -- e.g. "30x20"
  description      text,
  score            int default 0,          -- reddit upvotes at scrape time
  status           map_status not null default 'pending',
  created_utc      timestamptz,            -- original reddit post time
  scraped_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index if not exists maps_status_idx        on maps (status);
create index if not exists maps_created_utc_idx    on maps (created_utc desc);
create index if not exists maps_source_idx         on maps (source_subreddit);
create index if not exists maps_phash_idx          on maps (phash);
create index if not exists maps_title_trgm_idx     on maps using gin (title gin_trgm_ops);

-- keep updated_at fresh
create or replace function set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end $$ language plpgsql;

drop trigger if exists maps_set_updated_at on maps;
create trigger maps_set_updated_at before update on maps
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Tags (many-to-many)
-- ---------------------------------------------------------------------------
create table if not exists tags (
  id        bigint generated always as identity primary key,
  name      text not null unique,
  category  tag_category not null default 'other'
);

create table if not exists map_tags (
  map_id  uuid not null references maps(id) on delete cascade,
  tag_id  bigint not null references tags(id) on delete cascade,
  primary key (map_id, tag_id)
);

create index if not exists map_tags_tag_idx on map_tags (tag_id);

-- ---------------------------------------------------------------------------
-- Seed sources
-- ---------------------------------------------------------------------------
-- min_score is kept for future use but is 0 by default: the RSS source doesn't expose
-- post score, and 'top' feeds are already sorted by popularity.
insert into sources (subreddit, sort, time_filter, min_score) values
  ('battlemaps', 'top', 'month', 0),
  ('dndmaps',    'top', 'month', 0),
  ('FantasyMaps','top', 'month', 0),
  ('battlemaps', 'hot', 'month', 0),
  ('dndmaps',    'hot', 'month', 0),
  ('FantasyMaps','hot', 'month', 0)
on conflict (subreddit, sort) do nothing;

-- ===========================================================================
-- Row Level Security
--   * anon (public web + Foundry):  read-only, approved maps only
--   * authenticated (admin):        full read/write
--   * scraper uses the service_role key, which bypasses RLS entirely
-- ===========================================================================
alter table maps      enable row level security;
alter table tags      enable row level security;
alter table map_tags  enable row level security;
alter table sources   enable row level security;

-- Public: only approved maps
drop policy if exists maps_public_read on maps;
create policy maps_public_read on maps
  for select using ( status = 'approved' );

-- Admin: full access to maps
drop policy if exists maps_admin_all on maps;
create policy maps_admin_all on maps
  for all to authenticated using ( true ) with check ( true );

-- Tags / map_tags readable by everyone (harmless), writable by admin
drop policy if exists tags_public_read on tags;
create policy tags_public_read on tags for select using ( true );
drop policy if exists tags_admin_all on tags;
create policy tags_admin_all on tags for all to authenticated using ( true ) with check ( true );

drop policy if exists map_tags_public_read on map_tags;
create policy map_tags_public_read on map_tags for select using ( true );
drop policy if exists map_tags_admin_all on map_tags;
create policy map_tags_admin_all on map_tags for all to authenticated using ( true ) with check ( true );

-- Sources: admin only (no public read needed)
drop policy if exists sources_admin_all on sources;
create policy sources_admin_all on sources for all to authenticated using ( true ) with check ( true );

-- Convenience view: approved maps with aggregated tags (handy for the gallery/Foundry)
create or replace view approved_maps as
  select m.*,
         coalesce(
           (select array_agg(t.name order by t.name)
              from map_tags mt join tags t on t.id = mt.tag_id
             where mt.map_id = m.id), '{}') as tags
    from maps m
   where m.status = 'approved';

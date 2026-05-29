-- Migration: allow multiple sort strategies per subreddit (e.g. top + hot),
-- then seed a 'hot' source for each existing subreddit.
-- Run this once in the Supabase SQL editor.

-- Replace UNIQUE(subreddit) with UNIQUE(subreddit, sort).
alter table sources drop constraint if exists sources_subreddit_key;
alter table sources add constraint sources_subreddit_sort_key unique (subreddit, sort);

-- Add a 'hot' source alongside the existing 'top' ones. 'hot' surfaces currently
-- rising posts, so each scrape brings genuinely new maps (top/month goes stale).
insert into sources (subreddit, sort, time_filter, min_score) values
  ('battlemaps',  'hot', 'month', 0),
  ('dndmaps',     'hot', 'month', 0),
  ('FantasyMaps', 'hot', 'month', 0)
on conflict (subreddit, sort) do nothing;

-- Migration: record each map's "scale" so non-tactical maps can be filtered/rejected.
--   battlemap = tactical encounter map (place tokens & fight)
--   region    = overland / regional / country / city-overview / hex map
--   world     = whole-world / continent map
-- Run once in the Supabase SQL editor.
alter table maps add column if not exists scale text;
create index if not exists maps_scale_idx on maps (scale);

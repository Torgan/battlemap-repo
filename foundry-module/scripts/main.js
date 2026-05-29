/**
 * Battlemap Repository — FoundryVTT module.
 *
 * Reads APPROVED maps from your Supabase project (PostgREST `approved_maps` view,
 * using the public anon key — RLS guarantees only approved maps are returned) and
 * lets the GM import any map as a Scene whose background is the public R2 image URL.
 */

const MODULE_ID = "battlemap-repo";

Hooks.once("init", () => {
  game.settings.register(MODULE_ID, "supabaseUrl", {
    name: "Supabase URL",
    hint: "e.g. https://yourproject.supabase.co",
    scope: "world",
    config: true,
    type: String,
    default: "",
  });
  game.settings.register(MODULE_ID, "supabaseAnonKey", {
    name: "Supabase anon key",
    hint: "The PUBLIC anon key (safe to use client-side; RLS restricts it to approved maps).",
    scope: "world",
    config: true,
    type: String,
    default: "",
  });
  game.settings.register(MODULE_ID, "defaultGridSize", {
    name: "Default grid size (px per square)",
    hint: "Used when a map has no detected grid size.",
    scope: "world",
    config: true,
    type: Number,
    default: 100,
  });
  game.settings.register(MODULE_ID, "sceneFolder", {
    name: "Imported scenes folder",
    hint: "Imported maps are placed in this Scenes folder (created if missing). Leave blank for no folder.",
    scope: "world",
    config: true,
    type: String,
    default: "Battlemap Repository",
  });

  // Serialize a map object into a URI-encoded JSON string for a data attribute.
  Handlebars.registerHelper("encodeMap", (map) => encodeURIComponent(JSON.stringify(map)));
});

// Add a launcher button to the Scenes directory footer.
Hooks.on("renderSceneDirectory", (app, html) => {
  const root = html instanceof HTMLElement ? html : html[0];
  if (!game.user.isGM || root.querySelector(".battlemap-repo-btn")) return;
  const btn = document.createElement("button");
  btn.className = "battlemap-repo-btn";
  btn.innerHTML = `<i class="fas fa-map"></i> Battlemap Repository`;
  btn.addEventListener("click", () => new BattlemapBrowser().render(true));
  (root.querySelector(".directory-footer") ?? root).prepend(btn);
});

async function fetchApprovedMaps() {
  const base = game.settings.get(MODULE_ID, "supabaseUrl").replace(/\/$/, "");
  const key = game.settings.get(MODULE_ID, "supabaseAnonKey");
  if (!base || !key) {
    ui.notifications.error("Battlemap Repo: set the Supabase URL and anon key in module settings.");
    return [];
  }
  const url = `${base}/rest/v1/approved_maps?select=id,title,image_url,thumb_url,width,height,grid_type,grid_size,dimensions,tags,source_subreddit,reddit_author,permalink&order=created_utc.desc&limit=1000`;
  const res = await fetch(url, { headers: { apikey: key, Authorization: `Bearer ${key}` } });
  if (!res.ok) {
    ui.notifications.error(`Battlemap Repo: fetch failed (${res.status}).`);
    return [];
  }
  return res.json();
}

// Derive pixels-per-square from "WxH" dimensions + the image width, when possible.
function computeGridSize(map, fallback) {
  if (map.grid_size) return map.grid_size;
  const m = map.dimensions && /^(\d+)\s*[x×]\s*(\d+)$/i.exec(map.dimensions);
  if (m && map.width) {
    const cols = parseInt(m[1], 10);
    if (cols > 0) return Math.max(10, Math.round(map.width / cols));
  }
  return fallback;
}

// Find (or create) the configured Scenes folder; null if the setting is blank.
async function getSceneFolder() {
  const name = (game.settings.get(MODULE_ID, "sceneFolder") || "").trim();
  if (!name) return null;
  let folder = game.folders.find((f) => f.type === "Scene" && f.name === name);
  if (!folder) folder = await Folder.create({ name, type: "Scene" });
  return folder;
}

async function importAsScene(map) {
  const defaultSize = game.settings.get(MODULE_ID, "defaultGridSize");
  const gridSize = computeGridSize(map, defaultSize);
  const folder = await getSceneFolder();

  const data = {
    name: map.title.slice(0, 100),
    folder: folder?.id ?? null,
    width: map.width ?? 4000,
    height: map.height ?? 3000,
    padding: 0.25,
    grid: {
      type: map.grid_type === "gridless" ? CONST.GRID_TYPES.GRIDLESS : CONST.GRID_TYPES.SQUARE,
      size: gridSize,
    },
  };

  // Foundry v14 moved the background image into the Level structure
  // (levels[].background.src); v12/v13 use the top-level background.src.
  const generation = game.release?.generation ?? 13;
  if (generation >= 14) {
    data.levels = [{ _id: "defaultLevel0000", name: "Level", background: { src: map.image_url } }];
    data.initialLevel = "defaultLevel0000";
  } else {
    data.background = { src: map.image_url };
  }

  const scene = await Scene.create(data);

  // Best-effort thumbnail (API differs across versions; never block the import on it).
  try {
    const t = await scene?.createThumbnail?.();
    if (t?.thumb) await scene.update({ thumb: t.thumb });
  } catch (_e) { /* ignore */ }

  ui.notifications.info(`Imported scene: ${map.title}`);
  return scene;
}

class BattlemapBrowser extends Application {
  static get defaultOptions() {
    return foundry.utils.mergeObject(super.defaultOptions, {
      id: "battlemap-repo-browser",
      title: "Battlemap Repository",
      template: `modules/${MODULE_ID}/templates/browser.hbs`,
      width: 900,
      height: 700,
      resizable: true,
      classes: ["battlemap-repo"],
    });
  }

  async getData() {
    const maps = await fetchApprovedMaps();
    return { maps, count: maps.length };
  }

  activateListeners(html) {
    super.activateListeners(html);
    const root = html instanceof HTMLElement ? html : html[0];

    const search = root.querySelector(".bm-search");
    search?.addEventListener("input", () => {
      const q = search.value.toLowerCase();
      root.querySelectorAll(".bm-card").forEach((card) => {
        const hay = (card.dataset.search ?? "").toLowerCase();
        card.style.display = hay.includes(q) ? "" : "none";
      });
    });

    root.querySelectorAll(".bm-import").forEach((el) => {
      el.addEventListener("click", async (ev) => {
        const button = ev.currentTarget;
        button.disabled = true;
        try {
          const card = ev.target.closest(".bm-card");
          const map = JSON.parse(decodeURIComponent(card.dataset.map));
          const scene = await importAsScene(map);
          this.close();          // close the browser once the scene is imported
          scene?.view?.();       // and jump to the freshly imported scene
        } catch (e) {
          button.disabled = false;
          ui.notifications.error(`Import failed: ${e.message}`);
          console.error(e);
        }
      });
    });
  }
}

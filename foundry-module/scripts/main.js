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

async function importAsScene(map) {
  const defaultSize = game.settings.get(MODULE_ID, "defaultGridSize");
  const gridSize = map.grid_size || defaultSize;
  const data = {
    name: map.title.slice(0, 100),
    background: { src: map.image_url },
    width: map.width ?? 4000,
    height: map.height ?? 3000,
    padding: 0.25,
    grid: {
      type: map.grid_type === "gridless" ? CONST.GRID_TYPES.GRIDLESS : CONST.GRID_TYPES.SQUARE,
      size: gridSize,
    },
  };
  const scene = await Scene.create(data);
  await scene?.createThumbnail?.().then((t) => scene.update({ thumb: t.thumb })).catch(() => {});
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
        const card = ev.target.closest(".bm-card");
        const map = JSON.parse(decodeURIComponent(card.dataset.map));
        await importAsScene(map);
      });
    });
  }
}

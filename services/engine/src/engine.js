// Session manager: one isolated Playwright context per session, loading only our bundled page.
import { createHash, randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { FONT_CSS, MAX_XML, PROFILE_BASE, RENDER_TIMEOUT_MS, openFontPage, read, renderPage } from "./drawio.js";

const require = createRequire(import.meta.url);
const KONVA_PATH = require.resolve("konva/konva.min.js");
// fabric's `exports` map hides dist/, so locate the package root via its (exported) package.json-adjacent entry.
const FABRIC_PATH = join(dirname(require.resolve("fabric")), "..", "dist", "index.min.js");
const BACKENDS = {
  konva: { lib: KONVA_PATH, dispatcher: fileURLToPath(new URL("./dispatcher.browser.js", import.meta.url)) },
  fabric: { lib: FABRIC_PATH, dispatcher: fileURLToPath(new URL("./dispatcher.fabric.js", import.meta.url)) },
};

// Campaign assets (spec 7.1): vendored, hash-checked at startup, handed to the page as data URLs (the page has no network).
const ASSETS = Object.fromEntries([["h7-headphones", 1000, 1000], ["halden-wordmark", 480, 120]].map(([id, width, height]) =>
  [id, { data_url: `data:image/svg+xml;base64,${read(`assets/${id}.svg`).toString("base64")}`, width, height }]));

// Uploaded assets (the "bring your own banner" path): the owner's two crops travel with the scene as PNG data URLs. They are
// validated here, before any browser context exists, and only the product path (uploads: true) may pass them.
const UPLOAD_ID = /^u-[0-9a-f]{12}-(brand_mark|product_image)$/;
const UPLOAD_PREFIX = "data:image/png;base64,";
const PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const MAX_UPLOADS = 2, MAX_UPLOAD_BYTES = 1_000_000, MAX_UPLOAD_DIM = 2048;
const invalidScene = (m) => Object.assign(new Error(m), { code: "INVALID_SCENE" });

function uploadedAssets(raw) {
  if (raw === undefined || raw === null) return {};
  if (typeof raw !== "object" || Array.isArray(raw)) throw invalidScene("uploaded assets must be an object");
  const ids = Object.keys(raw);
  for (const id of ids) if (!UPLOAD_ID.test(id)) throw invalidScene("bad uploaded asset id");
  if (ids.length > MAX_UPLOADS) throw invalidScene("too many uploaded assets");
  const out = {};
  for (const id of ids) {
    const url = raw[id];
    if (typeof url !== "string" || !url.startsWith(UPLOAD_PREFIX)) throw invalidScene("uploaded assets must be PNG data URLs");
    const b64 = url.slice(UPLOAD_PREFIX.length);
    if (b64.length > Math.ceil((MAX_UPLOAD_BYTES * 4) / 3) + 8) throw invalidScene("uploaded asset is too large");
    if (!/^[A-Za-z0-9+/]*={0,2}$/.test(b64)) throw invalidScene("uploaded asset is not valid base64");
    const buf = Buffer.from(b64, "base64");
    if (buf.length > MAX_UPLOAD_BYTES) throw invalidScene("uploaded asset is too large");
    if (buf.length < 24 || !buf.subarray(0, 8).equals(PNG_SIG) || buf.subarray(12, 16).toString("latin1") !== "IHDR") throw invalidScene("uploaded asset is not a PNG");
    const width = buf.readUInt32BE(16), height = buf.readUInt32BE(20);
    if (width < 1 || height < 1 || width > MAX_UPLOAD_DIM || height > MAX_UPLOAD_DIM) throw invalidScene(`uploaded asset size ${width}x${height} is outside 1..${MAX_UPLOAD_DIM}`);
    out[id] = { data_url: url, width, height }; // the header says how big it is; nothing is decoded here
  }
  return out;
}

const MAX_SESSIONS = 4;          // spec 19.2 parallel browser contexts
const ACTION_DEADLINE_MS = 5000; // per-action deadline (spec 6.5)
const MEASURE_TIMEOUT_MS = 10000; // an SVG measurement that hangs is abandoned and its context closed
const MAX_RENDERS = 2;          // concurrent draw.io renders (each a fresh browser context)
const SESSION_IDLE_MS = 10 * 60 * 1000; // a session nobody has touched for this long is reclaimed (abandoned visitors must not exhaust the cap)

// PUBLIC tool contract. Identical across drift variants by construction: it is a constant,
// never derived from private config, so an undocumented semantic change leaves the hash unchanged.
const COMMON_TOOLS = {
  inspect_scene: [], inspect_node: ["node_id"], observe_geometry: ["node_ids"], measure_node: ["node_id"],
  move_node: ["node_id", "x", "y"], resize_node: ["node_id", "width", "height"],
  set_style: ["node_id", "style"], clone_node: ["node_id", "new_id"],
  group_nodes: ["node_ids", "group_id"], ungroup_node: ["node_id"], export_scene: ["format"], finish: ["summary"],
};
export const PUBLIC_TOOL_SCHEMAS = {
  konva: { backend: "konva", tools: { ...COMMON_TOOLS, observe_fit: ["artboard_id", "limits"],
    create_artboard: ["artboard_id", "x", "y", "width", "height", "format", "safe", "sequence"], remove_artboard: ["artboard_id"],
    reparent_nodes: ["node_ids", "parent_id"], set_order: ["node_id", "z"], fit_image_contain: ["node_id", "x", "y", "width", "height"] } },
  // Fabric: same tool names; grouping is a documented capability error, not a silent no-op.
  fabric: { backend: "fabric", tools: { ...COMMON_TOOLS, observe_fit: ["artboard_id", "limits"],
    create_artboard: ["artboard_id", "x", "y", "width", "height", "format", "safe", "sequence"], remove_artboard: ["artboard_id"],
    reparent_nodes: ["node_ids", "parent_id"], set_order: ["node_id", "z"], fit_image_contain: ["node_id", "x", "y", "width", "height"] },
    unsupported: ["group_nodes", "ungroup_node"] },
};
export const PUBLIC_TOOL_SCHEMA = PUBLIC_TOOL_SCHEMAS.konva;
export const publicSchemaHash = (backend = "konva") =>
  createHash("sha256").update(JSON.stringify(PUBLIC_TOOL_SCHEMAS[backend])).digest("hex");

export class Engine {
  #browser = null;
  #sessions = new Map();
  #idleMs;
  #healthy = false;
  #onDisconnect = null;
  #renders = 0;
  #renderTimeoutMs;

  constructor({ idleMs = SESSION_IDLE_MS, renderTimeoutMs = RENDER_TIMEOUT_MS } = {}) {
    this.#idleMs = idleMs;
    this.#renderTimeoutMs = renderTimeoutMs;
  }

  get healthy() { return this.#healthy; }
  get sessionCount() { return this.#sessions.size; }
  onDisconnect(fn) { this.#onDisconnect = fn; }

  async start() {
    const args = ["--disable-dev-shm-usage", ...(process.env.OA_CHROMIUM_NO_SANDBOX === "1" ? ["--no-sandbox"] : [])];
    this.#browser = await chromium.launch({ headless: true, args });
    this.#healthy = true;
    // A crashed browser must be visible to health checks, not discovered request by request.
    this.#browser.on("disconnected", () => { this.#healthy = false; this.#onDisconnect?.(); });
  }

  async killBrowserForTest() {
    await this.#browser.close();
  }

  async close() {
    for (const id of [...this.#sessions.keys()]) await this.destroy(id);
    await this.#browser?.close();
  }

  // privateConfig is accepted ONLY from the evaluator path (server.js enforces the token).
  async create(scene, { owner, privateConfig, backend = "konva", uploads = false } = {}) {
    if (!BACKENDS[backend]) throw Object.assign(new Error(`unknown backend ${backend}`), { code: "INVALID_ARGUMENT" });
    let extra = {};
    if (scene && typeof scene === "object" && "assets" in scene) {
      if (!uploads) throw invalidScene("uploaded assets are not accepted here");
      extra = uploadedAssets(scene.assets);
      const { assets: _assets, ...rest } = scene;
      scene = rest;
    }
    await this.#reapIdle();
    if (this.#sessions.size >= MAX_SESSIONS) throw Object.assign(new Error("session limit"), { code: "LIMIT" });
    // Reserve the slot BEFORE the first await, so parallel creates cannot all pass the cap check.
    const id = randomUUID();
    const slot = { context: null, page: null, owner, touched: Date.now(), pending: true };
    this.#sessions.set(id, slot);
    try {
      const context = await this.#browser.newContext();
      slot.context = context;
      // Block every network request: local bundled assets only (spec 18.2).
      await context.route("**/*", (route) => route.abort());
      const page = await context.newPage();
      slot.page = page;
      await page.setContent('<!doctype html><html><body><div id="c"></div></body></html>');
      await page.addStyleTag({ content: FONT_CSS });
      await page.evaluate(async () => {
        await document.fonts.load('16px "Liberation Sans"'); await document.fonts.load('bold 16px "Liberation Sans"');
        await document.fonts.ready;
      });
      await page.addScriptTag({ path: BACKENDS[backend].lib });
      await page.addScriptTag({ path: BACKENDS[backend].dispatcher });
      let loaded;
      try {
        loaded = await page.evaluate(([sc, c, a]) => window.__engine.load(sc, c, a), [scene, privateConfig ?? null, { ...extra, ...ASSETS }]); // fixed assets always win over an upload
      } catch (e) {
        throw Object.assign(new Error(String(e.message).split("\n")[0].slice(0, 200)), { code: "INVALID_SCENE" });
      }
      slot.pending = false;
      return { session_id: id, backend, revision: loaded.revision, public_schema_hash: publicSchemaHash(backend) };
    } catch (e) {
      // Any failure frees the slot and the browser context; nothing half-built is left behind.
      this.#sessions.delete(id);
      await slot.context?.close().catch(() => {});
      throw e;
    }
  }

  async #reapIdle() {
    const now = Date.now();
    for (const [id, s] of this.#sessions) {
      if (!s.pending && now - s.touched > this.#idleMs) await this.destroy(id);
    }
  }

  #get(id, owner) {
    const s = this.#sessions.get(id);
    if (!s || s.pending || s.owner !== owner) throw Object.assign(new Error("no such session"), { code: "NOT_FOUND" });
    s.touched = Date.now();
    return s;
  }

  async act(id, owner, action) {
    const { page } = this.#get(id, owner);
    const run = page.evaluate((a) => window.__engine.dispatch(a), action);
    const timeout = new Promise((resolve) =>
      setTimeout(() => resolve({ ok: false, error: { code: "INFRA_TIMEOUT", message: "action deadline" } }), ACTION_DEADLINE_MS));
    return Promise.race([run, timeout]);
  }

  // Measure rendered WORLD geometry of elements in an SVG document, using the browser's own transform matrices (local bboxes are not world coordinates).
  // Evaluator route only. The document was validated by the API; this context is network-blocked, short-lived, and rejects obvious active content again.
  async measureSvg(svg, ids) {
    if (typeof svg !== "string" || svg.length > 200_000 || !Array.isArray(ids) || ids.length > 200 || !ids.every((i) => typeof i === "string" && i.length < 120)) {
      throw Object.assign(new Error("invalid measure request"), { code: "INVALID_ARGUMENT" });
    }
    if (/<\s*(script|foreignObject|iframe|object|embed)\b|\son[a-z]+\s*=/i.test(svg)) {
      throw Object.assign(new Error("active content is not allowed"), { code: "INVALID_ARGUMENT" });
    }
    const body = svg.replace(/^\s*<\?xml[^>]*\?>/, "");
    // The page is parsed as HTML, where a processing instruction ends at the first ">" and can smuggle live markup in.
    if (body.includes("<?")) {
      throw Object.assign(new Error("processing instructions are not allowed (active content)"), { code: "INVALID_ARGUMENT" });
    }
    // JavaScript is OFF in this context, so nothing in the document can run even if a filter above misses it; page.evaluate still works.
    const context = await this.#browser.newContext({ javaScriptEnabled: false });
    let timer;
    try {
      await context.route("**/*", (route) => route.abort());
      const page = await context.newPage();
      const work = (async () => {
        await page.setContent(`<!doctype html><html><body style="margin:0">${body}</body></html>`);
        return page.evaluate((wanted) => {
        const root = document.querySelector("svg");
        if (!root) return { error: "no <svg> root" };
        const inv = root.getScreenCTM().inverse();
        const pt = root.createSVGPoint();
        return wanted.map((id) => {
          const el = document.getElementById(id);
          if (!el || typeof el.getBBox !== "function") return { id, missing: true };
          const b = el.getBBox();
          const m = el.getScreenCTM();
          const xs = [];
          const ys = [];
          for (const [x, y] of [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]]) {
            pt.x = x; pt.y = y;
            const w = pt.matrixTransform(m).matrixTransform(inv);
            xs.push(w.x); ys.push(w.y);
          }
          const x0 = Math.min(...xs), y0 = Math.min(...ys);
          return { id, x: x0, y: y0, width: Math.max(...xs) - x0, height: Math.max(...ys) - y0 };
        });
        }, ids);
      })();
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(Object.assign(new Error("measurement timed out"), { code: "TIMEOUT" })), MEASURE_TIMEOUT_MS);
      });
      return await Promise.race([work, timeout]);
    } finally {
      clearTimeout(timer);
      await context.close();
    }
  }

  // Render and measure one draw.io page (product route). The API refuses hostile files before calling this; the context
  // is fresh, network-blocked and closed afterwards whatever happens.
  async renderDrawio(xml, { wantPng = true, wantSvg = false } = {}) {
    if (typeof xml !== "string" || xml.length > MAX_XML || !xml.startsWith("<mxfile")) {
      throw Object.assign(new Error("invalid draw.io page"), { code: "INVALID_ARGUMENT" });
    }
    if (this.#renders >= MAX_RENDERS) throw Object.assign(new Error("render limit"), { code: "LIMIT" });
    this.#renders += 1;
    let timer;
    let opened = null;
    try {
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(Object.assign(new Error("render timed out"), { code: "TIMEOUT" })), this.#renderTimeoutMs);
      });
      const work = (async () => {
        opened = openFontPage(this.#browser);
        return renderPage(await opened, xml, { wantPng, wantSvg });
      })();
      const out = await Promise.race([work, timeout]);
      return { ...out, profile: { ...PROFILE_BASE, chromium: this.#browser.version() } };
    } catch (e) {
      if (e.code) throw e;
      throw Object.assign(new Error(String(e.message).split("\n")[0].slice(0, 200)), { code: "RENDER_FAILED" });
    } finally {
      clearTimeout(timer);
      // close the context here, whatever the race's outcome: an abandoned render must not keep a live page behind
      if (opened) await opened.then(({ context }) => context.close(), () => {}).catch(() => {});
      this.#renders -= 1;
    }
  }

  contextCountForTest() {
    return this.#browser.contexts().length;
  }

  async textWidthForTest(family, text, { size = 12, weight = "normal" } = {}) {
    const { context, page } = await openFontPage(this.#browser);
    try {
      return await page.evaluate(([f, t, sz, w]) => {
        const c = document.createElement("canvas").getContext("2d");
        c.font = `${w} ${sz}px "${f}"`;
        return c.measureText(t).width;
      }, [family, text, size, weight]);
    } finally {
      await context.close();
    }
  }

  async sessionTextWidthForTest(id, owner, font, text) {
    return this.#get(id, owner).page.evaluate(([f, t]) => {
      const c = document.createElement("canvas").getContext("2d");
      c.font = f;
      return c.measureText(t).width;
    }, [font, text]);
  }

  // Raw native attrs for the private verifier (evaluator route only).
  async nativeState(id, owner) {
    return this.#get(id, owner).page.evaluate(() => window.__engine.nativeState());
  }

  // Agent-facing delete: only the session's owner may end it.
  async destroyOwned(id, owner) {
    this.#get(id, owner);
    await this.destroy(id);
  }

  async destroy(id) {
    const s = this.#sessions.get(id);
    if (!s) return;
    this.#sessions.delete(id);
    await s.context?.close().catch(() => {});   // already-gone contexts must not break shutdown
  }
}

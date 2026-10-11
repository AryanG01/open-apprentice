// Session manager: one isolated Playwright context per session, loading only our bundled page.
import { createHash, randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const require = createRequire(import.meta.url);
const KONVA_PATH = require.resolve("konva/konva.min.js");
// fabric's `exports` map hides dist/, so locate the package root via its (exported) package.json-adjacent entry.
const FABRIC_PATH = join(dirname(require.resolve("fabric")), "..", "dist", "index.min.js");
const BACKENDS = {
  konva: { lib: KONVA_PATH, dispatcher: fileURLToPath(new URL("./dispatcher.browser.js", import.meta.url)) },
  fabric: { lib: FABRIC_PATH, dispatcher: fileURLToPath(new URL("./dispatcher.fabric.js", import.meta.url)) },
};

const MAX_SESSIONS = 4;          // spec 19.2 parallel browser contexts
const ACTION_DEADLINE_MS = 5000; // per-action deadline (spec 6.5)

// PUBLIC tool contract. Identical across drift variants by construction: it is a constant,
// never derived from private config, so an undocumented semantic change leaves the hash unchanged.
const COMMON_TOOLS = {
  inspect_scene: [], inspect_node: ["node_id"], observe_geometry: ["node_ids"], measure_node: ["node_id"],
  move_node: ["node_id", "x", "y"], resize_node: ["node_id", "width", "height"],
  set_style: ["node_id", "style"], clone_node: ["node_id", "new_id"],
  group_nodes: ["node_ids", "group_id"], ungroup_node: ["node_id"], export_scene: ["format"], finish: ["summary"],
};
export const PUBLIC_TOOL_SCHEMAS = {
  konva: { backend: "konva", tools: COMMON_TOOLS },
  // Fabric: same tool names; grouping is a documented capability error, not a silent no-op.
  fabric: { backend: "fabric", tools: COMMON_TOOLS, unsupported: ["group_nodes", "ungroup_node"] },
};
export const PUBLIC_TOOL_SCHEMA = PUBLIC_TOOL_SCHEMAS.konva;
export const publicSchemaHash = (backend = "konva") =>
  createHash("sha256").update(JSON.stringify(PUBLIC_TOOL_SCHEMAS[backend])).digest("hex");

export class Engine {
  #browser = null;
  #sessions = new Map();

  async start() {
    this.#browser = await chromium.launch({ headless: true, args: process.env.OA_CHROMIUM_NO_SANDBOX === "1" ? ["--no-sandbox"] : [] });
  }

  async close() {
    for (const id of [...this.#sessions.keys()]) await this.destroy(id);
    await this.#browser?.close();
  }

  // privateConfig is accepted ONLY from the evaluator path (server.js enforces the token).
  async create(scene, { owner, privateConfig, backend = "konva" } = {}) {
    if (!BACKENDS[backend]) throw Object.assign(new Error(`unknown backend ${backend}`), { code: "INVALID_ARGUMENT" });
    if (this.#sessions.size >= MAX_SESSIONS) throw Object.assign(new Error("session limit"), { code: "LIMIT" });
    const context = await this.#browser.newContext();
    // Block every network request: local bundled assets only (spec 18.2).
    await context.route("**/*", (route) => route.abort());
    const page = await context.newPage();
    await page.setContent('<!doctype html><html><body><div id="c"></div></body></html>');
    await page.addScriptTag({ path: BACKENDS[backend].lib });
    await page.addScriptTag({ path: BACKENDS[backend].dispatcher });
    let loaded;
    try {
      loaded = await page.evaluate(([s, c]) => window.__engine.load(s, c), [scene, privateConfig ?? null]);
    } catch (e) {
      await context.close();
      throw Object.assign(new Error(String(e.message).split("\n")[0].slice(0, 200)), { code: "INVALID_SCENE" });
    }
    const id = randomUUID();
    this.#sessions.set(id, { context, page, owner });
    return { session_id: id, backend, revision: loaded.revision, public_schema_hash: publicSchemaHash(backend) };
  }

  #get(id, owner) {
    const s = this.#sessions.get(id);
    if (!s || s.owner !== owner) throw Object.assign(new Error("no such session"), { code: "NOT_FOUND" });
    return s;
  }

  async act(id, owner, action) {
    const { page } = this.#get(id, owner);
    const run = page.evaluate((a) => window.__engine.dispatch(a), action);
    const timeout = new Promise((resolve) =>
      setTimeout(() => resolve({ ok: false, error: { code: "INFRA_TIMEOUT", message: "action deadline" } }), ACTION_DEADLINE_MS));
    return Promise.race([run, timeout]);
  }

  // Raw native attrs for the private verifier (evaluator route only).
  async nativeState(id, owner) {
    return this.#get(id, owner).page.evaluate(() => window.__engine.nativeState());
  }

  async destroy(id) {
    const s = this.#sessions.get(id);
    if (!s) return;
    this.#sessions.delete(id);
    await s.context.close().catch(() => {});   // already-gone contexts must not break shutdown
  }
}

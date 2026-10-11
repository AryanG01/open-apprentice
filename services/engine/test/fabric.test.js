import { after, afterEach, before, test } from "node:test";
import assert from "node:assert/strict";
import { Engine, publicSchemaHash } from "../src/engine.js";

const SCENE = {
  canvas: { width: 800, height: 500 },
  nodes: [
    { id: "a", type: "rect", x: 100, y: 100, width: 50, height: 40, fill: "red" },
    { id: "b", type: "rect", x: 300, y: 300, width: 60, height: 20, fill: "blue", scaleX: 2 },
  ],
};
let eng; const live = [];
before(async () => { eng = new Engine(); await eng.start(); });
after(async () => { await eng.close(); });
afterEach(async () => { while (live.length) await eng.destroy(live.pop()); });
const mk = async (privateConfig, scene = SCENE) => { const s = await eng.create(scene, { owner: "u", backend: "fabric", privateConfig }); live.push(s.session_id); return s; };
const act = (s, tool, args, extra = {}) => eng.act(s.session_id, "u", { tool, args, ...extra });

test("real Fabric geometry: bounds include scale; measure_node uses the native canvas frame", async () => {
  const s = await mk();
  const b = (await act(s, "observe_geometry", { node_ids: ["a", "b"] })).result.bounds;
  assert.deepEqual(b[0], { id: "a", left: 100, top: 100, width: 50, height: 40 });
  assert.deepEqual(b[1], { id: "b", left: 300, top: 300, width: 120, height: 20 });
  assert.equal((await act(s, "measure_node", { node_id: "b" })).result.frame, "canvas");
});

test("move_node sets left/top; async clone works and keeps size", async () => {
  const s = await mk();
  await act(s, "move_node", { node_id: "a", x: 10, y: 20 }, { expected_revision: s.revision });
  const c = await act(s, "clone_node", { node_id: "a", new_id: "a2" }, { expected_revision: s.revision + 1 });
  assert.equal(c.ok, true);
  await act(s, "move_node", { node_id: "a2", x: 200, y: 50 }, { expected_revision: s.revision + 2 });
  const bb = (await act(s, "observe_geometry", { node_ids: ["a", "a2"] })).result.bounds;
  assert.deepEqual([bb[0].left, bb[0].top, bb[1].left, bb[1].top, bb[1].width], [10, 20, 200, 50, 50]);
  const n = await eng.nativeState(s.session_id, "u");
  assert.equal(n.nodes.length, 3); assert.equal(n.nodes[0].originX, "left");
});

test("grouping and grouped scenes are explicit capability errors, not silent no-ops", async () => {
  const s = await mk();
  assert.equal((await act(s, "group_nodes", { node_ids: ["a"], group_id: "g" }, { expected_revision: s.revision })).error.code, "UNSUPPORTED_CAPABILITY");
  await assert.rejects(eng.create({ canvas: SCENE.canvas, nodes: [{ id: "g", type: "group" }] }, { owner: "u", backend: "fabric" }), { code: "INVALID_SCENE" });
});

test("private center-origin drift changes where move_node puts the object; public schema hash is unchanged", async () => {
  const n = await mk(); const d = await mk({ move_origin: "center" });
  await act(n, "move_node", { node_id: "a", x: 200, y: 200 }, { expected_revision: n.revision });
  await act(d, "move_node", { node_id: "a", x: 200, y: 200 }, { expected_revision: d.revision });
  const bn = (await act(n, "observe_geometry", { node_ids: ["a"] })).result.bounds[0];
  const bd = (await act(d, "observe_geometry", { node_ids: ["a"] })).result.bounds[0];
  assert.deepEqual([bn.left, bn.top], [200, 200]);
  assert.deepEqual([bd.left, bd.top], [200 - 25, 200 - 20]);   // x,y interpreted as the CENTER
  assert.equal(n.public_schema_hash, d.public_schema_hash);
});

test("backend identity is public: konva and fabric schema hashes differ", () => {
  assert.notEqual(publicSchemaHash("konva"), publicSchemaHash("fabric"));
});

test("unknown tools and bad arguments rejected", async () => {
  const s = await mk();
  assert.equal((await act(s, "eval", {})).error.code, "UNSUPPORTED_CAPABILITY");
  assert.equal((await act(s, "move_node", { node_id: "a", x: NaN, y: 1 }, { expected_revision: s.revision })).error.code, "INVALID_ARGUMENT");
  assert.equal((await act(s, "export_scene", { format: "svg" })).error.code, "UNSUPPORTED_CAPABILITY");
});

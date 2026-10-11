import { after, afterEach, before, test } from "node:test";
import assert from "node:assert/strict";
import { Engine, publicSchemaHash } from "../src/engine.js";

const SCENE = {
  canvas: { width: 800, height: 500 },
  nodes: [
    { id: "g", type: "group", x: 40, y: 20, scaleX: 2, scaleY: 2 },
    { id: "a", type: "rect", parent: "g", x: 5, y: 5, width: 10, height: 10, fill: "red" },
    { id: "b", type: "rect", x: 300, y: 300, width: 50, height: 40, fill: "blue" },
  ],
};
let eng;
before(async () => { eng = new Engine(); await eng.start(); });
after(async () => { await eng.close(); });

const live = [];
const mk = async (privateConfig) => {
  const s = await eng.create(SCENE, { owner: "u1", privateConfig });
  live.push(s.session_id);
  return s;
};
afterEach(async () => { while (live.length) await eng.destroy(live.pop()); });
const act = (s, tool, args, extra = {}) => eng.act(s.session_id, "u1", { tool, args, ...extra });

test("observe_geometry reports real rendered world bounds incl. parent scale", async () => {
  const s = await mk();
  const r = await act(s, "observe_geometry", { node_ids: ["a", "b"] });
  assert.deepEqual(r.result.bounds[0], { id: "a", left: 50, top: 30, width: 20, height: 20 });
  assert.deepEqual(r.result.bounds[1], { id: "b", left: 300, top: 300, width: 50, height: 40 });
});

test("mutations bump revision and stale writes conflict", async () => {
  const s = await mk();
  const ok = await act(s, "move_node", { node_id: "b", x: 10, y: 20 }, { expected_revision: s.revision });
  assert.equal(ok.ok, true); assert.equal(ok.revision, s.revision + 1);
  const stale = await act(s, "move_node", { node_id: "b", x: 1, y: 1 }, { expected_revision: s.revision });
  assert.equal(stale.error.code, "SCENE_REVISION_CONFLICT");
  const native = await eng.nativeState(s.session_id, "u1");
  assert.equal(native.nodes.find((n) => n.id === "b").x, 10);
});

test("retried clone with same action_id does not create a second object", async () => {
  const s = await mk();
  const a1 = await act(s, "clone_node", { node_id: "b", new_id: "b2" }, { expected_revision: s.revision, action_id: "k1" });
  const a2 = await act(s, "clone_node", { node_id: "b", new_id: "b2" }, { expected_revision: s.revision, action_id: "k1" });
  assert.equal(a1.ok, true); assert.equal(a2.replayed, true);
  const n = (await eng.nativeState(s.session_id, "u1")).nodes.filter((x) => x.id.startsWith("b"));
  assert.equal(n.length, 2);
});

test("unknown tools, bad args, and prototype names are rejected", async () => {
  const s = await mk();
  for (const t of ["eval", "constructor", "__proto__", "toString"]) {
    assert.equal((await act(s, t, {})).error.code, "UNSUPPORTED_CAPABILITY");
  }
  const bad = await act(s, "move_node", { node_id: "b", x: Infinity, y: 0 }, { expected_revision: s.revision });
  assert.equal(bad.error.code, "INVALID_ARGUMENT");
  assert.equal((await act(s, "export_scene", { format: "svg" })).error.code, "UNSUPPORTED_CAPABILITY");
});

test("sessions are owner-scoped", async () => {
  const s = await mk();
  await assert.rejects(eng.act(s.session_id, "intruder", { tool: "inspect_scene" }), { code: "NOT_FOUND" });
});

test("drift: private world-frame move changes behaviour, public schema hash does not", async () => {
  const before = publicSchemaHash();
  const normal = await mk();
  const drifted = await mk({ move_frame: "world" });
  await act(normal, "move_node", { node_id: "a", x: 100, y: 100 }, { expected_revision: normal.revision });
  await act(drifted, "move_node", { node_id: "a", x: 100, y: 100 }, { expected_revision: drifted.revision });
  const wn = (await act(normal, "observe_geometry", { node_ids: ["a"] })).result.bounds[0];
  const wd = (await act(drifted, "observe_geometry", { node_ids: ["a"] })).result.bounds[0];
  assert.deepEqual([wn.left, wn.top], [40 + 100 * 2, 20 + 100 * 2]); // local 100 inside scaled group
  assert.deepEqual([wd.left, wd.top], [100, 100]);                    // world 100 honoured
  assert.equal(normal.public_schema_hash, drifted.public_schema_hash);
  assert.equal(before, publicSchemaHash());
});

test("group_nodes preserves world placement", async () => {
  const s = await mk();
  const before = (await act(s, "observe_geometry", { node_ids: ["b"] })).result.bounds[0];
  await act(s, "group_nodes", { node_ids: ["b"], group_id: "g2" }, { expected_revision: s.revision });
  const after = (await act(s, "observe_geometry", { node_ids: ["b"] })).result.bounds[0];
  assert.deepEqual(after, before);
});

test("session cap is enforced", async () => {
  for (let i = 0; i < 4; i++) await mk();
  await assert.rejects(eng.create(SCENE, { owner: "u1" }), { code: "LIMIT" });
});

test("drift: private center-anchor move on a FLAT Konva scene; public schema hash unchanged", async () => {
  const n = await mk(); const d = await mk({ move_anchor: "center" });
  await act(n, "move_node", { node_id: "b", x: 200, y: 200 }, { expected_revision: n.revision });
  await act(d, "move_node", { node_id: "b", x: 200, y: 200 }, { expected_revision: d.revision });
  const bn = (await act(n, "observe_geometry", { node_ids: ["b"] })).result.bounds[0];
  const bd = (await act(d, "observe_geometry", { node_ids: ["b"] })).result.bounds[0];
  assert.deepEqual([bn.left, bn.top], [200, 200]);
  assert.deepEqual([bd.left, bd.top], [200 - 25, 200 - 20]);
  assert.equal(n.public_schema_hash, d.public_schema_hash);
});

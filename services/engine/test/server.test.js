import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { Engine } from "../src/engine.js";
import { buildServer } from "../src/server.js";

const SCENE = { canvas: { width: 100, height: 100 }, nodes: [{ id: "r", type: "rect", x: 0, y: 0, width: 10, height: 10, fill: "red" }] };
let eng, app, off;
before(async () => { eng = new Engine(); await eng.start(); app = buildServer(eng, { evaluatorToken: "tok-123" }); off = buildServer(eng, { evaluatorToken: undefined }); });
after(async () => { await eng.close(); });

test("agent route rejects private config outright", async () => {
  const r = await app.inject({ method: "POST", url: "/sessions", payload: { scene: SCENE, owner: "u", private_config: { move_frame: "world" } } });
  assert.equal(r.statusCode, 403);
});

test("internal routes need the evaluator token; disabled entirely without one", async () => {
  const payload = { scene: SCENE, owner: "u", private_config: { move_frame: "world" } };
  assert.equal((await app.inject({ method: "POST", url: "/internal/sessions", payload })).statusCode, 403);
  assert.equal((await app.inject({ method: "POST", url: "/internal/sessions", payload, headers: { "x-evaluator-token": "wrong" } })).statusCode, 403);
  assert.equal((await off.inject({ method: "POST", url: "/internal/sessions", payload, headers: { "x-evaluator-token": "tok-123" } })).statusCode, 404);
  const ok = await app.inject({ method: "POST", url: "/internal/sessions", payload, headers: { "x-evaluator-token": "tok-123" } });
  assert.equal(ok.statusCode, 200);
  await eng.destroy(ok.json().session_id);
});

test("full agent flow over HTTP; native state is not reachable from the agent surface", async () => {
  const c = (await app.inject({ method: "POST", url: "/sessions", payload: { scene: SCENE, owner: "u" } })).json();
  const a = await app.inject({ method: "POST", url: `/sessions/${c.session_id}/actions`, payload: { owner: "u", tool: "move_node", args: { node_id: "r", x: 5, y: 6 }, expected_revision: c.revision } });
  assert.equal(a.json().ok, true);
  assert.equal((await app.inject({ method: "GET", url: `/sessions/${c.session_id}/native?owner=u` })).statusCode, 404);
  assert.equal((await app.inject({ method: "GET", url: `/internal/sessions/${c.session_id}/native?owner=u` })).statusCode, 403);
  const n = await app.inject({ method: "GET", url: `/internal/sessions/${c.session_id}/native?owner=u`, headers: { "x-evaluator-token": "tok-123" } });
  assert.equal(n.json().nodes[0].x, 5);
  const wrongOwner = await app.inject({ method: "POST", url: `/sessions/${c.session_id}/actions`, payload: { owner: "x", tool: "inspect_scene" } });
  assert.equal(wrongOwner.statusCode, 404);
  await app.inject({ method: "DELETE", url: `/sessions/${c.session_id}` });
});

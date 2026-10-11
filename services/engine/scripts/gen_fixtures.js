// Drives the REAL engine through public tools and dumps raw native state for the Python verifier.
// Not a solution oracle: it just replays one hand-written parent-local procedure (fixture origin).
import { writeFileSync } from "node:fs";
import { Engine } from "../src/engine.js";

const SCENE = {
  canvas: { width: 800, height: 500 },
  nodes: [
    { id: "g", type: "group", x: 40, y: 20, scaleX: 2, scaleY: 2 },
    { id: "a", type: "rect", parent: "g", x: 0, y: 50, width: 50, height: 20, fill: "red" },
    { id: "b", type: "rect", parent: "g", x: 100, y: 55, width: 30, height: 20, fill: "red" },
    { id: "c", type: "rect", parent: "g", x: 200, y: 60, width: 40, height: 20, fill: "red" },
    { id: "d", type: "rect", x: 600, y: 50, width: 50, height: 40, fill: "blue" },
  ],
};
const GAP = 24, LEFT = 80, TOP = 120, IDS = ["a", "b", "c"];

// Procedure written for the documented contract: move_node is PARENT-LOCAL.
async function runLocalFramePlan(eng, s) {
  let worldCursor = LEFT, rev = s.revision, n = 0;
  for (const id of IDS) {
    const m = (await eng.act(s.session_id, "u", { tool: "measure_node", args: { node_id: id } })).result;
    const localX = (worldCursor - 40) / 2, localY = (TOP - 20) / 2; // invert parent scale/offset
    const r = await eng.act(s.session_id, "u", { tool: "move_node", args: { node_id: id, x: localX, y: localY }, expected_revision: rev, action_id: `m${n++}` });
    rev = r.revision;
    worldCursor += m.width * 2 + GAP; // parent group scale is 2 (read from the scene above)
  }
}

const eng = new Engine();
await eng.start();
const out = {};
for (const [name, cfg] of [["ok_local_frame", null], ["drifted_world_frame", { move_frame: "world" }]]) {
  const s = await eng.create(SCENE, { owner: "u", privateConfig: cfg });
  const initial = await eng.nativeState(s.session_id, "u");
  await runLocalFramePlan(eng, s);
  out[name] = { initial, final: await eng.nativeState(s.session_id, "u") };
  await eng.destroy(s.session_id);
}
await eng.close();
writeFileSync(new URL("../../../tests/integration/fixtures/konva_gap_row.json", import.meta.url), JSON.stringify(out, null, 1));
console.log("wrote fixtures", Object.keys(out));

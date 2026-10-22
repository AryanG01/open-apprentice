import { after, afterEach, before, test } from "node:test";
import assert from "node:assert/strict";
import { Engine } from "../src/engine.js";

const TEXT_SCENE = {
  canvas: { width: 1080, height: 1920 },
  nodes: [{ id: "r", type: "rect", x: 0, y: 0, width: 10, height: 10, fill: "#000" }],
};
let eng;
before(async () => { eng = new Engine(); await eng.start(); });
after(async () => { await eng.close(); });
const live = [];
const mk = async (scene) => {
  const s = await eng.create(scene, { owner: "u1" });
  live.push(s.session_id);
  return s;
};
afterEach(async () => { while (live.length) await eng.destroy(live.pop()); });

test("session pages measure with the vendored font", async () => {
  const s = await mk(TEXT_SCENE);
  const inSession = await eng.sessionTextWidthForTest(s.session_id, "u1", 'bold 72px "Liberation Sans"', "Silence the city.");
  const reference = await eng.textWidthForTest("OA Liberation Probe", "Silence the city.", { size: 72, weight: "bold" });
  assert.ok(Math.abs(inSession - reference) < 0.01, `${inSession} vs ${reference}`);
});

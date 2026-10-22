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

const SAFE = { top: 220, right: 72, bottom: 220, left: 72 };
const STORY = {
  canvas: { width: 1080, height: 1920 },
  nodes: [
    { id: "story-1", type: "artboard", x: 0, y: 0, width: 1080, height: 1920, format: "9:16", safe: SAFE, sequence: 1 },
    { id: "bg", type: "rect", parent: "story-1", role: "background", x: 0, y: 0, width: 1080, height: 1920, fill: "#1d1240", z: 0 },
    { id: "logo", type: "image", parent: "story-1", role: "brand_mark", asset: "halden-wordmark", crop: null, focal: { x: 240, y: 60 }, x: 72, y: 220, width: 240, height: 60, z: 1 },
    { id: "hero", type: "image", parent: "story-1", role: "product_image", asset: "h7-headphones", crop: null, focal: { x: 500, y: 520 }, x: 180, y: 320, width: 720, height: 720, z: 2 },
    { id: "head", type: "text", parent: "story-1", role: "headline", text: "Silence the city.", fontFamily: "Liberation Sans", fontSize: 72, fontStyle: "bold", lineHeight: 1.1, align: "left", wrap: "word", fill: "#fdfbff", x: 72, y: 1080, width: 936, height: 160, z: 3 },
    { id: "cta", type: "group", parent: "story-1", role: "cta", link: "https://halden.example/h7-sale", x: 72, y: 1360, z: 4 },
    { id: "cta-plate", type: "shape", parent: "cta", x: 0, y: 0, width: 936, height: 112, fill: "#ffd23f", cornerRadius: 16, z: 0 },
    { id: "cta-label", type: "text", parent: "cta", text: "Shop now", fontFamily: "Liberation Sans", fontSize: 44, fontStyle: "bold", lineHeight: 1.1, align: "center", wrap: "word", fill: "#1d1240", x: 0, y: 30, width: 936, height: 52, z: 1 },
  ],
};
const FIELDS = ["id", "type", "parent", "role", "x", "y", "width", "height", "z", "format", "safe", "sequence", "fill",
  "cornerRadius", "text", "fontFamily", "fontSize", "fontStyle", "lineHeight", "align", "wrap", "asset", "crop", "focal", "link"];

test("story scene round-trips through nativeState", async () => {
  const s = await mk(STORY);
  const native = await eng.nativeState(s.session_id, "u1");
  for (const want of STORY.nodes) {
    const got = native.nodes.find((n) => n.id === want.id);
    assert.ok(got, want.id);
    for (const f of FIELDS) if (f in want) assert.deepEqual(got[f], want[f], `${want.id}.${f}`);
  }
});

test("unknown asset id fails INVALID_SCENE", async () => {
  const bad = structuredClone(STORY);
  bad.nodes.find((n) => n.id === "hero").asset = "nope";
  await assert.rejects(eng.create(bad, { owner: "u1" }), (e) => e.code === "INVALID_SCENE" && /unknown asset nope/.test(e.message));
});

test("image keeps no crop and its aspect", async () => {
  const s = await mk(STORY);
  const hero = (await eng.nativeState(s.session_id, "u1")).nodes.find((n) => n.id === "hero");
  assert.equal(hero.crop, null);
  assert.equal(hero.width, 720);
  assert.equal(hero.height, 720);
  assert.equal(hero.type, "image");
});

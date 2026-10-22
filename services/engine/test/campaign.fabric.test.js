import { after, afterEach, before, test } from "node:test";
import assert from "node:assert/strict";
import { Engine } from "../src/engine.js";

const SAFE = { top: 220, right: 72, bottom: 220, left: 72 };
const STORY = {
  canvas: { width: 1080, height: 1920 },
  nodes: [
    { id: "story-1", type: "artboard", x: 0, y: 0, width: 1080, height: 1920, format: "9:16", safe: SAFE, sequence: 1 },
    { id: "bg", type: "rect", parent: "story-1", role: "background", x: 0, y: 0, width: 1080, height: 1920, fill: "#1d1240", z: 0 },
    { id: "logo", type: "image", parent: "story-1", role: "brand_mark", asset: "halden-wordmark", crop: null, focal: { x: 240, y: 60 }, x: 72, y: 220, width: 240, height: 60, z: 1 },
    { id: "hero", type: "image", parent: "story-1", role: "product_image", asset: "h7-headphones", crop: null, focal: { x: 500, y: 520 }, x: 180, y: 320, width: 720, height: 720, z: 2 },
    { id: "head", type: "text", parent: "story-1", role: "headline", text: "Silence the city.", fontFamily: "Liberation Sans", fontSize: 72, fontStyle: "bold", lineHeight: 1.1, align: "left", wrap: "word", fill: "#fdfbff", x: 72, y: 1080, width: 936, height: 160, z: 3 },
    { id: "price", type: "text", parent: "story-1", role: "price", text: "Now $179 (was $249)", fontFamily: "Liberation Sans", fontSize: 56, fontStyle: "bold", lineHeight: 1.1, align: "left", wrap: "word", fill: "#fdfbff", x: 72, y: 1256, width: 936, height: 72, z: 4 },
    { id: "cta", type: "group", parent: "story-1", role: "cta", link: "https://halden.example/h7-sale", x: 72, y: 1360, z: 5 },
    { id: "cta-plate", type: "shape", parent: "cta", x: 0, y: 0, width: 936, height: 112, fill: "#ffd23f", cornerRadius: 16, z: 0 },
    { id: "cta-label", type: "text", parent: "cta", text: "Shop now", fontFamily: "Liberation Sans", fontSize: 44, fontStyle: "bold", lineHeight: 1.1, align: "center", wrap: "word", fill: "#1d1240", x: 0, y: 30, width: 936, height: 52, z: 1 },
    { id: "legal", type: "text", parent: "story-1", role: "legal", text: "Offer ends 31 Oct 2026. While stocks last. Terms apply.", fontFamily: "Liberation Sans", fontSize: 24, fontStyle: "normal", lineHeight: 1.3, align: "left", wrap: "word", fill: "#fdfbff", x: 72, y: 1540, width: 936, height: 160, z: 6 },
  ],
};
let eng;
const live = [];
before(async () => { eng = new Engine(); await eng.start(); });
after(async () => { await eng.close(); });
afterEach(async () => { while (live.length) await eng.destroy(live.pop()); });
const mk = async (scene = STORY) => { const s = await eng.create(scene, { owner: "u", backend: "fabric" }); live.push(s.session_id); return s; };
const native = async (s) => Object.fromEntries((await eng.nativeState(s.session_id, "u")).nodes.map((n) => [n.id, n]));
// The documented frame rule (the verifier implements the same rule in Python): a child in "group_center" sits at
// parent-local x = x + parentWidth/2.
const local = (nodes, n) => (n.frame === "group_center" ? [n.x + nodes[n.parent].width / 2, n.y + nodes[n.parent].height / 2] : [n.x, n.y]);

test("fabric: a story card loads as real Fabric groups, textboxes and images", async () => {
  const s = await mk();
  const n = await native(s);
  for (const want of STORY.nodes) {
    const got = n[want.id];
    assert.ok(got, want.id);
    for (const f of ["type", "parent", "role", "format", "sequence", "text", "fontFamily", "fontSize", "fontStyle", "lineHeight", "align", "asset", "focal", "link", "cornerRadius", "z"]) {
      if (f in want) assert.deepEqual(got[f], want[f], `${want.id}.${f}`);
    }
    if (want.parent) {
      assert.equal(got.frame, "group_center", want.id);
      assert.deepEqual(local(n, got), [want.x, want.y], `${want.id} position`);
    }
  }
  assert.deepEqual(n["story-1"].safe, SAFE);
});

test("fabric: images keep their natural size and carry the scale", async () => {
  const n = await native(await mk());
  assert.deepEqual([n.hero.width, n.hero.height, n.hero.scaleX, n.hero.scaleY, n.hero.crop], [1000, 1000, 0.72, 0.72, null]);
});

test("fabric: text reports its authored frame even when Fabric widens the textbox", async () => {
  const wide = structuredClone(STORY);
  Object.assign(wide.nodes.find((x) => x.id === "head"), { text: "Geräuschunterdrückungstechnologie", width: 300, height: 400 });
  const n = await native(await mk(wide));
  assert.deepEqual([n.head.width, n.head.height], [300, 400]);
});

test("fabric: an unknown asset and a foreign font are refused", async () => {
  for (const [edit, why] of [[(x) => { x.hero.asset = "nope"; }, /unknown asset nope/], [(x) => { x.head.fontFamily = "Arial"; }, /Liberation Sans/]]) {
    const bad = structuredClone(STORY);
    edit(Object.fromEntries(bad.nodes.map((x) => [x.id, x])));
    await assert.rejects(eng.create(bad, { owner: "u", backend: "fabric" }), (e) => e.code === "INVALID_SCENE" && why.test(e.message));
  }
});

// Plan 9D Task 3: observe_fit on Fabric (same contract as Konva).
const LIMITS = { safe: SAFE, min_font: 40, min_legal_font: 24, min_cta_height: 96, min_hero_width: 432 };
const variant = (edit) => { const v = structuredClone(STORY); edit(Object.fromEntries(v.nodes.map((n) => [n.id, n]))); return v; };
const act = (s, tool, args, extra = {}) => eng.act(s.session_id, "u", { tool, args, ...extra });
const fit = async (scene) => {
  const s = await mk(scene);
  const r = await act(s, "observe_fit", { artboard_id: "story-1", limits: LIMITS });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  return { s, r };
};
const kinds = (r) => r.result.violations.map((v) => `${v.kind}:${v.node_id}`);

test("fabric observe_fit: short English copy fits", async () => {
  const { r } = await fit(STORY);
  assert.deepEqual(r.result.violations, []);
  assert.equal(r.result.text.find((t) => t.id === "head").lines.length, 1);
});

test("fabric observe_fit: a short frame overflows", async () => {
  const { r } = await fit(variant((n) => { n.head.width = 300; n.head.height = 80; n.head.text = "Hear only what matters."; }));
  assert.ok(r.result.text.find((t) => t.id === "head").lines.length >= 3);
  assert.ok(kinds(r).includes("text_overflow:head"), kinds(r).join());
});

test("fabric observe_fit: a widened textbox still reports the over-wide word", async () => {
  const { r } = await fit(variant((n) => { n.head.width = 300; n.head.height = 400; n.head.text = "Geräuschunterdrückungstechnologie"; }));
  assert.ok(kinds(r).includes("word_too_wide:head"), kinds(r).join());
});

test("fabric observe_fit: read-only", async () => {
  const { s, r } = await fit(STORY);
  assert.equal(r.revision, s.revision);
});

test("fabric observe_fit: outside safe area, overlap and minimums", async () => {
  const { r } = await fit(variant((n) => { n.logo.y = 100; n.price.y = 1200; n.legal.fontSize = 20; }));
  assert.ok(kinds(r).includes("outside_safe:logo"), kinds(r).join());
  assert.ok(kinds(r).some((k) => k.startsWith("overlap:")), kinds(r).join());
  assert.ok(kinds(r).includes("below_minimum:legal"), kinds(r).join());
});

test("fabric observe_fit: incomplete limits are refused", async () => {
  const s = await mk();
  const { min_font, ...partial } = LIMITS;
  const r = await act(s, "observe_fit", { artboard_id: "story-1", limits: partial });
  assert.equal(r.error.code, "INVALID_ARGUMENT");
});

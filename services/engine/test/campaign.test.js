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

const LIMITS = { safe: SAFE, min_font: 40, min_legal_font: 24, min_cta_height: 96, min_hero_width: 432 };
const FULL = structuredClone(STORY);
FULL.nodes.push(
  { id: "price", type: "text", parent: "story-1", role: "price", text: "Now $179 (was $249)", fontFamily: "Liberation Sans", fontSize: 56, fontStyle: "bold", lineHeight: 1.1, align: "left", wrap: "word", fill: "#fdfbff", x: 72, y: 1256, width: 936, height: 72, z: 5 },
  { id: "legal", type: "text", parent: "story-1", role: "legal", text: "Offer ends 31 Oct 2026. While stocks last. Terms apply.", fontFamily: "Liberation Sans", fontSize: 24, fontStyle: "normal", lineHeight: 1.3, align: "left", wrap: "word", fill: "#fdfbff", x: 72, y: 1540, width: 936, height: 160, z: 6 },
);
const variant = (edit) => { const v = structuredClone(FULL); edit(Object.fromEntries(v.nodes.map((n) => [n.id, n]))); return v; };
const fit = async (scene) => {
  const s = await mk(scene);
  const r = await act(s, "observe_fit", { artboard_id: "story-1", limits: LIMITS });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  return { s, r };
};
const act = (s, tool, args) => eng.act(s.session_id, "u1", { tool, args });
const kinds = (r) => r.result.violations.map((v) => `${v.kind}:${v.node_id}`);

test("short English copy fits the taught layout", async () => {
  const { r } = await fit(FULL);
  assert.deepEqual(r.result.violations, []);
  assert.equal(r.result.fits, true);
  assert.equal(r.result.text.find((t) => t.id === "head").lines.length, 1);
});

test("fixed-height frame does not hide overflow", async () => {
  const { r } = await fit(variant((n) => { n.head.width = 300; n.head.height = 80; n.head.text = "Hear only what matters."; }));
  const head = r.result.text.find((t) => t.id === "head");
  assert.ok(head.lines.length >= 3, JSON.stringify(head.lines));
  assert.ok(head.text_height > 80);
  assert.ok(kinds(r).includes("text_overflow:head"), kinds(r).join());
  assert.equal(r.result.fits, false);
});

test("over-wide German compound is reported, not broken", async () => {
  const { r } = await fit(variant((n) => { n.head.width = 300; n.head.height = 400; n.head.text = "Geräuschunterdrückungstechnologie"; }));
  assert.ok(kinds(r).includes("word_too_wide:head"), kinds(r).join());
});

test("observe_fit does not mutate", async () => {
  const { s, r } = await fit(FULL);
  assert.equal(r.revision, s.revision);
});

test("node outside safe area and overlapping nodes are reported", async () => {
  const { r } = await fit(variant((n) => { n.logo.y = 100; n.price.y = 1200; }));
  assert.ok(kinds(r).includes("outside_safe:logo"), kinds(r).join());
  assert.ok(kinds(r).some((k) => k.startsWith("overlap:")) , kinds(r).join());
});

test("minimum sizes are enforced", async () => {
  const { r } = await fit(variant((n) => { n.legal.fontSize = 20; n.hero.width = 400; n.hero.height = 400; }));
  assert.ok(kinds(r).includes("below_minimum:legal"), kinds(r).join());
  assert.ok(kinds(r).includes("below_minimum:hero"), kinds(r).join());
});

// Final review fixes.
test("a no-break-space run is one word for word_too_wide", async () => {
  const { r } = await fit(variant((n) => { n.price.width = 300; n.price.height = 400; n.price.text = "49,99 € statt 79,99 €"; }));
  assert.ok(kinds(r).includes("word_too_wide:price"), kinds(r).join());
});

test("scaled-down legal text is below the minimum", async () => {
  const { r } = await fit(variant((n) => { n.legal.scaleX = 0.5; n.legal.scaleY = 0.5; }));
  assert.ok(kinds(r).includes("below_minimum:legal"), kinds(r).join());
});

test("observe_fit refuses incomplete limits instead of skipping checks", async () => {
  const s = await mk(FULL);
  const { min_font, ...partial } = LIMITS;
  const r = await act(s, "observe_fit", { artboard_id: "story-1", limits: partial });
  assert.equal(r.ok, false);
  assert.equal(r.error.code, "INVALID_ARGUMENT");
});

test("text in a font the verifier cannot measure is refused", async () => {
  for (const edit of [(n) => { n.head.fontFamily = "Arial"; }, (n) => { n.head.fontStyle = "italic"; }]) {
    await assert.rejects(eng.create(variant(edit), { owner: "u1" }), (e) => e.code === "INVALID_SCENE");
  }
});

// Plan 9B Task 1: campaign layout tools.
const mut = async (s, tool, args) => {
  const r = await eng.act(s.session_id, "u1", { tool, args, expected_revision: s.revision });
  if (r.ok) s.revision = r.revision;
  return r;
};
const nodeOf = async (s, id) => (await eng.nativeState(s.session_id, "u1")).nodes.find((n) => n.id === id);

test("create_artboard adds a story card with its metadata", async () => {
  const s = await mk(FULL);
  const before = s.revision;
  const r = await mut(s, "create_artboard", { artboard_id: "story-2", x: 1180, y: 0, width: 1080, height: 1920, format: "9:16", safe: SAFE, sequence: 2 });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  assert.equal(r.revision, before + 1);
  const ab = await nodeOf(s, "story-2");
  assert.deepEqual([ab.type, ab.x, ab.width, ab.height, ab.format, ab.sequence], ["artboard", 1180, 1080, 1920, "9:16", 2]);
  assert.deepEqual(ab.safe, SAFE);
});

test("remove_artboard refuses a card that still has content", async () => {
  const s = await mk(FULL);
  const r = await mut(s, "remove_artboard", { artboard_id: "story-1" });
  assert.equal(r.error.code, "INVALID_ARGUMENT");
});

test("remove_artboard removes an empty card", async () => {
  const s = await mk(FULL);
  await mut(s, "create_artboard", { artboard_id: "story-2", x: 1180, y: 0, width: 1080, height: 1920, format: "9:16", safe: SAFE, sequence: 2 });
  const r = await mut(s, "remove_artboard", { artboard_id: "story-2" });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  assert.equal(await nodeOf(s, "story-2"), undefined);
});

test("reparent_nodes moves a node into another card keeping its world position", async () => {
  const s = await mk(FULL);
  await mut(s, "create_artboard", { artboard_id: "story-2", x: 1180, y: 0, width: 1080, height: 1920, format: "9:16", safe: SAFE, sequence: 2 });
  const r = await mut(s, "reparent_nodes", { node_ids: ["price"], parent_id: "story-2" });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  const p = await nodeOf(s, "price");
  assert.deepEqual([p.parent, p.x, p.y], ["story-2", 72 - 1180, 1256]);
});

test("set_order changes stacking within the parent", async () => {
  const s = await mk(FULL);
  const r = await mut(s, "set_order", { node_id: "legal", z: 1 });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  assert.equal((await nodeOf(s, "legal")).z, 1);
});

test("resize_node resizes a text frame", async () => {
  const s = await mk(FULL);
  const r = await mut(s, "resize_node", { node_id: "head", width: 600, height: 300 });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  const h = await nodeOf(s, "head");
  assert.deepEqual([h.width, h.height], [600, 300]);
});

test("set_style on text allows fontSize only", async () => {
  const s = await mk(FULL);
  assert.equal((await mut(s, "set_style", { node_id: "head", style: { fill: "#ff0000" } })).error.code, "INVALID_ARGUMENT");
  assert.equal((await mut(s, "set_style", { node_id: "head", style: { fontSize: 44 } })).ok, true);
  assert.equal((await nodeOf(s, "head")).fontSize, 44);
});

test("set_style on a shape allows cornerRadius", async () => {
  const s = await mk(FULL);
  const r = await mut(s, "set_style", { node_id: "cta-plate", style: { cornerRadius: 4 } });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  assert.equal((await nodeOf(s, "cta-plate")).cornerRadius, 4);
});

test("fit_image_contain centres the image at its natural aspect", async () => {
  const s = await mk(FULL);
  const r = await mut(s, "fit_image_contain", { node_id: "hero", x: 72, y: 320, width: 936, height: 720 });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  const h = await nodeOf(s, "hero");
  assert.deepEqual([h.x, h.y, h.width, h.height, h.crop], [72 + 108, 320, 720, 720, null]);
});

const pngSize = (dataUrl) => {
  const b = Buffer.from(dataUrl.split(",")[1], "base64");
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
};

test("export_scene shows every story card, even beyond the source canvas", async () => {
  const s = await mk(FULL);
  await mut(s, "create_artboard", { artboard_id: "story-2", x: 1180, y: 0, width: 1080, height: 1920, format: "9:16", safe: SAFE, sequence: 2 });
  const r = await eng.act(s.session_id, "u1", { tool: "export_scene", args: { format: "png" } });
  assert.equal(r.ok, true, JSON.stringify(r.error));
  const [w, h] = pngSize(r.result.data_url);
  const boards = (await eng.nativeState(s.session_id, "u1")).nodes.filter((n) => n.type === "artboard");
  const right = Math.max(...boards.map((b) => b.x + b.width)), bottom = Math.max(...boards.map((b) => b.y + b.height));
  const left = Math.min(...boards.map((b) => b.x)), top = Math.min(...boards.map((b) => b.y));
  assert.ok(Math.abs(w / h - (right - left) / (bottom - top)) < 0.01, `exported ${w}x${h}, cards span ${right - left}x${bottom - top}`);
});

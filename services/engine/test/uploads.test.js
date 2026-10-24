// A user's banner crops travel with the scene as scene.assets: PNG only, bounded, and never through the public route.
import { after, afterEach, before, test } from "node:test";
import assert from "node:assert/strict";
import zlib from "node:zlib";
import { Engine } from "../src/engine.js";
import { buildServer } from "../src/server.js";

function crc32(buf) {
  let c, crc = ~0;
  for (let i = 0; i < buf.length; i++) { c = (crc ^ buf[i]) & 0xff; for (let k = 0; k < 8; k++) c = c & 1 ? (c >>> 1) ^ 0xedb88320 : c >>> 1; crc = (crc >>> 8) ^ c; }
  return ~crc >>> 0;
}
const chunk = (tag, body) => {
  const t = Buffer.concat([Buffer.from(tag, "latin1"), body]);
  const len = Buffer.alloc(4); len.writeUInt32BE(body.length);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(t));
  return Buffer.concat([len, t, crc]);
};
/** A real PNG: solid colour, w x h. */
export function pngUrl(w, h, rgb = [200, 80, 40]) {
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array(w).fill(rgb).flat())]);
  const idat = zlib.deflateSync(Buffer.concat(Array(h).fill(row)));
  const png = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", ihdr), chunk("IDAT", idat), chunk("IEND", Buffer.alloc(0))]);
  return `data:image/png;base64,${png.toString("base64")}`;
}
/** A PNG whose header claims w x h but holds almost no pixel data (a decompression-bomb shape). */
const bombUrl = (w, h) => {
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const png = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", ihdr), chunk("IEND", Buffer.alloc(0))]);
  return `data:image/png;base64,${png.toString("base64")}`;
};

const LOGO = "u-0123456789ab-brand_mark", HERO = "u-0123456789ab-product_image";
const scene = (assets) => ({
  canvas: { width: 1280, height: 720 },
  nodes: [
    { id: "banner", type: "artboard", x: 0, y: 0, width: 1280, height: 720, format: "16:9", safe: { top: 0, right: 0, bottom: 0, left: 0 }, sequence: 1 },
    { id: "bg", type: "rect", parent: "banner", role: "background", x: 0, y: 0, width: 1280, height: 720, fill: "#1d1240", z: 0 },
    { id: "logo", type: "image", parent: "banner", role: "brand_mark", asset: LOGO, crop: null, focal: { x: 96, y: 24 }, x: 64, y: 48, width: 192, height: 48, z: 1 },
    { id: "hero", type: "image", parent: "banner", role: "product_image", asset: HERO, crop: null, focal: { x: 240, y: 240 }, x: 80, y: 152, width: 480, height: 480, z: 2 },
  ],
  ...(assets ? { assets } : {}),
});
const GOOD = () => ({ [LOGO]: pngUrl(192, 48), [HERO]: pngUrl(480, 480, [20, 120, 200]) });

let eng, app;
before(async () => { eng = new Engine(); await eng.start(); app = buildServer(eng, { evaluatorToken: "tok-123" }); });
after(async () => { await eng.close(); });
const live = [];
afterEach(async () => { while (live.length) await eng.destroy(live.pop()); });
const mk = async (sc, opts = { owner: "u1", uploads: true }) => { const s = await eng.create(sc, opts); live.push(s.session_id); return s; };

for (const backend of ["konva", "fabric"]) {
  test(`an uploaded PNG renders in ${backend}`, async () => {
    const s = await mk(scene(GOOD()), { owner: "u1", uploads: true, backend });
    const native = await eng.nativeState(s.session_id, "u1");
    assert.equal(native.nodes.find((n) => n.id === "hero").asset, HERO);
    assert.equal(native.assets, undefined, "uploads are not echoed into the scene state");
    const r = await eng.act(s.session_id, "u1", { tool: "export_scene", args: { format: "png" } });
    assert.equal(r.ok, true, JSON.stringify(r.error));
    const b = Buffer.from(r.result.data_url.split(",")[1], "base64");
    assert.deepEqual([b.readUInt32BE(16), b.readUInt32BE(20)], [1280, 720]);
  });
}

const refused = async (sc, why, opts) => {
  await assert.rejects(() => eng.create(sc, opts ?? { owner: "u1", uploads: true }), (e) => e.code === "INVALID_SCENE" && why.test(e.message), String(why));
  assert.equal(eng.sessionCount, 0, "a refused scene leaks no session");
};

test("uploaded assets are refused unless the caller is the product path", async () => {
  await refused(scene(GOOD()), /upload/i, { owner: "u1" });
});

test("only well-formed PNGs with a per-upload id are accepted", async () => {
  await refused(scene({ ...GOOD(), [LOGO]: "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=" }), /PNG/);
  await refused(scene({ ...GOOD(), [LOGO]: "data:image/jpeg;base64,/9j/4AAQ" }), /PNG/);
  await refused(scene({ ...GOOD(), [LOGO]: "data:image/png;base64,AAAA" }), /PNG/);
  await refused(scene({ ...GOOD(), [LOGO]: "data:image/png;base64,@@@@" }), /base64/);
  await refused(scene({ ...GOOD(), "h7-headphones": pngUrl(8, 8) }), /id/);
  await refused(scene({ ...GOOD(), "u-0123456789ab-extra": pngUrl(8, 8) }), /id|many/);
  await refused(scene({ ...GOOD(), "u-0123456789ab-brand_mark/../x": pngUrl(8, 8) }), /id/);
});

test("size is bounded before any decode: bytes, and the pixel size claimed in the header", async () => {
  await refused(scene({ ...GOOD(), [HERO]: bombUrl(5000, 5000) }), /size/);
  await refused(scene({ ...GOOD(), [HERO]: bombUrl(0, 10) }), /size/);
  const big = pngUrl(900, 900); // incompressible-looking colour rows are not needed: pad the data URL past the cap
  await refused(scene({ ...GOOD(), [HERO]: big + "A".repeat(1_400_000) }), /large|base64/);
});

test("a fixed asset id can never be replaced by an upload, and at most two uploads are taken", async () => {
  await refused(scene({ ...GOOD(), "halden-wordmark": pngUrl(8, 8) }), /id/);
  await refused(scene({ ...GOOD(), "u-aaaaaaaaaaaa-brand_mark": pngUrl(8, 8) }), /many/);
});

test("the public route never takes assets; the evaluator route does, with its larger body limit", async () => {
  const payload = { scene: scene(GOOD()), owner: "u" };
  const pub = await app.inject({ method: "POST", url: "/sessions", payload });
  assert.equal(pub.statusCode, 403);
  assert.equal((await app.inject({ method: "POST", url: "/internal/sessions", payload })).statusCode, 403);
  const ok = await app.inject({ method: "POST", url: "/internal/sessions", payload, headers: { "x-evaluator-token": "tok-123" } });
  assert.equal(ok.statusCode, 200, ok.body);
  await eng.destroy(ok.json().session_id);
});

// Pure pixel logic for "snap the model's box to what is really in the image" (apps/web/src/snap.ts).
// Run: node --experimental-strip-types --test tests/web/snap.test.ts   (Node 22.6+)
import { test } from "node:test";
import assert from "node:assert/strict";
import { backgroundOf, snapBox, type Pixels } from "../../apps/web/src/snap.ts";

const W = 400, H = 300;
const BG: [number, number, number] = [30, 18, 64];
function canvas(): Pixels {
  const data = new Uint8ClampedArray(W * H * 4);
  for (let i = 0; i < W * H; i++) data.set([...BG, 255], i * 4);
  return { data, width: W, height: H };
}
function rect(p: Pixels, x: number, y: number, w: number, h: number, c: [number, number, number] = [250, 250, 250]) {
  for (let yy = y; yy < y + h; yy++) for (let xx = x; xx < x + w; xx++) p.data.set([...c, 255], (yy * p.width + xx) * 4);
}
const near = (a: number[], b: number[], tol = 3) => a.every((v, i) => Math.abs(v - b[i]) <= tol);

test("a flat background is found from the border, a noisy one is reported as not flat", () => {
  const p = canvas();
  const bg = backgroundOf(p);
  assert.ok(bg.flat && near(bg.rgb, BG, 1));
  for (let i = 0; i < W * H; i++) p.data.set([(i * 37) % 256, (i * 91) % 256, (i * 13) % 256, 255], i * 4);
  assert.equal(backgroundOf(p).flat, false);
});

test("a box that is too narrow grows to the whole text block, across the gaps between words and lines", () => {
  const p = canvas();
  rect(p, 100, 50, 60, 16); rect(p, 170, 50, 80, 16); rect(p, 260, 50, 40, 16); // line 1: three words, 10 px gaps
  rect(p, 100, 78, 90, 16); rect(p, 200, 78, 50, 16); // line 2, 12 px below line 1
  const got = snapBox(p, [100, 50, 60, 44], BG);
  assert.ok(near(got, [98, 48, 204, 48], 1), String(got)); // ink x 100..300, y 50..94, plus the 2 px pad
});

test("it stops at a real gap: the price 60 px below the headline is not absorbed", () => {
  const p = canvas();
  rect(p, 100, 50, 200, 20); // headline
  rect(p, 100, 130, 150, 20); // price, 60 px lower
  const got = snapBox(p, [110, 52, 40, 14], BG);
  assert.ok(got[1] + got[3] < 100 && got[2] >= 196, String(got));
});

test("a loose box is tightened to the ink", () => {
  const p = canvas();
  rect(p, 150, 120, 60, 40, [255, 210, 63]);
  const got = snapBox(p, [100, 80, 200, 140], BG);
  assert.ok(near(got, [150, 120, 60, 40], 4), String(got));
});

test("a box with no ink near it, or on a background that is not flat, is returned unchanged", () => {
  const p = canvas();
  rect(p, 300, 250, 30, 20);
  assert.deepEqual(snapBox(p, [20, 20, 50, 30], BG), [20, 20, 50, 30]);
  const noisy = canvas();
  for (let i = 0; i < W * H; i++) noisy.data.set([(i * 37) % 256, (i * 91) % 256, (i * 13) % 256, 255], i * 4);
  assert.deepEqual(snapBox(noisy, [20, 20, 50, 30], BG, { flat: false }), [20, 20, 50, 30]);
});

test("growth is capped: ink that fills the canvas does not swallow the box", () => {
  const p = canvas();
  rect(p, 0, 0, W, H, [250, 250, 250]);
  rect(p, 100, 100, 40, 20, BG); // a hole in the middle, so the box sits on background
  assert.deepEqual(snapBox(p, [105, 105, 20, 10], BG), [105, 105, 20, 10]);
});

test("an image box may only grow a little: maxGrow stops it following ink far beyond what the model drew", () => {
  const p = canvas();
  rect(p, 100, 50, 160, 60); // a wide object
  const free = snapBox(p, [100, 50, 40, 60], BG);
  const capped = snapBox(p, [100, 50, 40, 60], BG, { maxGrow: 12 });
  assert.ok(free[2] >= 160, String(free));
  assert.ok(capped[2] <= 40 + 12 + 6 && capped[2] < free[2], String(capped));
});

test("overlap problems name an image box that holds a text box, by either share", async () => {
  const { imageTextOverlaps } = await import("../../apps/web/src/snap.ts");
  const L = (role: string, box: number[]) => ({ role, box });
  const clean = [L("brand_mark", [60, 40, 190, 50]), L("product_image", [80, 150, 480, 480]), L("headline", [640, 160, 576, 170]), L("price", [640, 350, 576, 50]), L("cta", [640, 430, 256, 76]), L("legal", [640, 560, 576, 80])];
  assert.deepEqual(imageTextOverlaps(clean), []);
  const swallow = clean.map((l) => (l.role === "product_image" ? L("product_image", [80, 150, 680, 480]) : l)); // reaches 120 px into the headline
  const got = imageTextOverlaps(swallow);
  assert.ok(got.some((m: string) => /Product image box overlaps the headline/.test(m)), String(got));
  const touch = clean.map((l) => (l.role === "product_image" ? L("product_image", [80, 150, 570, 480]) : l)); // 10 px: tolerated
  assert.deepEqual(imageTextOverlaps(touch), []);
});

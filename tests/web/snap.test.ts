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
/** Text-like ink: vertical strokes with gaps (about half filled), unlike a solid button plate. */
function txt(p: Pixels, x: number, y: number, w: number, h: number) {
  for (let xx = x; xx < x + w; xx += 4) rect(p, xx, y, 2, h);
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

test("a product box that holds part of the logo is a problem (its crop would show a stray fragment)", async () => {
  const { imageTextOverlaps } = await import("../../apps/web/src/snap.ts");
  const L = (role: string, box: number[]) => ({ role, box });
  const apart = [L("brand_mark", [32, 40, 205, 32]), L("product_image", [115, 90, 448, 580])];
  assert.deepEqual(imageTextOverlaps(apart), []);
  const into = [L("brand_mark", [32, 40, 205, 32]), L("product_image", [115, 43, 448, 626])]; // the fresh-set lamp: its box reaches into the wordmark
  assert.ok(imageTextOverlaps(into).some((m: string) => /Product image box overlaps the logo/.test(m)), String(imageTextOverlaps(into)));
  const touch = [L("brand_mark", [32, 40, 205, 32]), L("product_image", [115, 70, 448, 600])]; // 2 px: tolerated
  assert.deepEqual(imageTextOverlaps(touch), []);
});

import { clippedSides, foreignRuns, inkComponents, pictureComponents, unionBox } from "../../apps/web/src/snap.ts";

test("a picture is cut out of its box together with its own parts, without the logo that overlaps the rectangle", () => {
  const p = canvas();
  rect(p, 40, 30, 120, 14); // a wordmark
  rect(p, 100, 60, 90, 200); // the product (tall), whose rectangle reaches up into the wordmark's x range
  const comps = inkComponents(p, BG);
  assert.equal(comps.boxes.length, 2);
  const logoBox = [40, 30, 120, 14];
  const seed = [100, 36, 90, 230]; // the model's product box: reaches y 36, into the wordmark's rows
  const ids = pictureComponents(comps, seed, [logoBox]);
  assert.equal(ids.length, 1);
  const box = unionBox(comps, ids, 0) as number[];
  assert.deepEqual(box, [100, 60, 90, 200]);
  // the crop of the SEED rectangle holds the wordmark's tail: it is returned as foreign pixels to paint over
  const runs = foreignRuns(p, comps, seed, ids);
  assert.ok(runs.length > 0 && runs.every(([x, y, w]) => w > 0 && y < 12), JSON.stringify(runs.slice(0, 3)));
  assert.deepEqual(foreignRuns(p, comps, box, ids), []); // the tight crop is clean
});

test("a box that cuts the picture off is reported, a tight box is not", () => {
  const p = canvas();
  rect(p, 100, 60, 90, 200);
  const comps = inkComponents(p, BG);
  const ids = pictureComponents(comps, [100, 60, 90, 120], []);
  assert.ok(clippedSides(p, comps, [100, 60, 90, 120], ids).includes("bottom")); // stops halfway down
  assert.deepEqual(clippedSides(p, comps, [98, 58, 94, 204], ids), []);
  assert.deepEqual(unionBox(comps, ids, 0), [100, 60, 90, 200]); // and the union is the whole picture
});

test("specks are not pictures", () => {
  const p = canvas();
  rect(p, 100, 60, 90, 200);
  rect(p, 300, 20, 3, 3);
  const comps = inkComponents(p, BG);
  assert.equal(pictureComponents(comps, [60, 20, 300, 260], []).length, 1);
});

import { reassignText, textBlocks } from "../../apps/web/src/snap.ts";

test("text blocks: lines of one paragraph merge, a real gap splits, in reading order", () => {
  const p = canvas();
  txt(p, 200, 20, 150, 20); txt(p, 200, 46, 120, 20); txt(p, 200, 72, 100, 20); // headline, three lines 6 px apart
  txt(p, 200, 130, 90, 22); // price, 38 px below
  rect(p, 200, 180, 150, 40); // button plate
  txt(p, 280, 260, 100, 10); // small print, far right
  const b = textBlocks(p, BG, [190, 0, 210, 300], []);
  assert.equal(b.length, 4, JSON.stringify(b));
  assert.ok(b[0][3] >= 70 && b[1][1] > b[0][1] + b[0][3]);
});

test("misplaced text boxes move onto their blocks only when the block count matches", () => {
  const p = canvas();
  txt(p, 200, 20, 150, 20); txt(p, 200, 46, 120, 20); txt(p, 200, 72, 100, 20);
  txt(p, 200, 130, 90, 22); rect(p, 200, 180, 150, 40); txt(p, 280, 260, 100, 10);
  const L = (role: string, box: number[]) => ({ role, box });
  // the model put price, button and small print on the headline's last lines (the fresh-set speaker)
  const bad = [L("headline", [200, 20, 150, 40]), L("price", [200, 60, 120, 20]), L("cta", [200, 80, 150, 20]), L("legal", [280, 90, 100, 12])];
  const got = reassignText(p, BG, bad, []) as { role: string; box: number[] }[];
  const at = (r: string) => got.find((g) => g.role === r)?.box as number[];
  assert.ok(near(at("headline"), [198, 18, 154, 76], 3) && near(at("price"), [198, 128, 94, 26], 3) && near(at("cta"), [198, 178, 154, 44], 3) && near(at("legal"), [278, 258, 104, 14], 3), JSON.stringify(got));
  rect(p, 176, 150, 8, 40); // a stray decoration: the count no longer matches, so nothing is moved
  assert.equal(reassignText(p, BG, bad, []), null);
});

test("a button plate right under a price is its own block, not part of the price", () => {
  const p = canvas();
  txt(p, 200, 130, 90, 22); // price text-like bar
  rect(p, 200, 168, 150, 44); // a solid plate 16 px below it (closer than half the price height would allow merging)
  const b = textBlocks(p, BG, [190, 0, 210, 300], []);
  assert.equal(b.length, 2, JSON.stringify(b));
});

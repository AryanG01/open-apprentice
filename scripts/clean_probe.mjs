// Runs the clean-picture pipeline (apps/web/src/snap.ts) on the saved raw model boxes of the fresh set, in Node, and writes the new
// boxes plus the cleaned crops so they can be looked at. No model, no network.
//   node --experimental-strip-types scripts/clean_probe.mjs docs/evaluation/fresh_synthetic /tmp/out
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { backgroundOf, foreignComponents, foreignRuns, inkComponents, pictureComponents, reassignText, snapBox, unionBox } from "../apps/web/src/snap.ts";

const [setDir, outDir] = process.argv.slice(2);
fs.mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
const page = await (await browser.newContext()).newPage();
await page.goto("about:blank");
const isImg = (r) => r === "brand_mark" || r === "product_image";
const summary = {};
for (const b of ["banner_01", "banner_02", "banner_03", "banner_04"]) {
  const file = path.join(setDir, "inputs", `${b}.png`);
  const raw = JSON.parse(fs.readFileSync(path.join(setDir, "run1/stage_a", `${b}.upload_response.json`), "utf8")).response.layers.map((l) => ({ role: l.role, box: l.box }));
  const r = await page.evaluate(async (b64) => {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = "data:image/png;base64," + b64; });
    const c = document.createElement("canvas"); c.width = 1280; c.height = 720;
    const ctx = c.getContext("2d"); ctx.imageSmoothingQuality = "high"; ctx.drawImage(img, 0, 0, 1280, 720);
    return Array.from(ctx.getImageData(0, 0, 1280, 720).data);
  }, fs.readFileSync(file).toString("base64"));
  const p = { width: 1280, height: 720, data: Uint8ClampedArray.from(r) };
  const bg = backgroundOf(p);
  if (!bg.flat) { summary[b] = { flat: false }; continue; }
  const keepOut = raw.filter((l) => isImg(l.role)).map((l) => l.box);
  const re = reassignText(p, bg.rgb, raw, keepOut);
  const work = re ? raw.map((l) => ({ ...l, box: re.find((x) => x.role === l.role).box })) : raw;
  let snapped = work.map((l) => (re && !isImg(l.role) && re.some((x) => x.role === l.role) ? l : { ...l, box: snapBox(p, l.box, bg.rgb, { flat: true, maxGrow: isImg(l.role) ? 14 : undefined }).map(Math.round) }));
  const comps = inkComponents(p, bg.rgb);
  const prod = snapped.find((l) => l.role === "product_image");
  const ids = pictureComponents(comps, prod.box, snapped.filter((l) => l !== prod).map((l) => l.box));
  const ub = unionBox(comps, ids, 2);
  if (ub) snapped = snapped.map((l) => (l === prod ? { ...l, box: ub.map(Math.round) } : l));
  summary[b] = { flat: true, reassigned: !!re, raw: raw.map((l) => [l.role, l.box.map(Math.round)]), final: snapped.map((l) => [l.role, l.box]) };
  // cleaned crops, as raw RGBA for PIL
  for (const l of snapped.filter((x) => isImg(x.role))) {
    const own = pictureComponents(comps, l.box, snapped.filter((o) => o !== l).map((o) => o.box));
    const [x, y, w, h] = l.box;
    const buf = Buffer.alloc(w * h * 4);
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) { const s = ((y + j) * 1280 + x + i) * 4, d = (j * w + i) * 4; for (let k = 0; k < 4; k++) buf[d + k] = p.data[s + k]; }
    if (own.length) for (const [rx, ry, rw] of foreignRuns(p, comps, l.box, foreignComponents(comps, snapped.filter((o) => o !== l).map((o) => o.box), own))) for (let i = 0; i < rw; i++) { const d = (ry * w + rx + i) * 4; buf[d] = bg.rgb[0]; buf[d + 1] = bg.rgb[1]; buf[d + 2] = bg.rgb[2]; }
    fs.writeFileSync(path.join(outDir, `${b}.${l.role}.${w}x${h}.rgba`), buf);
  }
}
await browser.close();
fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 1));
console.log(JSON.stringify(summary, null, 1));

// Preflight for the fresh synthetic set, run BEFORE any model call: resizes each original exactly as the app's banner path does
// (canvas drawImage to 1280 x 720) and applies the app's own flat-background detector (apps/web/src/snap.ts backgroundOf:
// the border must be >= 92% within RGB distance 40 of its median). Rule fixed before running: flat -> "within the documented
// simple-background contract"; not flat -> "outside it". No model, no annotations.
//   node --experimental-strip-types scripts/fresh_preflight.mjs <inputs dir>
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { backgroundOf } from "../apps/web/src/snap.ts";

const dir = process.argv[2];
const browser = await chromium.launch();
const page = await (await browser.newContext()).newPage();
await page.goto("about:blank");
const out = [];
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith(".png")).sort()) {
  const buf = fs.readFileSync(path.join(dir, f));
  const r = await page.evaluate(async (b64) => {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = "data:image/png;base64," + b64; });
    const c = document.createElement("canvas"); c.width = 1280; c.height = 720;
    const ctx = c.getContext("2d"); ctx.imageSmoothingQuality = "high"; ctx.drawImage(img, 0, 0, 1280, 720);
    return { w: img.naturalWidth, h: img.naturalHeight, data: Array.from(ctx.getImageData(0, 0, 1280, 720).data) };
  }, buf.toString("base64"));
  const bg = backgroundOf({ width: 1280, height: 720, data: Uint8ClampedArray.from(r.data) });
  out.push({ file: f, sha256: createHash("sha256").update(buf).digest("hex"), natural: [r.w, r.h], ratio_vs_16_9: +(r.w / r.h / (16 / 9)).toFixed(4), border_rgb: bg.rgb, flat: bg.flat, preflight: bg.flat ? "within contract (flat border)" : "outside contract (border not flat)" });
}
await browser.close();
console.log(JSON.stringify(out, null, 1));

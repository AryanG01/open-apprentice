// Regression view for the clean-picture pipeline on the repository's own banner fixtures: start from the REAL saved model proposals
// (<id>.proposed.json, from docs/evaluation/campaign_vision_dev_run3.json) or, without them, the authored boxes made deliberately
// wrong, and draw where the pipeline puts them. No model call.
//   node --experimental-strip-types scripts/clean_probe_fixtures.mjs <dir with <id>.png and <id>.gold.json> <out.png>
import { chromium } from "playwright";
import fs from "node:fs";
import { backgroundOf, inkComponents, pictureComponents, reassignText, snapBox, unionBox } from "../apps/web/src/snap.ts";

const [dir, out] = process.argv.slice(2);
const ids = fs.readdirSync(dir).filter((f) => f.endsWith(".png")).map((f) => f.replace(".png", ""));
const browser = await chromium.launch();
const page = await (await browser.newContext()).newPage();
await page.goto("about:blank");
const isImg = (r) => r === "brand_mark" || r === "product_image";
const report = {};
const results = [];
for (const id of ids) {
  const r = await page.evaluate(async (b64) => {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = "data:image/png;base64," + b64; });
    const c = document.createElement("canvas"); c.width = 1280; c.height = 720;
    const ctx = c.getContext("2d"); ctx.drawImage(img, 0, 0, 1280, 720);
    return Array.from(ctx.getImageData(0, 0, 1280, 720).data);
  }, fs.readFileSync(`${dir}/${id}.png`).toString("base64"));
  const p = { width: 1280, height: 720, data: Uint8ClampedArray.from(r) };
  const bg = backgroundOf(p);
  const gold = JSON.parse(fs.readFileSync(`${dir}/${id}.gold.json`, "utf8"));
  const proposedFile = `${dir}/${id}.proposed.json`;
  const bad = fs.existsSync(proposedFile) ? JSON.parse(fs.readFileSync(proposedFile, "utf8")) : gold.map((l) => {
    const [x, y, w, h] = l.box; const k = 0.1;
    const s = [x + (w * k) / 2, y + (h * k) / 2 + 0, w * (1 - k), h * (1 - k)];
    return { role: l.role, box: s };
  });
  const re = bg.flat ? reassignText(p, bg.rgb, bad, bad.filter((l) => isImg(l.role)).map((l) => l.box)) : null;
  const work = re ? bad.map((l) => ({ ...l, box: re.find((x) => x.role === l.role).box })) : bad;
  let fin = work.map((l) => (re && !isImg(l.role) && re.some((x) => x.role === l.role) ? l : { ...l, box: snapBox(p, l.box, bg.rgb, { flat: bg.flat, maxGrow: isImg(l.role) ? 14 : undefined }).map(Math.round) }));
  if (bg.flat) {
    const comps = inkComponents(p, bg.rgb);
    const prod = fin.find((l) => l.role === "product_image");
    const ub = unionBox(comps, pictureComponents(comps, prod.box, fin.filter((l) => l !== prod).map((l) => l.box)), 2);
    if (ub) fin = fin.map((l) => (l === prod ? { ...l, box: ub.map(Math.round) } : l));
  }
  report[id] = { flat: bg.flat, reassigned: !!re, final: fin.map((l) => [l.role, l.box]), gold: gold.map((l) => [l.role, l.box.map(Math.round)]) };
  results.push({ id, fin, gold });
}
await browser.close();
fs.writeFileSync(out.replace(/\.png$/, ".json"), JSON.stringify({ report, results }));
console.log(Object.entries(report).map(([k, v]) => `${k} flat=${v.flat} reassigned=${v.reassigned}`).join("\n"));

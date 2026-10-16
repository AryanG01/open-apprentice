// Measure label text boxes in an SVG exported by the draw.io CLI, rendered with the host's own fonts (no bundled-font
// override): the "real Helvetica" side of the drift report. Same primitive as the engine: one Range per non-empty text node.
// Usage: node scripts/drawio/drift_measure.mjs EXPORT.svg > boxes.json   (prints {text: {x, y, w, h}} in SVG user units)
import { readFileSync } from "node:fs";
import { chromium } from "playwright";

const svg = readFileSync(process.argv[2], "utf8").replace(/^\s*<\?xml[^>]*\?>/, "").replace(/<!DOCTYPE[^>]*>/i, "");
const browser = await chromium.launch();
const context = await browser.newContext({ javaScriptEnabled: false });
await context.route("**/*", (route) => route.abort());
const page = await context.newPage();
await page.setContent(`<!doctype html><html><body style="margin:0">${svg}</body></html>`);
const boxes = await page.evaluate(async () => {
  await document.fonts.ready;
  const root = document.querySelector("svg");
  const inv = root.getScreenCTM().inverse();
  const pt = root.createSVGPoint();
  const toUser = (x, y) => { pt.x = x; pt.y = y; const q = pt.matrixTransform(inv); return [q.x, q.y]; };
  const out = {};
  for (const fo of root.querySelectorAll("foreignObject")) {
    const walker = document.createTreeWalker(fo, NodeFilter.SHOW_TEXT);
    const rects = [];
    let text = "";
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent.trim()) continue;
      text += n.textContent;
      const r = document.createRange(); r.selectNodeContents(n);
      rects.push(...[...r.getClientRects()].filter((q) => q.width > 0 && q.height > 0));
    }
    if (!rects.length) continue;
    const [x0, y0] = toUser(Math.min(...rects.map((q) => q.left)), Math.min(...rects.map((q) => q.top)));
    const [x1, y1] = toUser(Math.max(...rects.map((q) => q.right)), Math.max(...rects.map((q) => q.bottom)));
    out[text.trim()] = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }
  return out;
});
console.log(JSON.stringify(boxes));
await browser.close();

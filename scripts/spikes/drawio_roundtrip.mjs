// Spike: render one .drawio page with the locally served viewer in a network-blocked Chromium and measure labels.
// Usage: node scripts/spikes/drawio_roundtrip.mjs <file.drawio> <viewer.js> > out.json
import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const [file, viewerPath] = process.argv.slice(2);
const xml = readFileSync(file, "utf8");
const viewer = readFileSync(viewerPath, "utf8");
const browser = await chromium.launch();
const context = await browser.newContext({ javaScriptEnabled: true });
const blocked = [];
await context.route("**/*", (route) => { blocked.push(route.request().url()); route.abort(); });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.setContent(`<!doctype html><html><body style="margin:0"><div id="c"></div></body></html>`);
await page.addScriptTag({ content: viewer });
const result = await page.evaluate(async (xmlText) => {
  const globals = Object.keys(window).filter((k) => /^(GraphViewer|mx[A-Z]|Graph$)/.test(k)).slice(0, 12);
  if (typeof GraphViewer === "undefined") return { error: "GraphViewer undefined", globals };
  const doc = mxUtils.parseXml(xmlText);
  const container = document.getElementById("c");
  const v = new GraphViewer(container, doc.documentElement, { highlight: "none", nav: false, resize: false, center: false });
  const graph = v.graph;
  graph.view.setScale(1);
  await document.fonts.ready;
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const svg = container.querySelector("svg");
  const toDoc = (cx, cy) => {
    const p = svg.createSVGPoint(); p.x = cx; p.y = cy;
    const q = p.matrixTransform(svg.getScreenCTM().inverse());
    const s = graph.view.scale, t = graph.view.translate;
    return { x: q.x / s - t.x, y: q.y / s - t.y };
  };
  const out = { globals, translate: { x: graph.view.translate.x, y: graph.view.translate.y }, scale: graph.view.scale, labels: {}, nodes: {} };
  for (const cell of Object.values(graph.model.cells)) {
    const st = graph.view.getState(cell);
    if (!st || !cell.vertex) continue;
    const g = cell.geometry;
    const isText = (cell.style || "").startsWith("text;");
    if (isText && st.text && st.text.node) {
      // measure the text glyph runs only: one Range per non-empty text node (the foreignObject container is 100%)
      const walker = document.createTreeWalker(st.text.node, NodeFilter.SHOW_TEXT);
      const rects = [];
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!n.textContent.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(n);
        rects.push(...[...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0));
      }
      const xs = rects.flatMap((r) => [r.left, r.right]), ys = rects.flatMap((r) => [r.top, r.bottom]);
      const a = toDoc(Math.min(...xs), Math.min(...ys)), b = toDoc(Math.max(...xs), Math.max(...ys));
      out.labels[cell.id] = { geometry: { x: g.x, y: g.y, w: g.width, h: g.height }, box: { x: a.x, y: a.y, w: b.x - a.x, h: b.y - a.y }, rects: rects.length };
    } else {
      out.nodes[cell.id] = { geometry: { x: g.x, y: g.y, w: g.width, h: g.height },
        state: { x: st.x / st.view.scale - st.view.translate.x, y: st.y / st.view.scale - st.view.translate.y, w: st.width / st.view.scale, h: st.height / st.view.scale } };
    }
  }
  return out;
}, xml);
result.blocked_requests = blocked;
result.page_errors = errors;
console.log(JSON.stringify(result, null, 1));
await browser.close();

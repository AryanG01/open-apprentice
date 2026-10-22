// Render and measure one draw.io page with the pinned viewer in a fresh, network-blocked context (spec 6).
// Measurement primitives follow the round-trip spike: labels = union of client rects of one Range per non-empty text node,
// plus visible background/border/padding; fixed shapes = draw.io cell-state bounds cross-checked with the rendered element.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const VENDOR = new URL("../vendor/", import.meta.url);
const MANIFEST = JSON.parse(readFileSync(new URL("MANIFEST.json", VENDOR)));
export const read = (rel) => {
  const buf = readFileSync(new URL(rel, VENDOR));
  if (createHash("sha256").update(buf).digest("hex") !== MANIFEST.files[rel].sha256) throw new Error(`vendored ${rel} hash mismatch`);
  return buf;
};
const VIEWER = read("drawio/viewer-static.min.js").toString("utf8");
const REGULAR = read("fonts/LiberationSans-Regular.ttf").toString("base64");
const BOLD = read("fonts/LiberationSans-Bold.ttf").toString("base64");
// The bundled font is declared under "Helvetica" (what draw.io requests) and a probe name used only by tests; author
// @font-face rules shadow any system Helvetica, so the profile is identical on macOS and on Cloud Run.
export const FONT_CSS = ["Helvetica", "OA Liberation Probe", "Liberation Sans"].map((fam) =>
  `@font-face{font-family:"${fam}";src:url(data:font/ttf;base64,${REGULAR}) format("truetype");font-weight:400}` +
  `@font-face{font-family:"${fam}";src:url(data:font/ttf;base64,${BOLD}) format("truetype");font-weight:700}`).join("");
export const PROFILE_BASE = {
  viewer_sha256: MANIFEST.files["drawio/viewer-static.min.js"].sha256,
  font: "Liberation Sans 2.1.5 as Helvetica",
  font_sha256: { Regular: MANIFEST.files["fonts/LiberationSans-Regular.ttf"].sha256, Bold: MANIFEST.files["fonts/LiberationSans-Bold.ttf"].sha256 },
};
export const MAX_XML = 4 * 1024 * 1024;
export const RENDER_TIMEOUT_MS = 15000;

export async function openFontPage(browser) {
  const context = await browser.newContext({ javaScriptEnabled: true });
  const blocked = [];
  await context.route("**/*", (route) => { blocked.push(route.request().url()); return route.abort(); });
  try {
    const page = await context.newPage();
    await page.setContent('<!doctype html><html><body style="margin:0"><div id="c"></div></body></html>');
    await page.addStyleTag({ content: FONT_CSS });
    await page.evaluate(async () => {
      await document.fonts.load('12px "Helvetica"'); await document.fonts.load('bold 12px "Helvetica"');
      await document.fonts.load('12px "OA Liberation Probe"'); await document.fonts.ready;
    });
    return { context, page, blocked };
  } catch (e) {
    await context.close().catch(() => {});
    throw e;
  }
}

// The caller owns the context (opened with openFontPage) and closes it, including when a render is abandoned on timeout.
export async function renderPage({ page, blocked }, xml, { wantPng = true, wantSvg = false } = {}) {
  await page.addScriptTag({ content: VIEWER });
  const out = await page.evaluate(async (xmlText) => {
    const doc = mxUtils.parseXml(xmlText);
    const container = document.getElementById("c");
    const v = new GraphViewer(container, doc.documentElement, { highlight: "none", nav: false, resize: false, center: false });
    const graph = v.graph;
    graph.view.setScale(1);
    await document.fonts.ready;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const svg = container.querySelector("svg");
    const inv = svg.getScreenCTM().inverse();
    const toDoc = (cx, cy) => {
      const p = svg.createSVGPoint(); p.x = cx; p.y = cy;
      const q = p.matrixTransform(inv);
      return { x: q.x / graph.view.scale - graph.view.translate.x, y: q.y / graph.view.scale - graph.view.translate.y };
    };
    const box = (l, t, r, b) => { const a = toDoc(l, t), c = toDoc(r, b); return { x: a.x, y: a.y, w: c.x - a.x, h: c.y - a.y }; };
    const res = { translate: { x: graph.view.translate.x, y: graph.view.translate.y }, labels: {}, nodes: {}, missing: [] };
    for (const cell of Object.values(graph.model.cells)) {
      if (!cell.vertex) continue;
      const st = graph.view.getState(cell);
      if (!st) { res.missing.push(cell.id); continue; }
      if ((cell.style || "").startsWith("text;")) {
        const rects = [];
        if (st.text && st.text.node) {
          const walker = document.createTreeWalker(st.text.node, NodeFilter.SHOW_TEXT);
          for (let n = walker.nextNode(); n; n = walker.nextNode()) {
            if (!n.textContent.replace(/ /g, " ").trim()) continue;
            const range = document.createRange(); range.selectNodeContents(n);
            rects.push(...[...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0));
          }
        }
        if (!rects.length) { res.missing.push(cell.id); continue; }
        let l = Math.min(...rects.map((r) => r.left)), t = Math.min(...rects.map((r) => r.top));
        let r = Math.max(...rects.map((q) => q.right)), b = Math.max(...rects.map((q) => q.bottom));
        // a visible background or border on the label's own HTML box extends the measured box
        const div = st.text.node.querySelector("div div") || st.text.node.querySelector("div");
        if (div) {
          const cs = getComputedStyle(div);
          const bg = cs.backgroundColor && cs.backgroundColor !== "rgba(0, 0, 0, 0)" && cs.backgroundColor !== "transparent";
          if (bg || parseFloat(cs.borderTopWidth) > 0) {
            const d = div.getBoundingClientRect();
            l = Math.min(l, d.left); t = Math.min(t, d.top); r = Math.max(r, d.right); b = Math.max(b, d.bottom);
          }
        }
        const lines = new Set(rects.map((q) => Math.round(q.top))).size;
        res.labels[cell.id] = { box: box(l, t, r, b), lines, rects: rects.length };
      } else {
        const s = graph.view.scale, tr = graph.view.translate;
        const state = { x: st.x / s - tr.x, y: st.y / s - tr.y, w: st.width / s, h: st.height / s };
        let element = null;
        const shapeNode = st.shape && st.shape.node;
        if (shapeNode) {
          const q = shapeNode.getBoundingClientRect();
          if (q.width > 0 || q.height > 0) element = box(q.left, q.top, q.right, q.bottom);
        }
        res.nodes[cell.id] = { state, element, stroke: Number(st.style.strokeWidth || 1) };
      }
    }
    return res;
  }, xml);
  out.png = wantPng ? (await page.locator("#c svg").screenshot({ type: "png" })).toString("base64") : null;
  out.svg = wantSvg ? await page.evaluate(() => new XMLSerializer().serializeToString(document.querySelector("#c svg"))) : null;
  out.blocked_requests = blocked;
  return out;
}

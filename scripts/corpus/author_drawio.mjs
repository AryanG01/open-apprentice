// Author the real-file corpus in the draw.io web editor (app.diagrams.net) by driving its GUI: palette clicks, the
// Edit Geometry dialog, label typing, connector dragging, Page Setup, Properties and Save as (download). Positions and
// texts are ours; ids, default styles and serialization come from the editor.
// Usage: node scripts/corpus/author_drawio.mjs <outdir> <id> [<id> ...]   (ids: A B C D E F)
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const W = (t) => Math.max(40, Math.ceil(t.length * 7 + 12)); // single-line label width a person would drag to
const below = (n, text) => [text, n[0], n[1] + n[3] + 4, W(text)];

const D = {};
{
  const n = [[60, 40, 120, 50, "Dataset"], [60, 180, 120, 50, "Preprocess"], [60, 320, 120, 50, "Train"], [60, 460, 120, 50, "Evaluate"], [300, 460, 120, 50, "Registry"]];
  D.C = { title: "Training workflow", page: [500, 700], pages: [{ nodes: n, labels: [below(n[0], "parquet, 2 TB"), below(n[1], "dedupe + split"), below(n[2], "8x GPU, 6 h"), below(n[3], "warning: drift check"), below(n[4], "signed models")], edges: [[0, 1], [1, 2], [2, 3], [3, 4]] }] };
}
{
  const n = [[40, 40, 110, 50, "Web"], [240, 40, 110, 50, "API"], [440, 40, 110, 50, "Auth"], [240, 200, 110, 50, "Orders"], [440, 200, 110, 50, "Payments"], [640, 200, 110, 50, "DB"]];
  D.A = { title: "Checkout service", page: [800, 400], pages: [{ nodes: n, labels: [below(n[0], "CDN cached"), below(n[1], "p95 120 ms"), below(n[2], "JWT"), below(n[3], "idempotent"), below(n[4], "warning: PCI scope"), below(n[5], "nightly backup")], edges: [[0, 1], [1, 2], [1, 3], [3, 4], [4, 5]] }] };
}
{
  const n = [[40, 60, 120, 50, "Gateway"], [220, 60, 120, 50, "Users"], [400, 60, 120, 50, "Catalog"], [580, 60, 120, 50, "Cart"], [220, 240, 120, 50, "Search"], [580, 240, 120, 50, "Billing"], [760, 240, 120, 50, "Mail"]];
  const legend = [[40, 40, 100, 40, "Service"]];
  D.E = { title: "Microservices", page: [900, 500], pages: [
    { nodes: n, labels: [below(n[0], "rate limited"), below(n[1], "PII"), below(n[2], "read heavy"), below(n[3], "sessions"), below(n[4], "OpenSearch"), below(n[5], "warning: retries"), below(n[6], "SMTP relay")], edges: [[0, 1], [0, 2], [0, 3], [1, 4], [3, 5], [5, 6]] },
    { nodes: legend, labels: [below(legend[0], "owned by one team")], edges: [] }] };
}
{
  const n = [[30, 40, 100, 50, "Client"], [200, 40, 100, 50, "LB"], [460, 40, 120, 50, "Edge A"], [460, 160, 120, 50, "Edge B"], [200, 160, 100, 50, "Origin"], [460, 280, 120, 50, "Cache"]];
  D.D = { title: "Edge network", page: [600, 360], pages: [{ nodes: n, labels: [below(n[0], "mobile"), below(n[1], "TLS"), below(n[2], "warning: hot"), below(n[3], "warning: cold"), below(n[4], "us-east"), [ "LRU", 460, 334, W("LRU")]], edges: [[0, 1], [1, 2], [1, 3], [2, 4], [3, 4], [4, 5]] }] };
}
{
  const n = [[40, 40, 120, 50, "Ingest"], [260, 40, 120, 50, "Stream"], [480, 40, 120, 50, "Warehouse"], [480, 200, 120, 50, "BI"], [260, 200, 120, 50, "Alerts"], [40, 200, 120, 50, "Archive"]];
  D.F = { title: "Analytics stack", page: [700, 450], compressed: true, pages: [{ nodes: n, labels: [below(n[0], "Kafka"), below(n[1], "Flink"), below(n[2], "aggregates refreshed every fifteen minutes"), below(n[3], "dashboards"), below(n[4], "warning: paging"), below(n[5], "cold storage")], edges: [[0, 1], [1, 2], [2, 3], [1, 4], [0, 5]] }] };
}
{
  const n = [[20, 30, 90, 44, "Extract"], [140, 30, 90, 44, "Validate"], [260, 30, 90, 44, "Enrich"], [380, 30, 90, 44, "Load"], [20, 160, 90, 44, "Schedule"], [140, 160, 90, 44, "Monitor"], [260, 160, 90, 44, "Report"]];
  D.B = { title: "Data pipeline", page: [640, 300], pages: [{ nodes: n, labels: [below(n[0], "hourly"), below(n[1], "schema v3"), below(n[2], "geo lookup"), below(n[3], "warning: slow"), below(n[4], "cron"), below(n[5], "SLO 99.9")], edges: [[0, 1], [1, 2], [2, 3], [4, 5], [5, 6]] }] };
}

const PALETTE = { rect: [36, 290], text: [112, 290] };

async function dialogInputs(p) { return p.$$(".geDialog input"); }

async function inputsOfType(p, type) {
  // draw.io sets input types as JS properties, so [type=...] attribute selectors do not match
  const all = await p.$$(".geDialog input");
  const out = [];
  for (const h of all) if ((await h.evaluate((e) => e.type)) === type) out.push(h);
  return out;
}

async function setGeometry(p, [x, y, w, h]) {
  // Edit > Edit Geometry (Cmd+Shift+M); if keyboard focus slipped off the diagram, refocus it and retry
  for (let tries = 0; ; tries++) {
    await p.keyboard.press("Meta+Shift+M");
    const ok = await p.waitForSelector(".geDialog", { timeout: 3000 }).then(() => true).catch(() => false);
    if (ok) break;
    if (tries >= 2) throw new Error("Edit Geometry dialog did not open");
    await p.focus(".geDiagramContainer").catch(() => {});
  }
  const ins = await dialogInputs(p);
  const vals = { 1: x, 2: y, 5: w, 6: h };
  for (const [i, v] of Object.entries(vals)) { await ins[+i].fill(String(v)); }
  await p.click(".geDialog >> text=Apply");
  await p.waitForTimeout(150);
}

async function setLabel(p, text) {
  await p.keyboard.press("Enter");
  await p.keyboard.press("Meta+A");
  await p.keyboard.type(text);
  await p.mouse.click(1140, 860); // outside the page: stop editing
  await p.waitForTimeout(150);
}

async function insert(p, kind) {
  await p.mouse.click(1140, 860); // deselect
  await p.mouse.click(...PALETTE[kind]);
  await p.waitForTimeout(200);
}

async function cellScreenCenter(p, text) {
  // locate a rendered vertex by its label text (draw.io renders HTML labels as divs inside the canvas)
  return p.evaluate((t) => {
    const el = [...document.querySelectorAll(".geDiagramContainer div")].find((d) => d.childElementCount === 0 && d.textContent === t);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
  }, text);
}

async function connect(p, a, b, srcWidth) {
  const pa = await cellScreenCenter(p, a), pb = await cellScreenCenter(p, b);
  if (!pa || !pb) return false;
  // hover the source so its blue connection arrows appear, then drag from its RIGHT arrow (labels sit below boxes,
  // so the bottom arrow would grab a label) and drop on the target's centre
  await p.mouse.move(...pa); await p.waitForTimeout(300);
  const start = [pa[0] + srcWidth / 2 + 17, pa[1] + 3];
  await p.mouse.move(start[0], start[1], { steps: 5 }); await p.waitForTimeout(400);
  await p.mouse.down(); await p.waitForTimeout(100);
  const mid = [(start[0] + pb[0]) / 2, (start[1] + pb[1]) / 2];
  await p.mouse.move(mid[0], mid[1], { steps: 10 }); await p.mouse.move(pb[0], pb[1], { steps: 10 });
  await p.waitForTimeout(400); await p.mouse.up(); await p.waitForTimeout(400);
  await p.mouse.click(1140, 860); await p.waitForTimeout(200);
  return true;
}

async function pageSetup(p, [w, h]) {
  await p.click("text=File"); await p.waitForTimeout(200);
  await p.click("text=Page Setup..."); await p.waitForSelector(".geDialog");
  await p.selectOption(".geDialog select >> nth=0", "custom");
  await p.waitForTimeout(200);
  const ins = await inputsOfType(p, "text");
  await ins[0].fill(String(w)); await ins[1].fill(String(h));
  await p.click(".geDialog >> text=Apply"); await p.waitForTimeout(300);
}

async function author(p, id, outdir, name) {
  const d = D[id];
  await p.goto("https://app.diagrams.net/?splash=0&libraries=0&offline=1", { waitUntil: "networkidle", timeout: 60000 });
  await p.waitForTimeout(2500);
  const report = { id, edges_drawn: 0, edges_planned: 0 };
  for (let pi = 0; pi < d.pages.length; pi++) {
    if (pi > 0) { await p.mouse.click(30, 885); await p.waitForTimeout(600); } // "+" adds a page
    await pageSetup(p, d.page);
    const pg = d.pages[pi];
    for (const [x, y, w, h, text] of pg.nodes) { await insert(p, "rect"); await setGeometry(p, [x, y, w, h]); await setLabel(p, text); }
    for (const [text, x, y, w] of pg.labels) { await insert(p, "text"); await setGeometry(p, [x, y, w, 20]); await setLabel(p, text); }
    for (const [a, b] of process.env.NO_EDGES ? [] : pg.edges) {
      report.edges_planned++;
      const pa = await cellScreenCenter(p, pg.nodes[a][4]);
      if (process.env.DEBUG) report.debug = (report.debug || []).concat([[pg.nodes[a][4], pa, await cellScreenCenter(p, pg.nodes[b][4])]]);
      if (await connect(p, pg.nodes[a][4], pg.nodes[b][4], pg.nodes[a][2])) report.edges_drawn++;
      if (process.env.DEBUG && report.edges_planned === 1) await p.screenshot({ path: `${outdir}/${id}-edge1.png` });
    }
  }
  if (d.compressed) {
    await p.click("text=File"); await p.waitForTimeout(200);
    await p.click("text=Properties..."); await p.waitForSelector(".geDialog");
    const box = (await inputsOfType(p, "checkbox"))[0];
    if (!(await box.isChecked())) await box.check();
    await p.click(".geDialog >> text=Apply"); await p.waitForTimeout(300);
  }
  await p.keyboard.press("Meta+Shift+S"); await p.waitForSelector(".geDialog");
  const nameInput = (await inputsOfType(p, "text"))[0];
  await nameInput.fill(name);
  const selects = await p.$$(".geDialog select");
  await selects[selects.length - 1].selectOption({ label: "Download" }); // Where: Download (headless has no device picker)
  const [dl] = await Promise.all([p.waitForEvent("download", { timeout: 20000 }), p.click(".geDialog >> text=OK")]);
  await dl.saveAs(`${outdir}/${name}`);
  report.file = `${outdir}/${name}`;
  return report;
}

const [outdir, ...ids] = process.argv.slice(2);
if (outdir === "--spec") { console.log(JSON.stringify(D)); process.exit(0); }
mkdirSync(outdir, { recursive: true });
const b = await chromium.launch();
for (const id of ids) {
  const ctx = await b.newContext({ viewport: { width: 1400, height: 900 }, acceptDownloads: true });
  const p = await ctx.newPage();
  try {
    console.log(JSON.stringify(await author(p, id, outdir, `${id}.drawio`)));
  } catch (e) {
    await p.screenshot({ path: `${outdir}/${id}-error.png` });
    console.log(JSON.stringify({ id, error: String(e).split("\n")[0], at: (e.stack || "").split("\n").find((l) => l.includes("author_drawio")) }));
  }
  await ctx.close();
}
await b.close();

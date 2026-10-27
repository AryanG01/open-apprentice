// Reads real sketches with the production endpoint and writes an overlay image per sketch, so the boxes can be judged by eye
// (docs/evaluation/campaign_sketch_real_protocol.md). One call per image, never retried: a paid POST is sent once.
// Images run in the order of <dir>/manifest.txt (one filename per line, the order received) or, without it, by filename.
// Each sketch gets its own workspace (the workspace holds at most 4 uploads; this measures reading, not preferences).
//   node scripts/sketch_probe_real.mjs <dir with images> [--url https://...] [--out dir]
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { execFileSync } from "node:child_process";

/** POST JSON with curl: Node\'s fetch resets the connection on this slow endpoint. No retries: a repeated POST could bill twice. */
function post(url, obj) {
  const f = path.join(os.tmpdir(), `sketch-probe-${process.pid}.json`);
  fs.writeFileSync(f, JSON.stringify(obj));
  const out = execFileSync("curl", ["-sS", "-m", "180", "-w", "\n%{http_code}", "-H", "content-type: application/json", "-d", `@${f}`, url], { maxBuffer: 64 * 1024 * 1024 }).toString();
  const i = out.lastIndexOf("\n");
  return { status: Number(out.slice(i + 1)), body: JSON.parse(out.slice(0, i)) };
}

const dir = process.argv[2];
const arg = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const URL_ = arg("--url", "https://open-apprentice-md76de375q-uc.a.run.app").replace(/\/$/, "");
const OUT = arg("--out", path.join(dir ?? ".", "overlays"));
if (!dir || !fs.existsSync(dir)) {
  console.error("usage: node scripts/sketch_probe_real.mjs <dir with images> [--url URL] [--out dir]");
  process.exit(2);
}
fs.mkdirSync(OUT, { recursive: true });
const listed = fs.existsSync(path.join(dir, "manifest.txt"))
  ? fs.readFileSync(path.join(dir, "manifest.txt"), "utf8").split("\n").map((s) => s.trim()).filter(Boolean)
  : null;
const files = listed ?? fs.readdirSync(dir).filter((f) => /\.(png|jpe?g)$/i.test(f)).sort();
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 720 } })).newPage();
await page.goto("about:blank");
const results = [];
for (const f of files) {
  const mime = /\.png$/i.test(f) ? "image/png" : "image/jpeg";
  const src = `data:${mime};base64,${fs.readFileSync(path.join(dir, f)).toString("base64")}`;
  const ws = post(`${URL_}/api/campaign/workspaces`, { reading: "fixed" }).body.workspace_id;
  // letterbox onto a white 1280 x 720 canvas exactly as the app does (in the browser), call the endpoint (from Node), draw the boxes
  const png = await page.evaluate(async (src) => {
    const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
    const c = document.createElement("canvas"); c.width = 1280; c.height = 720;
    const ctx = c.getContext("2d"); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, 1280, 720);
    const k = Math.min(1280 / img.naturalWidth, 720 / img.naturalHeight);
    const w = img.naturalWidth * k, h = img.naturalHeight * k;
    ctx.imageSmoothingQuality = "high"; ctx.drawImage(img, (1280 - w) / 2, (720 - h) / 2, w, h);
    return c.toDataURL("image/png");
  }, src);
  const res = post(`${URL_}/api/campaign/workspaces/${ws}/sketches`, { image: png });
  const body = res.body;
  const r = res.status !== 200
    ? { error: `HTTP ${res.status} ${JSON.stringify(body).slice(0, 200)}` }
    : {
        origin: body.origin, model: body.model, problems: body.problems, note: body.note,
        layers: body.layers.map((l) => ({ role: l.role, box: l.box })), // raw boxes; the overlay rounds nothing either
        overlay: await page.evaluate(async ({ png, layers }) => {
          const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = png; });
          const c = document.createElement("canvas"); c.width = 1280; c.height = 720;
          const ctx = c.getContext("2d"); ctx.drawImage(img, 0, 0);
          const colours = { brand_mark: "#d1387f", product_image: "#1b8fd1", headline: "#2f9e44", price: "#c98a00", cta: "#7a55d6", legal: "#555555" };
          ctx.lineWidth = 3; ctx.font = "bold 18px sans-serif";
          for (const l of layers) { const [x, y, bw, bh] = l.box; ctx.strokeStyle = colours[l.role] ?? "#f00"; ctx.fillStyle = ctx.strokeStyle; ctx.strokeRect(x, y, bw, bh); ctx.fillText(l.role, x + 4, Math.max(16, y - 6)); }
          return c.toDataURL("image/png");
        }, { png, layers: body.layers.map((l) => ({ role: l.role, box: l.box })) }),
      };
  if (r.error) { console.log(`${f}: ${r.error}`); results.push({ file: f, workspace: ws, status: res.status, error: r.error }); continue; }
  fs.writeFileSync(path.join(OUT, `${path.parse(f).name}.overlay.png`), Buffer.from(r.overlay.split(",")[1], "base64"));
  results.push({ file: f, workspace: ws, status: res.status, origin: r.origin, model: r.model, problems: r.problems, note: r.note, layers: r.layers });
  console.log(`${f}: ${r.origin} ${r.layers.map((l) => l.role).join(", ")}${r.problems.length ? `  problems: ${r.problems.join("; ")}` : ""}`);
}
fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 1));
await browser.close();

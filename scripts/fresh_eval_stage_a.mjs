// Stage A of the fresh-set evaluation: the FIRST read of each original image by the app, exactly as a user would (upload through
// the real Adapt screen), with nothing but the image reaching the model. Saves, per image and BEFORE any annotation is read:
//   the app's resized PNG and its hash, the server's raw upload response (Nemotron's layers), the editor's field values after the
//   app's own snapping, a screenshot, timings. One read per image, no retry here. Commits the artifacts itself so the order
//   (extraction saved before annotations consulted) is in git history.
//   node scripts/fresh_eval_stage_a.mjs --url http://127.0.0.1:8780 --out docs/evaluation/fresh_synthetic/run1
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";

const arg = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const URL_ = arg("--url", "http://127.0.0.1:8780");
const OUT = arg("--out", "docs/evaluation/fresh_synthetic/run1");
const SET = "docs/evaluation/fresh_synthetic";
const order = fs.readFileSync(path.join(SET, "run_order.txt"), "utf8").split("\n").map((s) => s.trim()).filter(Boolean);
fs.mkdirSync(path.join(OUT, "stage_a"), { recursive: true });
const sha = (b) => createHash("sha256").update(b).digest("hex");

const browser = await chromium.launch();
const summary = [];
for (const rel of order) {
  const name = path.basename(rel, ".png");
  const file = path.join(SET, rel);
  const buffer = fs.readFileSync(file);
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
  const page = await ctx.newPage();
  const seen = { upload: null, request: null, status: null };
  page.on("request", (r) => { if (/\/uploads$/.test(r.url()) && r.method() === "POST") seen.request = JSON.parse(r.postData()).image; });
  page.on("response", async (r) => { if (/\/uploads$/.test(r.url()) && r.request().method() === "POST") { seen.status = r.status(); seen.upload = await r.json().catch(() => null); } });
  await page.goto(`${URL_}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
  const t0 = Date.now();
  await page.locator("input[type=file]").setInputFiles({ name: `${name}.png`, mimeType: "image/png", buffer });
  let outcome = "editor";
  try {
    await page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 150_000 });
  } catch {
    outcome = "no editor within 150 s (see error text)";
  }
  const elapsed = (Date.now() - t0) / 1000;
  await page.waitForTimeout(800);
  const dir = path.join(OUT, "stage_a");
  const resized = seen.request ? Buffer.from(seen.request.split(",")[1], "base64") : null;
  if (resized) fs.writeFileSync(path.join(dir, `${name}.app_resized.png`), resized);
  fs.writeFileSync(path.join(dir, `${name}.upload_response.json`), JSON.stringify({ http_status: seen.status, response: seen.upload }, null, 1));
  const fields = await page.evaluate(() =>
    [...document.querySelectorAll("fieldset.lrow")].map((f) => ({
      legend: f.querySelector("legend")?.innerText ?? "",
      values: [...f.querySelectorAll("input, textarea")].map((i) => ({ label: i.getAttribute("aria-label") || i.closest("label")?.innerText?.split("\n")[0] || i.name || "", value: i.type === "checkbox" ? i.checked : i.value })),
    })),
  );
  const pageText = (await page.locator("body").innerText()).replace(/\s+/g, " ");
  fs.writeFileSync(path.join(dir, `${name}.editor_after_snap.json`), JSON.stringify({ fields, page_text: pageText.slice(0, 2500) }, null, 1));
  await page.screenshot({ path: path.join(dir, `${name}.editor.png`), fullPage: true });
  summary.push({
    image: rel, original_sha256: sha(buffer), app_resized_sha256: resized ? sha(resized) : null, outcome, elapsed_s: elapsed,
    http_status: seen.status, origin: seen.upload?.origin ?? null, model: seen.upload?.model ?? null,
    layers_returned: seen.upload?.layers?.length ?? null, problems: seen.upload?.problems ?? null, note: seen.upload?.note ?? null,
  });
  console.log(name, outcome, seen.status, seen.upload?.origin, `${elapsed.toFixed(1)}s`);
  await ctx.close();
}
await browser.close();
fs.writeFileSync(path.join(OUT, "stage_a_summary.json"), JSON.stringify(summary, null, 1));
execFileSync("git", ["add", OUT]);
execFileSync("git", ["commit", "-q", "-m", "eval(fresh): stage A, first raw extraction of the four originals, saved before any annotation is read"]);
console.log("committed stage A");

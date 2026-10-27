// Stage B of the fresh-set evaluation: corrected completion through the real Adapt screen, after Stage A is committed.
// The vision model answers from the Stage A log (server in replay-vision mode), so no image is read a second time; the text model is
// live (only an overflow question uses it). A scripted operator applies the frozen rule of docs/evaluation/fresh_synthetic_protocol.md:
// each correction is one changed field, counted; nothing else is edited. Expected text comes from evaluator_only/ (read only now).
//   node scripts/fresh_eval_stage_b.mjs --url http://127.0.0.1:8780 --out docs/evaluation/fresh_synthetic/run1
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const arg = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const URL_ = arg("--url", "http://127.0.0.1:8780");
const OUT = arg("--out", "docs/evaluation/fresh_synthetic/run1");
const SET = "docs/evaluation/fresh_synthetic";
const only = arg("--only", null);
const order = fs.readFileSync(path.join(SET, "run_order.txt"), "utf8").split("\n").map((s) => s.trim()).filter(Boolean);
const expected = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(SET, "evaluator_only/expected_content.json"), "utf8")).records.map((r) => [r.id, r]));
const seedFile = arg("--seeds", "stage_b_box_corrections.json");
const seeds = JSON.parse(fs.readFileSync(path.join(OUT, seedFile), "utf8")); // hand-measured boxes for the off-target ones
const dir = path.join(OUT, arg("--stage-dir", "stage_b"));
fs.mkdirSync(dir, { recursive: true });
const norm = (s) => s.normalize("NFC").replace(/\s+/g, " ").trim();
const LEG = { brand_mark: "Logo", product_image: "Product image", headline: "Headline", price: "Price", cta: "Button", legal: "Small print" };

const browser = await chromium.launch();
for (const rel of order) {
  const name = path.basename(rel, ".png");
  if (only && name !== only) continue;
  const exp = expected[name];
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
  const page = await ctx.newPage();
  const log = { image: rel, corrections: [], events: [] };
  const t0 = Date.now();
  const text = async () => (await page.locator("body").innerText()).replace(/\s+/g, " ");
  const row = (legend) => page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: legend }) });
  page.on("response", async (r) => {
    if (/\/(runs|answer)$/.test(r.url()) && r.request().method() === "POST") log.events.push({ url: r.url().split("/").slice(-1)[0], status: r.status() });
  });
  await page.goto(`${URL_}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
  await page.locator("input[type=file]").setInputFiles(path.join(SET, rel));
  await page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 90_000 });
  await page.waitForTimeout(600);
  // the replayed read must equal Stage A (same editor values after the app's own snapping)
  const read = async () => page.evaluate(() => [...document.querySelectorAll("fieldset.lrow")].map((f) => [f.querySelector("legend")?.innerText ?? "", [...f.querySelectorAll("input, textarea")].map((i) => (i.type === "checkbox" ? i.checked : i.value))]));
  const a = JSON.parse(fs.readFileSync(path.join(OUT, "stage_a", `${name}.editor_after_snap.json`), "utf8")).fields.map((f) => [f.legend, f.values.map((v) => v.value)]);
  const b = await read();
  log.replay_equals_stage_a = JSON.stringify(a) === JSON.stringify(b);
  // text corrections: a field whose normalised text differs from the expected string
  const wantText = { headline: exp.headline, price: exp.price_text, cta: exp.cta, legal: exp.legal };
  for (const [role, want] of Object.entries(wantText)) {
    const r = row(LEG[role]).locator("textarea, input[type=text]").first();
    const have = await r.inputValue();
    if (norm(have) !== norm(want)) { await r.fill(want); log.corrections.push({ kind: "text", role, from: have, to: want }); }
  }
  // box corrections: only the boxes judged off target in Stage A scoring
  for (const [role, box] of Object.entries(seeds[name] ?? {})) {
    const r = row(LEG[role]);
    const was = [];
    for (const [i, label] of ["Left", "Top", "Width", "Height"].entries()) { const f = r.getByLabel(label, { exact: true }); was.push(Number(await f.inputValue())); await f.fill(String(box[i])); }
    log.corrections.push({ kind: "box", role, from: was, to: box });
  }
  if ((seeds[name] ?? {}).snap && (await page.getByRole("button", { name: /Snap boxes/ }).isEnabled())) { await page.getByRole("button", { name: /Snap boxes/ }).click(); log.events.push("snap all (not counted as a correction: the app's own measuring)"); }
  log.editor_text = (await text()).slice(0, 1500);
  await page.screenshot({ path: path.join(dir, `${name}.editor_corrected.png`), fullPage: true });
  const build = page.getByRole("button", { name: "Looks right: make the story card" });
  const blocked = (await text()).match(/Fix before continuing:(.{0,200})/);
  log.blocked_in_editor = blocked ? blocked[1].trim() : null;
  log.build_enabled = (await build.isEnabled()) && !blocked;
  if (log.build_enabled) {
    await build.click();
    try {
      await page.getByRole("heading", { level: 2, name: /Your story card|It needs one decision/ }).waitFor({ timeout: 120_000 });
    } catch { log.events.push("no result or question within 120 s"); }
    if (await page.getByRole("heading", { level: 2, name: "It needs one decision from you" }).count()) {
      log.question = (await text()).slice(0, 1500);
      await page.screenshot({ path: path.join(dir, `${name}.question.png`), fullPage: true });
      const split = page.getByRole("button", { name: /Split across two cards/ }).first();
      const shrink = page.getByRole("button", { name: /Shrink the product image/ }).first();
      const pick = (await split.isEnabled()) ? ["split", split] : (await shrink.isEnabled()) ? ["shrink", shrink] : ["neither", page.getByRole("button", { name: /Neither/ })];
      log.answer = pick[0];
      await pick[1].click();
      await page.waitForTimeout(500);
      await page.getByRole("heading", { level: 2, name: /Your story card|Your banner/ }).waitFor({ timeout: 90_000 }).catch(() => {});
    }
  }
  const final = await text();
  log.final_text = final.slice(0, 2500);
  log.checks = (final.match(/(\d+) of (\d+) checks passed/) ?? []).slice(1, 3).map(Number);
  const links = await page.locator("a[download]").evaluateAll((as) => as.map((a) => [a.getAttribute("download"), a.getAttribute("href")]));
  for (const [i, [dl, href]] of links.entries()) if (href?.startsWith("data:image/png")) fs.writeFileSync(path.join(dir, `${name}.export_${i + 1}_${(dl ?? "").replace(/[^\w.-]/g, "_")}`), Buffer.from(href.split(",")[1], "base64"));
  await page.screenshot({ path: path.join(dir, `${name}.result.png`), fullPage: true });
  log.elapsed_s = (Date.now() - t0) / 1000;
  fs.writeFileSync(path.join(dir, `${name}.json`), JSON.stringify(log, null, 1));
  console.log(name, "corrections", log.corrections.length, "checks", log.checks, "answer", log.answer ?? "-", "replay==A", log.replay_equals_stage_a, `${log.elapsed_s.toFixed(0)}s`);
  await ctx.close();
}
await browser.close();

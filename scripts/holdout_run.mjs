// Held-out run, one pass, live models, through the real Adapt screen (docs/evaluation/holdout/PROTOCOL.md). The raw reading is written to disk
// before the expected text is looked at. The scripted operator edits only text that differs from the expected text; it never edits a box.
//   node scripts/holdout_run.mjs --url http://127.0.0.1:8780 --from 1 --to 8 --out docs/evaluation/holdout/run1
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";

const arg = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const URL_ = arg("--url", "http://127.0.0.1:8780");
const FROM = Number(arg("--from", "1")), TO = Number(arg("--to", "17"));
const OUT = arg("--out", "docs/evaluation/holdout/run1");
const DIR = "docs/evaluation/holdout";
const files = JSON.parse(fs.readFileSync(`${DIR}/manifest.json`, "utf8")).map((m) => m.file).slice(FROM - 1, TO);
fs.mkdirSync(OUT, { recursive: true });
const norm = (s) => s.normalize("NFC").replace(/\s+/g, " ").trim();
const LEG = { headline: "Headline", price: "Price", cta: "Button", legal: "Small print" };
const browser = await chromium.launch();
for (const file of files) {
  const id = file.replace(".jpeg", "");
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 1000 } })).newPage();
  const log = { file, events: [], corrections: [] };
  const t0 = Date.now();
  const text = async () => (await page.locator("body").innerText()).replace(/\s+/g, " ");
  const row = (l) => page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: l }) });
  let upload = null;
  page.on("response", async (r) => {
    if (/\/uploads$/.test(r.url()) && r.request().method() === "POST") upload = { status: r.status(), body: await r.json().catch(() => null) };
    if (/\/(runs|answer)$/.test(r.url()) && r.request().method() === "POST") log.events.push({ url: r.url().split("/").pop(), status: r.status() });
  });
  await page.goto(`${URL_}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
  const buf = fs.readFileSync(`${DIR}/inputs/${file}`);
  await page.locator("input[type=file]").setInputFiles({ name: file, mimeType: "image/jpeg", buffer: buf });
  // wait for the editor, the busy-background screen, or an error
  const which = await Promise.race([
    page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 150_000 }).then(() => "editor"),
    page.getByRole("alert").filter({ hasText: /photo or busy background/ }).waitFor({ timeout: 150_000 }).then(() => "refused_background"),
  ]).catch(() => "none");
  log.stage = which;
  if (upload) fs.writeFileSync(path.join(OUT, `${id}.raw_upload_response.json`), JSON.stringify(upload, null, 1)); // BEFORE expected is read
  if (which === "refused_background") {
    log.note = "refused before any model call; operator took 'Choose another banner'";
    log.model_called = upload !== null;
    await page.screenshot({ path: path.join(OUT, `${id}.refused.png`), fullPage: true });
    fs.writeFileSync(path.join(OUT, `${id}.json`), JSON.stringify(log, null, 1));
    console.log(id, which);
    await page.context().close();
    continue;
  }
  if (which !== "editor") {
    log.note = (await text()).slice(0, 400);
    await page.screenshot({ path: path.join(OUT, `${id}.no_editor.png`), fullPage: true });
    fs.writeFileSync(path.join(OUT, `${id}.json`), JSON.stringify(log, null, 1));
    console.log(id, "no editor", log.note.slice(0, 120));
    await page.context().close();
    continue;
  }
  await page.waitForTimeout(700);
  const exp = JSON.parse(fs.readFileSync(`${DIR}/expected.json`, "utf8")).find((e) => e.file === file);
  const want = { headline: exp.headline, price: exp.price, cta: exp.cta, legal: exp.legal };
  const roles = (upload?.body?.layers ?? []).map((l) => l.role);
  log.raw = { origin: upload?.body?.origin, model: upload?.body?.model, roles, has_all_roles: ["brand_mark", "product_image", "headline", "price", "cta", "legal"].every((r) => roles.includes(r)),
    raw_text_exact: Object.fromEntries(Object.entries(want).map(([r, w]) => [r, norm((upload?.body?.layers ?? []).find((l) => l.role === r)?.text ?? "") === norm(w)])) };
  log.snap_note = (await text()).match(/The boxes were snapped[^.]*\./)?.[0] ?? null;
  await page.screenshot({ path: path.join(OUT, `${id}.editor.png`), fullPage: true });
  for (const [role, w] of Object.entries(want)) {
    const el = row(LEG[role]).locator("textarea, input[type=text]").first();
    if ((await el.count()) === 0) { log.corrections.push({ role, kind: "missing field", want: w }); continue; }
    const have = await el.inputValue();
    if (norm(have) !== norm(w)) { await el.fill(w); log.corrections.push({ role, kind: "text", from: have, to: w }); }
  }
  const blocked = (await text()).match(/Fix before continuing:(.{0,220})/);
  log.blocked_in_editor = blocked ? blocked[1].trim() : null;
  const build = page.getByRole("button", { name: "Looks right: make the story card" });
  if (!blocked && (await build.isEnabled())) {
    await build.click();
    await page.getByRole("heading", { level: 2, name: /Your story card|It needs one decision/ }).waitFor({ timeout: 150_000 }).catch(() => log.events.push("no result within 150 s"));
    if (await page.getByRole("heading", { level: 2, name: "It needs one decision from you" }).count()) {
      log.question = (await text()).slice(0, 900);
      await page.screenshot({ path: path.join(OUT, `${id}.question.png`), fullPage: true });
      const split = page.getByRole("button", { name: /Split across two cards/ }).first();
      const shrink = page.getByRole("button", { name: /Shrink the product image/ }).first();
      const pick = (await split.count()) && (await split.isEnabled()) ? ["split", split] : (await shrink.count()) && (await shrink.isEnabled()) ? ["shrink", shrink] : ["none_fits", null];
      log.answer = pick[0];
      if (pick[1]) { await pick[1].click(); await page.getByRole("heading", { level: 2, name: /Your story card/ }).waitFor({ timeout: 90_000 }).catch(() => {}); }
    }
  }
  const final = await text();
  log.checks = (final.match(/(\d+) of (\d+) structure checks passed/) ?? []).slice(1, 3).map(Number);
  const links = await page.locator("a[download]").evaluateAll((as) => as.map((a) => [a.getAttribute("download"), a.getAttribute("href")]));
  for (const [i, [dl, href]] of links.entries()) if (href?.startsWith("data:image/png")) fs.writeFileSync(path.join(OUT, `${id}.export_${i + 1}_${(dl ?? "").replace(/[^\w.-]/g, "_")}`), Buffer.from(href.split(",")[1], "base64"));
  log.final_text = final.slice(0, 1800);
  await page.screenshot({ path: path.join(OUT, `${id}.result.png`), fullPage: true });
  log.elapsed_s = (Date.now() - t0) / 1000;
  fs.writeFileSync(path.join(OUT, `${id}.json`), JSON.stringify(log, null, 1));
  console.log(id, "corrections", log.corrections.length, "checks", log.checks, "answer", log.answer ?? "-", log.blocked_in_editor ? "BLOCKED" : "");
  await page.context().close();
}
await browser.close();

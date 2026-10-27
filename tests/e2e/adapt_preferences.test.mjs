// The saved-choice sequence through the real Adapt screen and real request payloads (no model, no spend: the owner types the words
// on the manual template). Run: npm run build:web && OA_E2E=1 node --test tests/e2e/adapt_preferences.test.mjs
//   1 a German banner asks; shrink is saved (v1)      2 a different German banner reuses it without asking
//   3 a German banner where shrink cannot fit asks again; the answer is sent with v1 and saved as v2
//   4 another language still asks, and so does a fresh workspace (reload)
//   5 a question shown before the choice changed cannot overwrite the newer one: 409, a plain message, nothing saved
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PORT = Number(process.env.OA_E2E_PREFS_PORT ?? 8771);
const API = `http://127.0.0.1:${PORT}`;
const enabled = process.env.OA_E2E === "1";
let server, browser, store;

async function waitReady(url, ms = 90_000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      const r = await fetch(url);
      if (r.ok && (await r.json()).engine) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`server at ${url} did not become ready`);
}

// words of the repository's own fixtures: A fits both layouts, B has a small print so long that shrinking cannot fit
const DE = {
  A: ["Bring die Stadt endlich zum Schweigen – mit aktiver Geräuschunterdrückung.", "Jetzt 179 € (statt 249 €)", "Jetzt kaufen", "Angebot gültig bis 31.10.2026, solange der Vorrat reicht. Es gelten die AGB der Halden Audio GmbH. Abbildung ähnlich."],
  A2: ["Hören Sie nur, was zählt – mit aktiver Geräuschunterdrückung.", "Jetzt 179 € (statt 249 €)", "Jetzt kaufen", "Angebot gültig bis 31.10.2026, solange der Vorrat reicht. Es gelten die AGB der Halden Audio GmbH. Abbildung ähnlich."],
  B: ["Bring die Stadt endlich zum Schweigen – mit aktiver Geräuschunterdrückung.", "Jetzt 179 € (statt 249 €)", "Jetzt kaufen", "Angebot gültig bis 31.10.2026 und nur, solange der Vorrat reicht. Es gelten die Allgemeinen Geschäftsbedingungen der Halden Audio GmbH, Musterstraße 1, 10115 Berlin. Unverbindliche Preisempfehlung des Herstellers. Alle Preise inklusive gesetzlicher Mehrwertsteuer. Abbildung ähnlich, Farbabweichungen möglich. Versandkostenfrei innerhalb Deutschlands ab einem Bestellwert von 50 €. Rückgabe innerhalb von 30 Tagen nach Erhalt der Ware möglich. Die gesetzliche Gewährleistung bleibt unberührt."],
};
const FR = ["Faites taire la ville grâce à la réduction de bruit active nouvelle génération.", "179 € au lieu de 249 €", "Acheter", "Offre valable jusqu'au 31/10/2026 dans la limite des stocks disponibles. Voir conditions générales."];

describe("Saved choices through the Adapt screen", { skip: !enabled && "set OA_E2E=1 to run browser tests" }, () => {
  before(async () => {
    assert.ok(fs.existsSync(path.join(ROOT, "apps/web/dist/index.html")), "build the web app first: npm run build:web");
    store = fs.mkdtempSync(path.join(os.tmpdir(), "oa-prefs-"));
    const py = process.env.OA_PYTHON ?? path.join(ROOT, ".venv/bin/python");
    server = spawn(py, ["-m", "uvicorn", "open_apprentice.api.app:app", "--port", String(PORT)], {
      cwd: ROOT,
      env: { ...process.env, PYTHONPATH: path.join(ROOT, "src"), DEMO_MODEL_ENABLED: "0", OA_STORE_DIR: store },
      stdio: "ignore",
    });
    await waitReady(`${API}/health/ready`);
    browser = await chromium.launch();
  });
  after(async () => {
    await browser?.close();
    server?.kill("SIGTERM");
    if (store) fs.rmSync(store, { recursive: true, force: true });
  });

  test("v1 shrink, reuse on another banner, v2 split with the version sent, other language and workspace unaffected, stale question refused", async () => {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 1000 } })).newPage();
    const answers = [];
    let wid = null;
    const banners = [];
    page.on("request", (r) => {
      const m = r.url().match(/workspaces\/([0-9a-f]{32})/);
      if (m) wid = m[1];
      if (/\/runs\/[^/]+\/answer$/.test(r.url())) answers.push(JSON.parse(r.postData()));
    });
    page.on("response", async (r) => {
      if (/\/uploads\/[^/]+\/confirm$/.test(r.url()) && r.ok()) banners.push((await r.json()).banner_id);
    });
    const text = async () => (await page.locator("body").innerText()).replace(/\s+/g, " ");
    const prefs = async (w) => (await (await fetch(`${API}/api/campaign/workspaces/${w}/preferences`)).json()).scopes;
    const row = (legend) => page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: legend }) });
    const fixtures = (await (await fetch(`${API}/api/campaign/fixtures`)).json()).fixtures;
    const png = (id) => Buffer.from(fixtures.find((f) => f.id === id).png.split(",")[1], "base64");

    const adapt = async (art, words, lang) => {
      await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
      await page.locator("input[type=file]").setInputFiles({ name: "banner.png", mimeType: "image/png", buffer: png(art) });
      await page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 60_000 });
      for (const [legend, v] of [["Headline", words[0]], ["Price", words[1]], ["Button", words[2]], ["Small print", words[3]]]) await row(legend).locator("textarea, input[type=text]").first().fill(v);
      await page.getByLabel("Language (2 letters)").fill(lang);
      await page.getByRole("button", { name: "Looks right: make the story card" }).click();
      await page.getByRole("heading", { level: 2, name: /Your story card|It needs one decision/ }).waitFor({ timeout: 90_000 });
    };
    const again = async () => {
      await page.getByRole("button", { name: "Adapt another banner" }).click();
      await page.getByRole("heading", { name: "Bring a banner. Get story cards, checked." }).waitFor();
    };

    await page.goto(`${API}/`, { waitUntil: "networkidle" });
    // 1: a first German banner asks; both layouts fit; shrink is chosen
    await adapt("de_long_a", DE.A, "de");
    await page.getByRole("heading", { level: 2, name: "It needs one decision from you" }).waitFor();
    await page.getByRole("button", { name: /Shrink/i }).first().click();
    await page.getByRole("heading", { level: 2, name: "Your story card" }).waitFor({ timeout: 60_000 });
    assert.deepEqual(answers.at(-1), { choice: "builtin_shrink_hero", expected_version: null }); // nothing saved yet: no version
    assert.match(await text(), /remembered for this workspace: .*for de \(version 1\)/);
    // 2: a different German banner (other artwork, other words) reuses it and does not ask
    await again();
    await adapt("short_b", DE.A2, "de");
    await page.getByRole("heading", { level: 2, name: "Your story card" }).waitFor();
    assert.match(await text(), /\(version 1\)/);
    assert.equal(answers.length, 1, "no question was asked, so no answer was sent");
    // 3: a German banner where shrink cannot fit asks again; the answer carries the version the question was shown under
    await again();
    await adapt("de_long_b", DE.B, "de");
    await page.getByRole("heading", { level: 2, name: "It needs one decision from you" }).waitFor();
    await page.getByRole("button", { name: /Split/i }).first().click();
    await page.getByRole("heading", { level: 2, name: "Your story card" }).waitFor({ timeout: 60_000 });
    assert.deepEqual(answers.at(-1), { choice: "builtin_split_two_cards", expected_version: 1 });
    assert.match(await text(), /for de \(version 2\)/);
    const w1 = wid;
    assert.deepEqual((await prefs(w1)).filter((s) => s.active).map((s) => [s.locale, s.active.version, s.active.outcome]), [["de", 2, "builtin_split_two_cards"]]);
    // 4: another language is unaffected (it asks, nothing saved for it yet)
    await again();
    await adapt("fr_long", FR, "fr");
    await page.getByRole("heading", { level: 2, name: "It needs one decision from you" }).waitFor();
    assert.equal((await prefs(w1)).filter((s) => s.locale === "fr" && s.active).length, 0);
    // 5: this French question is on screen (shown with no saved French choice). Another answer saves one first...
    const bannerId = banners.at(-1);
    const other = await (await fetch(`${API}/api/campaign/workspaces/${w1}/runs`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ fixture_id: bannerId }) })).json();
    assert.equal(other.status, "question");
    const saved = await fetch(`${API}/api/campaign/workspaces/${w1}/runs/${other.run_id}/answer`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ choice: "builtin_split_two_cards", expected_version: null }) });
    assert.equal(saved.status, 200);
    // ...so answering the older question on screen is refused with a plain message, and the newer choice stands
    await page.getByRole("button", { name: /Shrink/i }).first().click();
    await page.getByRole("alert").filter({ hasText: /changed after this question was shown/ }).waitFor({ timeout: 30_000 });
    assert.equal(answers.at(-1).expected_version, null);
    const fr = (await prefs(w1)).find((s) => s.locale === "fr");
    assert.deepEqual([fr.active.version, fr.active.outcome], [1, "builtin_split_two_cards"]);
    // a fresh workspace (reload) has none of this: the same German banner asks again
    await page.goto(`${API}/`, { waitUntil: "networkidle" });
    await adapt("de_long_a", DE.A, "de");
    await page.getByRole("heading", { level: 2, name: "It needs one decision from you" }).waitFor();
    assert.notEqual(wid, w1);
  });
});

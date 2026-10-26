// The Campaign tab in real Chromium against the real API and Konva engine (no model, no spend): learn the banner->story
// layout, run banners, answer the overflow question, reuse the saved preference, and see a broken banner stop.
// Run: npm run build:web && OA_E2E=1 node --test tests/e2e/campaign.test.mjs   (needs Chromium and the Python env)
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PORT = Number(process.env.OA_E2E_CAMPAIGN_PORT ?? 8768);
const API = `http://127.0.0.1:${PORT}`;
const enabled = process.env.OA_E2E === "1";

let server;
let browser;
let store;

async function waitReady(url, ms = 90_000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      const r = await fetch(url);
      if (r.ok && (await r.json()).engine) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`server at ${url} did not become ready`);
}

describe("Campaign tab in a real browser", { skip: !enabled && "set OA_E2E=1 to run browser tests" }, () => {
  before(async () => {
    assert.ok(fs.existsSync(path.join(ROOT, "apps/web/dist/index.html")), "build the web app first: npm run build:web");
    store = fs.mkdtempSync(path.join(os.tmpdir(), "oa-campaign-"));
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

  test("learn, run, ask, answer, reuse and stop on a broken banner", async () => {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 1000 } })).newPage();
    const problems = [];
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message.slice(0, 160)}`));
    page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text().slice(0, 160)}`));
    page.on("response", (r) => r.status() >= 400 && problems.push(`HTTP ${r.status()} ${r.url()}`));
    const text = () => page.locator("main").innerText();
    const banner = (id) => page.getByRole("button", { name: new RegExp(`^${id}\\b`) });
    const run = async (id) => {
      const done = page.waitForResponse((r) => /\/api\/campaign\/workspaces\/[0-9a-f]+\/runs$/.test(r.url()));
      await banner(id).click();
      await done;
      await page.waitForLoadState("networkidle");
    };
    const pick = async (label) => {
      const done = page.waitForResponse((r) => /\/answer$/.test(r.url()));
      await page.getByRole("button", { name: label }).click();
      await done;
      await page.waitForLoadState("networkidle");
    };
    const prefRow = (loc) => page.locator("table.data tr", { has: page.locator("td", { hasText: new RegExp(`^${loc}$`) }) });

    await page.goto(`${API}/#campaign`, { waitUntil: "networkidle" });
    const learned = page.waitForResponse((r) => /\/api\/campaign\/workspaces$/.test(r.url()) && r.request().method() === "POST");
    await page.getByRole("button", { name: "Learn this layout" }).click();
    await learned;
    await page.waitForLoadState("networkidle");
    assert.match(await text(), /Learned by\s+search/i);

    // one example, two readings of the product image: it asks once, both options rendered and verified on a test banner
    const q = page.getByLabel("Teaching question");
    assert.match(await q.innerText(), /fits two rules for the product image/);
    assert.equal(await q.locator("img").count(), 3, "test banner plus one render per reading");
    assert.ok(await page.getByRole("button", { name: /^short_a/ }).isDisabled(), "no run before the question is answered");
    const chosen = page.waitForResponse((r) => /\/reading$/.test(r.url()) && r.request().method() === "POST");
    await page.getByRole("button", { name: "Same frame every time" }).click();
    await chosen;
    await page.waitForLoadState("networkidle");
    const work = await page.getByLabel("Learned rule").innerText();
    assert.match(work, /same frame every time/);

    await run("short_a");
    assert.match(await text(), /15 of 15 checks passed/);

    await run("de_long_a");
    await page.getByText(/Which tradeoff should this rule make/).first().waitFor({ timeout: 20_000 }); // a slow runner renders after the response
    assert.match(await text(), /Which tradeoff should this rule make/);
    assert.equal(await page.locator(".preview img").count(), 2);
    await pick("Shrink the product image");
    assert.match(await text(), /Applied result/);
    assert.match(await text(), /15 of 15 checks passed/);
    assert.match(await prefRow("de").innerText(), /Shrink the product image \(v1\)/);

    await run("de_long_b");
    assert.ok(await page.getByRole("button", { name: "Shrink the product image" }).isDisabled());
    assert.match(await text(), /does not fit/i);
    await pick("Split across two cards");
    assert.match(await text(), /15 of 15 checks passed/);
    assert.match(await prefRow("de").innerText(), /Split across two cards \(v2\)/);

    await run("de_long_a");
    assert.match(await text(), /Saved preference: Split across two cards v2/i);
    assert.doesNotMatch(await text(), /Which tradeoff/);

    await page.getByRole("radio", { name: "Fabric" }).check();
    await run("short_a");
    assert.match(await text(), /engine: fabric/i);
    assert.match(await text(), /15 of 15 checks passed/);
    await page.getByRole("radio", { name: "Konva" }).check();

    await banner("untagged_short_b").click();
    await page.getByRole("button", { name: "Confirm roles and run" }).waitFor();
    assert.match(await text(), /Roles proposed by/);
    const confirmed = page.waitForResponse((r) => /\/api\/campaign\/workspaces\/[0-9a-f]+\/runs$/.test(r.url()));
    await page.getByRole("button", { name: "Confirm roles and run" }).click();
    await confirmed;
    await page.waitForLoadState("networkidle");
    assert.match(await text(), /15 of 15 checks passed/);

    await run("missing_role");
    assert.match(await page.getByRole("alert").innerText(), /role headline is missing/);

    assert.deepEqual(problems, []);
  });
});

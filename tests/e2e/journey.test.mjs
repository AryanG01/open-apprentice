// The whole Apprentice flow in real Chromium against the real API and engine, offline learner (no model, no spend):
// import → map → teach → clarify/preview → commit → reuse → download → correct, plus reload, double submit, overlay
// alignment, live-unavailable wording, cancel, and the earlier prototype tab.
// Run: npm run build:web && OA_E2E=1 node --test tests/e2e/journey.test.mjs   (needs Chromium and the Python env)
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PORT = Number(process.env.OA_E2E_JOURNEY_PORT ?? 8767);
const API = `http://127.0.0.1:${PORT}`;
const CORPUS = path.join(ROOT, "tests/fixtures/drawio_corpus/dev");
const enabled = process.env.OA_E2E === "1";
const LIVE_UNAVAILABLE = "Live inference is unavailable. Open the recorded example.";
const TERMINAL = ["committed", "failed", "cancelled", "activated", "activation_rejected", "override", "dismissed"];

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

const until = async (fn, what, ms = 60_000) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 250));
  }
};

const n = (s) => (String(s).includes("/") ? Number(s.split("/")[0]) / Number(s.split("/")[1]) : Number(s));
const state = (page) => page.locator("[data-state]").getAttribute("data-state");

/** Answer whatever question is open with the first acceptable choice until the session ends. */
async function answerUntilDone(page) {
  for (let i = 0; i < 12; i++) {
    const s = await until(async () => {
      const st = await state(page).catch(() => null);
      if (st && TERMINAL.includes(st)) return st;
      if (await page.locator("section.question").count()) return "question";
      return null;
    }, "a question or the end of the session", 90_000);
    if (s !== "question") return s;
    const before = await page.locator("section.question").getAttribute("data-request-id");
    if (await page.locator("fieldset[data-item]").count()) {
      for (const fs_ of await page.locator("fieldset[data-item]").all()) {
        const approve = fs_.getByLabel("Approve");
        if (await approve.isEnabled()) await approve.check();
        else await fs_.getByLabel("Reject").check();
      }
      await page.getByRole("button", { name: "Submit verdicts" }).click();
    } else {
      await page.locator('input[name="alt"], input[name="interp"]').first().check();
      await page.getByRole("button", { name: "Submit answer" }).click();
    }
    await until(async () => {
      const st = await state(page).catch(() => null);
      if (st && TERMINAL.includes(st)) return true;
      const now = await page.locator("section.question").getAttribute("data-request-id").catch(() => null);
      return now !== before;
    }, "the next step after answering", 90_000);
  }
  throw new Error("too many questions");
}

/** Type "centred below its node, gap 8" into every mapped label's x/y fields. */
async function placeBelow(page, pageInfo, objs) {
  for (const [lid, m] of Object.entries(pageInfo.mapping.labels)) {
    const a = objs[m.node_id], o = objs[lid];
    await page.getByRole("button", { name: `label ${lid}`, exact: true }).click();
    await page.getByLabel(`x of ${lid}`).fill(String(n(a.x) + (n(a.w) - n(o.w)) / 2));
    await page.getByLabel(`y of ${lid}`).fill(String(n(a.y) + n(a.h) + 8));
  }
}

/** Mapping info of an imported document, read through the page's own cookie. */
async function docInfo(page, name) {
  const ids = JSON.parse(await page.evaluate(() => localStorage.getItem("oa.v2.docs") ?? "[]"));
  for (const id of ids) {
    const d = await (await page.request.get(`${API}/api/v2/documents/${id}`)).json();
    if (d.name === name) return d;
  }
  throw new Error(`document ${name} not found`);
}

describe("Apprentice journey in a real browser", { skip: !enabled && "set OA_E2E=1 to run browser tests" }, () => {
  before(async () => {
    assert.ok(fs.existsSync(path.join(ROOT, "apps/web/dist/index.html")), "build the web app first: npm run build:web");
    store = fs.mkdtempSync(path.join(os.tmpdir(), "oa-journey-"));
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

  test("teach, clarify, commit, reuse, download and correct", async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 }, acceptDownloads: true });
    const page = await ctx.newPage();
    const problems = [];
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message.slice(0, 160)}`));
    page.on("response", (r) => {
      if (r.status() >= 400 && !(r.status() === 503 && /\/api\/v2\/runs\//.test(r.url()))) problems.push(`HTTP ${r.status()} ${r.url()}`);
    });
    const sessions = [];
    const bodies = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && /\/api\/v2\/sessions$/.test(r.url())) bodies.push(r.postData());
    });
    page.on("response", async (r) => {
      if (r.request().method() === "POST" && /\/api\/v2\/sessions$/.test(r.url())) sessions.push(await r.json().catch(() => ({})));
    });

    // 1. import and map
    await page.goto(`${API}/#apprentice`, { waitUntil: "networkidle" });
    await page.getByLabel("Add .drawio files").setInputFiles([path.join(CORPUS, "d1.drawio"), path.join(CORPUS, "d2.drawio")]);
    await until(async () => (await page.getByRole("button", { name: "Confirm mapping" }).count()) === 2, "two rendered documents");
    for (let i = 0; i < 2; i++) await page.getByRole("button", { name: "Confirm mapping" }).first().click(), await page.waitForTimeout(400);
    await until(async () => (await page.getByText("Mapping confirmed ✓").count()) === 2, "two confirmed mappings");

    // 8. live unavailable wording (no live model on this server)
    assert.ok(await page.getByText(LIVE_UNAVAILABLE).isVisible());
    assert.ok(await page.getByLabel("Use the live model").isDisabled());

    // 2. teach on d1: every mapped label centred below its node, gap 8, typed into the label's x/y fields
    await page.getByLabel("Document to edit").selectOption({ label: "d1.drawio" });
    const d1 = await docInfo(page, "d1.drawio");
    const p1 = d1.pages.find((p) => p.status === "ok");
    const scene = await (await page.request.get(`${API}/api/v2/documents/${d1.doc_id}/pages/${p1.page_id}/scene?mapping_hash=${p1.mapping_hash}`)).json();
    const objs = Object.fromEntries(scene.objects.map((o) => [o.id, o]));
    await page.waitForSelector("button[data-label]");

    // 7. overlay alignment at two widths: each label button sits at (doc + image offset) × displayed scale
    for (const width of [1280, 800]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.waitForTimeout(400);
      const geo = await page.evaluate(() => {
        const img = document.querySelector(".docview-stage img");
        const r = img.getBoundingClientRect();
        return {
          scale: img.clientWidth / img.naturalWidth,
          ix: r.left,
          iy: r.top,
          labels: [...document.querySelectorAll(".docview-stage button[data-label]")].map((b) => {
            const q = b.getBoundingClientRect();
            return { id: b.dataset.label, x: q.left, y: q.top };
          }),
        };
      });
      const ox = n(scene.image_offset.x), oy = n(scene.image_offset.y);
      for (const l of geo.labels) {
        const o = objs[l.id];
        assert.ok(Math.abs(l.x - geo.ix - (n(o.x) + ox) * geo.scale) < 1.5, `x of ${l.id} at ${width}px`);
        assert.ok(Math.abs(l.y - geo.iy - (n(o.y) + oy) * geo.scale) < 1.5, `y of ${l.id} at ${width}px`);
      }
    }
    await page.setViewportSize({ width: 1280, height: 1000 });

    await placeBelow(page, p1, objs);
    const confirm = page.getByRole("button", { name: "This whole document is right" });
    await until(async () => confirm.isEnabled(), "the draft render to be seen");

    // 5 (focus). double submit creates one session
    await confirm.dblclick();
    await until(async () => /#apprentice\/s\/[0-9a-f]+/.test(page.url()), "the session in the URL");
    const sid = page.url().match(/s\/([0-9a-f]+)/)[1];
    assert.ok(sessions.length >= 1 && sessions.every((s) => s.session_id === sid), JSON.stringify(sessions));

    // 3 (focus). reload mid-question resumes the same question
    await until(async () => (await page.locator("section.question").count()) > 0 || TERMINAL.includes(await state(page).catch(() => "")), "first question");
    if (await page.locator("section.question").count()) {
      const rid = await page.locator("section.question").getAttribute("data-request-id");
      await page.reload({ waitUntil: "networkidle" });
      await until(async () => (await page.locator("section.question").count()) > 0, "the question after reload");
      assert.equal(await page.locator("section.question").getAttribute("data-request-id"), rid);
      assert.equal(page.url().match(/s\/([0-9a-f]+)/)[1], sid);
    }

    // preview cards name their document (not an id prefix)
    if (await page.locator("fieldset[data-item] legend").count()) {
      assert.match(await page.locator("fieldset[data-item] legend").first().innerText(), /\.drawio/);
      assert.match(await page.locator("fieldset[data-item] img").first().getAttribute("alt"), /\.drawio/);
    }

    // 4. answer through the preview until committed
    const taught = await answerUntilDone(page);
    const sstate = await (await page.request.get(`${API}/api/v2/sessions/${sid}`)).json();
    assert.equal(taught, "committed", JSON.stringify({ result: sstate.result, budgets: sstate.budgets, sent: bodies[0] }));
    assert.match(await page.locator(".prov").innerText(), /Model: Fixture · Teacher: You/);

    // the first skill read lands before activation finishes: Reuse must wait for the active version, not silently no-op
    let skillReads = 0;
    await page.route(/\/api\/v2\/skills\/[^/]+$/, async (route) => {
      if (skillReads++ === 0) {
        const real = await (await route.fetch()).json();
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...real, active: { version: null, generation: null } }) });
      }
      return route.continue();
    });
    await page.reload({ waitUntil: "networkidle" });

    // 5. reuse on d2 and d3
    await page.getByLabel("Add .drawio files").setInputFiles([path.join(CORPUS, "d3.drawio")]);
    await until(async () => (await page.getByRole("button", { name: "Confirm mapping" }).count()) === 1, "d3 rendered");
    await page.getByRole("button", { name: "Confirm mapping" }).click();
    await until(async () => (await page.getByText("Mapping confirmed ✓").count()) === 3, "three confirmed mappings");
    await page.locator("label.pick", { hasText: "d2.drawio" }).locator("input").check();
    await page.locator("label.pick", { hasText: "d3.drawio" }).locator("input").check();
    // a transient failure while polling the run must not freeze the results (the first poll gets a 503)
    let failedOnce = false;
    await page.route(/\/api\/v2\/runs\/[0-9a-f]+$/, async (route) => {
      if (!failedOnce && route.request().method() === "GET") {
        failedOnce = true;
        return route.fulfill({ status: 503, contentType: "application/json", body: '{"error":{"code":"TEMPORARY","message":"try again"}}' });
      }
      return route.continue();
    });
    await page.getByRole("button", { name: "Apply" }).click();
    try {
      await until(async () => (await page.locator("article.result").count()) === 2 && !(await page.getByText("Run running").count()), "two results", 150_000);
    } catch (e) {
      const runId = await page.locator("[data-run]").getAttribute("data-run").catch(() => null);
      const run = runId ? await (await page.request.get(`${API}/api/v2/runs/${runId}`)).json() : null;
      throw new Error(`${e.message}: run ${JSON.stringify(run)?.slice(0, 800)}; screen ${(await page.locator("#h-reuse").locator("..").innerText()).slice(0, 600)}`);
    }

    const d2 = page.locator('article.result[data-result="d2.drawio"]');
    assert.match(await d2.locator("h3").innerText(), /Published/);
    assert.equal(await d2.locator(".checks li").count(), 3);
    const d3 = page.locator('article.result[data-result="d3.drawio"]');
    const d3text = await d3.innerText();
    assert.ok(/Published/.test(d3text) || (/Blocked/.test(d3text) && (await d3.locator(".err").count()) === 1), d3text);
    const [download] = await Promise.all([page.waitForEvent("download"), d2.getByRole("link", { name: ".drawio" }).click()]);
    const file = await download.path();
    assert.ok(fs.readFileSync(file, "utf8").startsWith("<mxfile"));

    // 6. correct d2: move one label down by 2 units with the keyboard
    await d2.getByRole("button", { name: "Correct this document" }).click();
    await page.waitForSelector("#h-correct");
    const submit = page.getByRole("button", { name: "Submit correction" });
    await until(async () => !(await page.locator("[data-pending]").count()), "the run's output rendered");
    const first = page.locator("#h-correct ~ figure button[data-label]").first();
    await first.focus();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await until(async () => submit.isEnabled(), "the corrected render to be seen");
    await submit.click();
    await until(async () => (/#apprentice\/s\/[0-9a-f]+/.test(page.url()) && page.url().match(/s\/([0-9a-f]+)/)[1] !== sid), "the correction session");
    const end = await answerUntilDone(page);
    assert.ok(["activated", "override", "dismissed", "failed"].includes(end), end);

    // 9. cancel a fresh session from its first question
    await page.getByRole("button", { name: "Start over with these documents" }).click();
    await page.getByLabel("Document to edit").selectOption({ label: "d1.drawio" });
    await page.waitForSelector("button[data-label]");
    await placeBelow(page, p1, objs); // the same explainable demonstration, so the session reaches a question
    await until(async () => confirm.isEnabled(), "the draft render to be seen");
    await confirm.click();
    await until(async () => (await page.locator("section.question").count()) > 0 || TERMINAL.includes(await state(page).catch(() => "")), "the first question of the new session");
    if (await page.getByRole("button", { name: "Cancel session" }).count()) {
      const [cancelResp] = await Promise.all([
        page.waitForResponse((r) => /\/cancel$/.test(r.url())),
        page.getByRole("button", { name: "Cancel session" }).click(),
      ]);
      const sid2 = page.url().match(/s\/([0-9a-f]+)/)[1];
      try {
        await until(async () => (await state(page)) === "cancelled", "cancelled", 15_000);
      } catch (e) {
        const api = await (await page.request.get(`${API}/api/v2/sessions/${sid2}`)).json();
        throw new Error(`${e.message}: cancel ${cancelResp.status()} ${await cancelResp.text()}; ui ${await state(page)}; api ${api.state} ${JSON.stringify(api.result)}`);
      }
    }

    // 10. the earlier prototype still renders
    await page.getByRole("tab", { name: "Earlier prototype" }).click();
    await page.getByText("Try it live", { exact: true }).first().click();
    await page.waitForTimeout(800);
    assert.ok((await page.locator("body").innerText()).length > 500);

    assert.deepEqual(problems, []);
    await ctx.close();
  });

  test("draft renders gate the confirm button and keep the overlay aligned", async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
    const page = await ctx.newPage();
    await page.goto(`${API}/#apprentice`, { waitUntil: "networkidle" });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: "networkidle" });
    await page.getByLabel("Add .drawio files").setInputFiles([path.join(CORPUS, "d1.drawio"), path.join(CORPUS, "d2.drawio")]);
    await until(async () => (await page.getByRole("button", { name: "Confirm mapping" }).count()) === 2, "two rendered documents");
    for (let i = 0; i < 2; i++) await page.getByRole("button", { name: "Confirm mapping" }).first().click(), await page.waitForTimeout(400);
    await until(async () => (await page.getByText("Mapping confirmed ✓").count()) === 2, "two confirmed mappings");
    await page.getByLabel("Document to edit").selectOption({ label: "d1.drawio" });
    await page.waitForSelector("button[data-label]");
    const confirm = page.getByRole("button", { name: "This whole document is right" });
    const label = page.locator("button[data-label]").first();

    // Important 1: a slow render of edit A must not mark edit B as seen
    let release, fetched;
    const held = new Promise((r) => (release = r));
    const ready = new Promise((r) => (fetched = r));
    let first = true;
    await page.route("**/api/v2/documents/*/draft", async (route) => {
      if (!first) return route.continue();
      first = false;
      const response = await route.fetch(); // A's render is done on the server…
      fetched();
      await held; // …but delivered only after edit B has been made
      await route.fulfill({ response });
    });
    await label.focus();
    await page.keyboard.press("ArrowRight"); // edit A
    await ready; // A's draft has been rendered and is being held
    await page.keyboard.press("ArrowRight"); // edit B: its 300 ms timer has not fired yet
    release(); // A's image arrives at once, before B's request is even sent
    await page.waitForTimeout(150);
    assert.ok(await confirm.isDisabled(), "B's positions must not count as seen while A's image is shown");
    await until(async () => confirm.isEnabled(), "B's render to be seen", 30_000);
    await page.unroute("**/api/v2/documents/*/draft");

    // Important 2: a net-zero edit (same positions, same PNG) must not leave the button locked
    await label.focus();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowLeft");
    await until(async () => confirm.isEnabled(), "the unchanged render to count as seen", 15_000);

    // Important 4: after a draft that changes the image offset, the overlay follows the measured geometry
    const id = await label.getAttribute("data-label");
    await label.click();
    const [resp] = await Promise.all([
      page.waitForResponse((r) => /\/draft$/.test(r.url()) && r.request().method() === "POST"),
      page.getByLabel(`x of ${id}`).fill("-40"), // past the page's left edge: the rendered bounds and offset change
    ]);
    const draft = await resp.json();
    await until(async () => confirm.isEnabled(), "the off-page render to be seen", 15_000);
    const geo = await page.evaluate(() => {
      const img = document.querySelector(".docview-stage img");
      const r = img.getBoundingClientRect();
      return { scale: img.clientWidth / img.naturalWidth, ix: r.left, iy: r.top,
               labels: [...document.querySelectorAll(".docview-stage button[data-label]")].map((b) => ({ id: b.dataset.label, x: b.getBoundingClientRect().left, y: b.getBoundingClientRect().top })) };
    });
    const ox = n(draft.image_offset.x), oy = n(draft.image_offset.y);
    for (const l of geo.labels) {
      const b = draft.boxes[l.id];
      if (!b) continue;
      assert.ok(Math.abs(l.x - geo.ix - (n(b.x) + ox) * geo.scale) < 1.5, `x of ${l.id} after the draft`);
      assert.ok(Math.abs(l.y - geo.iy - (n(b.y) + oy) * geo.scale) < 1.5, `y of ${l.id} after the draft`);
    }
    await ctx.close();
  });
  test("a sample diagram imports with one click and renders", async () => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
    const page = await ctx.newPage();
    const problems = [];
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message.slice(0, 160)}`));
    await page.goto(`${API}/#apprentice`, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "Try a sample: Checkout service" }).click();
    await until(async () => (await page.getByRole("button", { name: "Confirm mapping" }).count()) === 1, "the sample rendered");
    assert.ok(await page.getByRole("heading", { name: "checkout-service.drawio" }).isVisible());
    assert.deepEqual(problems, []);
    await ctx.close();
  });
});

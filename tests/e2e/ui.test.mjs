// Browser smoke tests for the web app, driven through real Chromium against a real server and the real engine.
// Run:  OA_E2E=1 node --test tests/e2e/ui.test.mjs     (needs Chromium, the Python env, and the built web app: npm run build:web)
// Skipped unless OA_E2E=1. These exist because a hook placed after an early return once left "Try it live" blank
// and nothing noticed: every claim about the UI should be checked here, not by reading code.
import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const API_PORT = Number(process.env.OA_E2E_API_PORT ?? 8765);
const STATIC_PORT = Number(process.env.OA_E2E_STATIC_PORT ?? 8766);
const API = `http://127.0.0.1:${API_PORT}`;
const STATIC = `http://127.0.0.1:${STATIC_PORT}`;
const enabled = process.env.OA_E2E === "1";

let server;
let staticServer;
let browser;

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

/** Serves apps/web/dist with no API at all, like a static host. */
function serveStatic(dir, port) {
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json" };
  return new Promise((resolve) => {
    const s = http.createServer((req, res) => {
      const rel = req.url === "/" ? "/index.html" : req.url.split("?")[0];
      const file = path.join(dir, rel);
      if (!file.startsWith(dir) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404).end("not found");
        return;
      }
      res.writeHead(200, { "content-type": types[path.extname(file)] ?? "application/octet-stream" }).end(fs.readFileSync(file));
    });
    s.listen(port, "127.0.0.1", () => resolve(s));
  });
}

/** A page that records everything that should never happen. */
async function newPage(opts = {}, expected404 = /\/health\/ready$/) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 1000 }, acceptDownloads: true, ...opts });
  const page = await ctx.newPage();
  const problems = [];
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message.slice(0, 160)}`));
  page.on("response", (r) => {
    if (r.status() >= 400 && !expected404.test(r.url())) problems.push(`HTTP ${r.status()} ${r.url()}`);
  });
  return { page, problems, close: () => ctx.close() };
}

const bodyText = async (page) => (await page.locator("body").innerText()).replace(/\n+/g, " | ");

async function openTryIt(page, url) {
  await page.goto(`${url}/#home`, { waitUntil: "networkidle" }); // the badge demo lives under "Earlier prototype"
  await page.getByText("Try it live", { exact: true }).first().click();
}

/** Answer whichever question is showing (first option) until the rule is sealed. */
async function teachUntilSealed(page, pick = "first") {
  await page.getByRole("button", { name: /Start teaching/ }).click();
  await page.waitForSelector("text=/Which result did you mean|rule is sealed|No rule/", { timeout: 60_000 });
  for (let i = 0; i < 6 && (await page.getByRole("button", { name: "Submit answer" }).count()); i++) {
    const radios = page.locator("input[name=live-opt]");
    await (pick === "first" ? radios.first() : radios.nth(1)).check();
    await page.getByRole("button", { name: "Submit answer" }).click();
    await page.waitForTimeout(1200);
  }
  assert.match(await bodyText(page), /rule is sealed/i, "the rule should be sealed after answering");
}

async function run(page, backend, toolChange) {
  await page.locator("select").first().selectOption(backend);
  const box = page.getByLabel(/Silently change the tool/i);
  if ((await box.isEnabled()) && (await box.isChecked()) !== toolChange) await box.setChecked(toolChange);
  const [resp] = await Promise.all([
    page.waitForResponse((r) => /\/api\/teach\/[^/]+\/run$/.test(r.url()), { timeout: 90_000 }),
    page.getByRole("button", { name: /^Run$/ }).click(),
  ]);
  assert.equal(resp.status(), 200);
  await page.waitForSelector("text=/Binding origin/", { timeout: 30_000 });
  await page.waitForFunction(() => !/Working…/.test(document.body.innerText), null, { timeout: 30_000 });
  return bodyText(page);
}

describe("web app in a real browser", { skip: !enabled && "set OA_E2E=1 to run browser tests" }, () => {
  before(async () => {
    assert.ok(fs.existsSync(path.join(ROOT, "apps/web/dist/index.html")), "build the web app first: npm run build:web");
    const py = process.env.OA_PYTHON ?? path.join(ROOT, ".venv/bin/python");
    server = spawn(py, ["-m", "uvicorn", "open_apprentice.api.app:app", "--port", String(API_PORT)], {
      cwd: ROOT,
      env: { ...process.env, PYTHONPATH: path.join(ROOT, "src"), DEMO_MODEL_ENABLED: "0" },
      stdio: "ignore",
    });
    staticServer = await serveStatic(path.join(ROOT, "apps/web/dist"), STATIC_PORT);
    await waitReady(`${API}/health/ready`);
    browser = await chromium.launch();
  });

  after(async () => {
    await browser?.close();
    staticServer?.close();
    server?.kill("SIGTERM");
  });

  test("every tab renders with no page or network errors", async () => {
    const { page, problems, close } = await newPage();
    await page.goto(`${API}/#home`, { waitUntil: "networkidle" });
    for (const tab of ["Home", "Learn", "Reuse", "Transfer", "Challenge", "Compare", "Try it live", "Real SVG"]) {
      await page.getByText(tab, { exact: true }).first().click();
      await page.waitForTimeout(800);
      assert.ok((await page.locator("body").innerText()).length > 500, `${tab} tab rendered (almost) nothing`);
    }
    assert.deepEqual(problems, []);
    await close();
  });

  test("learner box only explains the selected option", async () => {
    const { page, problems, close } = await newPage();
    await openTryIt(page, API);
    await page.getByLabel(/Reference learner/i).check();
    const text = (await page.getByLabel("Live controls").innerText()).replace(/\n+/g, " | ");
    assert.doesNotMatch(text, /REPLAY of a real Nemotron run/, "replay text must not show while Reference is selected");
    assert.doesNotMatch(text, /DEMO_MODEL_ENABLED/, "operator instructions must not show in the learner box");
    assert.match(text, /not enabled on this server/i, "the disabled Nemotron option should say why");
    assert.deepEqual(problems, []);
    await close();
  });

  test("replay: teach, seal, run on Konva with a recorded model procedure, at zero cost", async (t) => {
    const ready = await (await fetch(`${API}/health/ready`)).json();
    if (!ready.replay?.available) return t.skip("no replay tape installed");
    const { page, problems, close } = await newPage();
    await openTryIt(page, API);
    await page.getByLabel(/Nemotron replay/i).check();
    assert.match(await bodyText(page), /REPLAY of a real Nemotron run/);
    await teachUntilSealed(page);
    const text = await run(page, "konva", false);
    assert.match(text, /Model usage REPLAY/);
    assert.match(text, /\$0\.000/);
    assert.match(text, /model-generated, accepted only after passing the real-backend checks/);
    assert.deepEqual(problems, []);
    await close();
  });

  test("repair, break, export and offline re-check (reference mode)", async () => {
    const { page, problems, close } = await newPage();
    await openTryIt(page, API);
    await page.getByLabel(/Reference learner/i).check();
    await teachUntilSealed(page);

    await run(page, "konva", false);
    await run(page, "fabric", false);
    const broken = await run(page, "fabric", true);
    assert.match(broken, /Reproduced native mismatch/);
    assert.match(broken, /Independent verifier\s*\|?\s*FAIL/i);
    const repairBtn = page.getByRole("button", { name: /Repair native procedure/ });
    assert.ok(await repairBtn.isEnabled(), "repair should be offered after a reproduced mismatch");

    await repairBtn.click();
    await page.waitForSelector("text=/Repaired\\./", { timeout: 90_000 });
    assert.match(await bodyText(page), /byte-identical/, "the rule hash must be unchanged by a repair");
    const after = await run(page, "fabric", true);
    assert.match(after, /Independent verifier\s*\|?\s*PASS/i);

    await page.getByRole("button", { name: /Try to break it/ }).click();
    await page.waitForSelector("text=/Could not break it|Broke it/", { timeout: 120_000 });
    assert.match(await bodyText(page), /Could not break it: 40 of 40 inputs passed/);

    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "oa-e2e-"));
    const [svgDl] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /Download editable SVG/ }).click()]);
    const svgPath = path.join(dir, "layout.svg");
    await svgDl.saveAs(svgPath);
    const svg = fs.readFileSync(svgPath, "utf8");
    assert.match(svg, /<svg[\s>]/);
    assert.match(svg, /<oa:rule>/);
    assert.doesNotMatch(svg, /<script/i);

    const [evDl] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /Evidence package/ }).click()]);
    const evPath = path.join(dir, "evidence.json");
    await evDl.saveAs(evPath);
    const raw = fs.readFileSync(evPath, "utf8");
    JSON.parse(raw);

    await page.getByRole("button", { name: /Re-check this package offline/ }).click();
    await page.waitForSelector("text=/Every offline check passed|offline check FAILED/", { timeout: 30_000 });
    assert.match(await bodyText(page), /Every offline check passed/);

    const tampered = raw.replace(/"verifier_passed":\s*true/, '"verifier_passed": false').replace(/"native_passed":\s*true/, '"native_passed": false');
    assert.notEqual(tampered, raw, "the tamper step must actually change the package");
    const tamperedPath = path.join(dir, "tampered.json");
    fs.writeFileSync(tamperedPath, tampered);
    await page.locator("input[type=file]").setInputFiles(tamperedPath);
    await page.waitForSelector("text=/At least one offline check FAILED/", { timeout: 30_000 });

    assert.deepEqual(problems, []);
    await close();
  });

  test("guided story, reference learner: teach, reuse, tool change, repair, stress test in one click", async () => {
    const { page, problems, close } = await newPage();
    await openTryIt(page, API);
    await page.getByRole("button", { name: /Watch the story/ }).first().click();
    await page.waitForSelector('[aria-label="Story"] strong:text-is("Done.")', { timeout: 180_000 });
    const text = await bodyText(page);
    assert.match(text, /Repair validated\./);
    assert.match(text, /byte-identical/);
    assert.match(text, /Re-run after the repair: independent verifier PASS/);
    assert.match(text, /Stress test: 40 of 40 generated inputs passed/);
    const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
    assert.ok(size.w <= 1280, `page is ${size.w}px wide: something overflows horizontally (the repair diff once did, by ~73,000 px)`);
    assert.ok(size.h < 5000, `page is ${size.h}px tall: something stretches it (the repair diff once made it 6,828px)`);
    assert.match(text, /Repaired\./, "the repair result should stay on screen");
    assert.match(text, /Passes after the silent tool change/, "after a repair the run panel must not claim it survived without one");
    assert.doesNotMatch(text, /Survived the silent tool change/);
    assert.match(text, /Could not break it: 40 of 40/, "the stress result should stay on screen");
    assert.deepEqual(problems, []);
    await close();
  });

  test("guided story, recorded Nemotron: labelled replay, no repair claimed", async (t) => {
    const ready = await (await fetch(`${API}/health/ready`)).json();
    if (!ready.replay?.available) return t.skip("no replay tape installed");
    const { page, problems, close } = await newPage();
    await openTryIt(page, API);
    await page.getByRole("button", { name: /Watch it with recorded Nemotron/ }).click();
    await page.waitForSelector('[aria-label="Story"] strong:text-is("Done.")', { timeout: 180_000 });
    const text = await bodyText(page);
    assert.match(text, /recorded Nemotron session, no model is called now/);
    assert.match(text, /Model usage REPLAY/);
    assert.match(text, /model-generated native procedure/);
    assert.match(text, /nothing to repair/);
    assert.match(text, /The recorded run contains no repair/);
    assert.doesNotMatch(text, /Repair validated/);
    assert.deepEqual(problems, []);
    await close();
  });

  test("skip link moves focus to the stage and keeps the current tab", async () => {
    const { page, problems, close } = await newPage();
    await page.goto(`${API}/#compare`, { waitUntil: "networkidle" }); // fresh page, deep-linked to a non-Home tab
    await page.keyboard.press("Tab"); // the skip link is the first focusable element, shown only on focus
    assert.equal(await page.evaluate(() => document.activeElement?.textContent?.trim()), "Skip to the canvas");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(500);
    assert.equal(await page.locator('nav[aria-label="Modes"] [role="tab"][aria-selected="true"]').innerText(), "Compare");
    assert.equal(await page.evaluate(() => document.activeElement?.id), "stage");
    assert.deepEqual(problems, []);
    await close();
  });

  test("leaving the live tab mid-story stops further API calls", async () => {
    const { page, close } = await newPage();
    await openTryIt(page, API);
    let calls = 0;
    page.on("request", (r) => { if (/\/api\/teach/.test(r.url())) calls += 1; });
    await page.getByRole("button", { name: /Watch the story/ }).first().click();
    await page.waitForTimeout(2500); // the story is mid-way: started, answering
    await page.getByText("Compare", { exact: true }).first().click();
    const atLeave = calls;
    await page.waitForTimeout(6000); // the story would have made several more calls in this time
    assert.ok(atLeave > 0, "the story should have started");
    assert.equal(calls, atLeave, "no API calls after leaving the tab");
    await close();
  });

  test("a static copy with no backend says so plainly", async () => {
    // a static host has no API: /health/ready and the SVG lane's /api calls legitimately 404 there
    const { page, problems, close } = await newPage({}, /\/(health\/ready|api\/.*)$/);
    await page.goto(`${STATIC}/#home`, { waitUntil: "networkidle" });
    for (const tab of ["Try it live", "Real SVG"]) {
      await page.getByText(tab, { exact: true }).first().click();
      await page.waitForTimeout(1500);
      assert.match(await page.locator(".banner").first().innerText(), /NOT AVAILABLE IN THIS COPY/);
    }
    await page.getByText("Try it live", { exact: true }).first().click();
    await page.waitForTimeout(800);
    const text = await bodyText(page);
    assert.match(text, /There is no live backend here/);
    assert.doesNotMatch(text, /HTTP 404/);
    assert.deepEqual(problems, []);
    await close();
  });
});

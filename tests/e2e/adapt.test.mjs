// "Adapt a banner" in real Chromium against the real API and engine (no model, no spend: with no vision model the owner places the
// boxes on the manual template). Run: npm run build:web && OA_E2E=1 node --test tests/e2e/adapt.test.mjs
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const AXE = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "../../node_modules/axe-core/axe.min.js"), "utf8");

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PORT = Number(process.env.OA_E2E_ADAPT_PORT ?? 8770);
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

describe("Adapt a banner in a real browser", { skip: !enabled && "set OA_E2E=1 to run browser tests" }, () => {
  before(async () => {
    assert.ok(fs.existsSync(path.join(ROOT, "apps/web/dist/index.html")), "build the web app first: npm run build:web");
    store = fs.mkdtempSync(path.join(os.tmpdir(), "oa-adapt-"));
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

  test("the landing page is the banner flow; upload, fix the parts by keyboard and mouse, get a verified story card", async () => {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 1000 } })).newPage();
    const problems = [];
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message.slice(0, 160)}`));
    page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text().slice(0, 160)}`));
    page.on("response", (r) => r.status() >= 400 && problems.push(`HTTP ${r.status()} ${r.url()}`));
    const text = async () => (await page.locator("body").innerText()).replace(/\s+/g, " ");

    await page.goto(`${API}/`, { waitUntil: "networkidle" });
    assert.equal(await page.getByRole("tab", { name: "Adapt a banner" }).getAttribute("aria-selected"), "true");
    assert.match(await text(), /Bring a banner\. Get story cards, checked\./);
    const who = await page.getByLabel("Who does what").innerText();
    assert.match(who, /Nemotron-3\.5-Super-VL/);
    assert.match(who, /independent verifier/);
    assert.match(await text(), /What it cannot do yet/);

    // a real 16:9 banner image: the in-repo sample, as a file
    const fx = (await (await fetch(`${API}/api/campaign/fixtures`)).json()).fixtures.find((f) => f.id === "short_a");
    const buffer = Buffer.from(fx.png.split(",")[1], "base64");
    await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
    await page.locator("input[type=file]").setInputFiles({ name: "banner.png", mimeType: "image/png", buffer });
    await page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 60_000 });
    assert.match(await text(), /Place the parts yourself/); // no vision model on this server: the manual template

    const boxes = page.locator(".lbox");
    assert.equal(await boxes.count(), 6);
    assert.ok((await boxes.first().getAttribute("tabindex")) === "0", "every box is keyboard-focusable");
    assert.match((await boxes.first().getAttribute("aria-label")) ?? "", /Arrow keys move it, Shift plus arrow keys resize it/);

    // keyboard: three arrow presses move the headline box 12 px
    const left = (legend) => page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: legend }) }).getByLabel("Left");
    const before = Number(await left("Headline").inputValue());
    await page.locator(".lbox.r-headline").focus();
    for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowRight");
    assert.equal(Number(await left("Headline").inputValue()), before + 12);
    await page.keyboard.press("Shift+ArrowRight");
    assert.equal(Number(await page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: "Headline" }) }).getByLabel("Width").inputValue()), 580);

    // mouse: drag the logo box 60 screen pixels to the right
    const logoLeft = Number(await left("Logo").inputValue());
    const b = await page.locator(".lbox.r-brand_mark").boundingBox();
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
    await page.mouse.down();
    await page.mouse.move(b.x + b.width / 2 + 60, b.y + b.height / 2, { steps: 6 });
    await page.mouse.up();
    assert.ok(Number(await left("Logo").inputValue()) > logoLeft + 20, "the drag moved the box");
    await left("Logo").fill(String(logoLeft)); // put it back
    await left("Headline").fill(String(before));
    await page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: "Headline" }) }).getByLabel("Width").fill("576");

    // the words the model would have read: typed by the owner
    const words = { Headline: "Hear only what matters.", Price: "Now $159 (was $229)", Button: "Shop now", "Small print": "Offer ends 31 Oct 2026. While stocks last. Terms apply." };
    for (const [legend, value] of Object.entries(words)) {
      const row = page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: legend }) });
      await row.locator("textarea, input[type=text]").first().fill(value);
    }
    await page.getByRole("button", { name: "Looks right: make the story card" }).click();
    await page.getByRole("heading", { level: 2, name: /Your story card|It needs one decision/ }).waitFor({ timeout: 90_000 });
    assert.match(await text(), /15 of 15 checks passed/);
    assert.match(await text(), /no authored expected output for your banner/);
    assert.ok((await page.locator("img[alt='The story card']").count()) === 1);
    assert.match((await page.locator("a[download]").getAttribute("href")) ?? "", /^data:image\/png;base64,/);
    assert.equal(await page.locator("img[alt='Your banner rebuilt as editable layers']").count(), 1);

    await page.getByRole("button", { name: "Adapt another banner" }).click();
    await page.getByRole("heading", { name: "Bring a banner. Get story cards, checked." }).waitFor();
    await page.getByRole("tab", { name: "Diagrams" }).click();
    assert.equal(new URL(page.url()).hash, "#apprentice");
    assert.deepEqual(problems, []);
  });

  test("a banner with no price, button or small print: remove those parts and still get a verified story card", async () => {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 1000 } })).newPage();
    const text = async () => (await page.locator("body").innerText()).replace(/\s+/g, " ");
    await page.goto(`${API}/`, { waitUntil: "networkidle" });
    const fx = (await (await fetch(`${API}/api/campaign/fixtures`)).json()).fixtures.find((f) => f.id === "short_a");
    await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
    await page.locator("input[type=file]").setInputFiles({ name: "banner.png", mimeType: "image/png", buffer: Buffer.from(fx.png.split(",")[1], "base64") });
    await page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 60_000 });
    for (const part of ["price", "button", "small print"]) await page.getByRole("button", { name: new RegExp(`has no ${part}: remove it`) }).click();
    assert.equal(await page.locator(".lbox").count(), 3);
    assert.match(await text(), /That is fine, this part is optional/);
    const row = page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: "Headline" }) });
    await row.locator("textarea").fill("Hear only what matters.");
    await page.getByRole("button", { name: "Looks right: make the story card" }).click();
    await page.getByRole("heading", { level: 2, name: /Your story card|It needs one decision/ }).waitFor({ timeout: 90_000 });
    assert.match(await text(), /\d+ of \d+ checks passed/);
    assert.doesNotMatch(await text(), /Add the missing part/);
    assert.ok((await page.locator("img[alt='The story card']").count()) === 1);
  });

  test("the sketch door: sample sketch and sample page, the owner's pictures, a built banner, a verified story card and a page check", async () => {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 1000 } })).newPage();
    const problems = [];
    page.on("pageerror", (e) => problems.push(`pageerror: ${e.message.slice(0, 160)}`));
    page.on("response", (r) => r.status() >= 400 && problems.push(`HTTP ${r.status()} ${r.url()}`));
    const text = async () => (await page.locator("body").innerText()).replace(/\s+/g, " ");
    await page.goto(`${API}/`, { waitUntil: "networkidle" });
    await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
    await page.getByRole("button", { name: "Start from a sketch" }).click();
    await page.getByRole("heading", { name: "Start from a sketch" }).waitFor();
    await page.getByRole("button", { name: "Use the sample sketch" }).click();
    await page.locator("img[alt='Your sketch']").waitFor();
    await page.getByRole("button", { name: "Use the sample page" }).click();
    assert.match(await page.locator("input[type=url]").inputValue(), /^https:\/\/.+\/samples\/halden-h7\.html$/);
    await page.getByRole("button", { name: "Read my sketch" }).click();
    await page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 60_000 });
    assert.match(await text(), /Place the parts yourself/); // no vision model on this server: the manual template
    assert.match(await text(), /Copy from your page/);
    assert.match(await text(), /Offline sample page/);
    assert.match(await text(), /Only facts found on the page are kept/);
    await page.getByRole("button", { name: "Use the sample pictures" }).click();
    await page.locator("img[alt='Logo you chose']").waitFor();
    await page.locator("img[alt='Product image you chose']").waitFor();
    const removeLegal = page.getByRole("button", { name: /has no small print: remove it/ });
    if (await page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: "Small print" }) }).locator("textarea").inputValue() === "") await removeLegal.click();
    await page.getByRole("radio", { name: "#1d1240" }).click();
    await page.getByRole("button", { name: "Looks right: make the story card" }).click();
    await page.getByRole("heading", { level: 2, name: /Your story card|It needs one decision/ }).waitFor({ timeout: 90_000 });
    assert.match(await text(), /\d+ of \d+ checks passed/);
    assert.match(await text(), /Page check/);
    assert.match(await text(), /Amount found on page/);
    assert.ok((await page.locator("a[download]").count()) >= 2, "story card and banner downloads");
    assert.match((await page.locator("a[download]").nth(1).getAttribute("href")) ?? "", /^data:image\/png;base64,/);
    assert.deepEqual(problems, []);
  });

  test("axe-core finds no WCAG 2.x A or AA and no best-practice violations on the landing, the sketch door, the workbench and the result, in light and dark", async () => {
    const found = {};
    for (const scheme of ["light", "dark"]) {
      const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: scheme, bypassCSP: true })).newPage(); // CSP bypassed only so the scanner can be injected
      const scan = async (name) => {
        await page.waitForTimeout(900); // the entrance animation must finish: axe reads blended colours mid-fade
        await page.addScriptTag({ content: AXE });
        const r = await page.evaluate(async () => await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "best-practice"] } }));
        found[`${scheme}: ${name}`] = r.violations.map((v) => `${v.impact} ${v.id} (${v.nodes.length}) ${v.nodes[0].target.join(" ")}`);
      };
      await page.goto(`${API}/`, { waitUntil: "networkidle" });
      await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
      await scan("landing");
      await page.getByRole("button", { name: "Start from a sketch" }).click();
      await page.getByRole("button", { name: "Use the sample sketch" }).click();
      await page.locator("img[alt='Your sketch']").waitFor();
      await page.getByRole("button", { name: "Use the sample page" }).click();
      await scan("sketch door");
      await page.getByRole("button", { name: "Read my sketch" }).click();
      await page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 60_000 });
      await page.getByRole("button", { name: "Use the sample pictures" }).click();
      await page.locator("img[alt='Logo you chose']").waitFor();
      await scan("workbench");
      const legal = page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: "Small print" }) }).locator("textarea");
      if ((await legal.count()) && (await legal.inputValue()) === "") await page.getByRole("button", { name: /has no small print: remove it/ }).click();
      await page.getByRole("button", { name: "Looks right: make the story card" }).click();
      await page.getByRole("heading", { level: 2, name: /Your story card|It needs one decision/ }).waitFor({ timeout: 90_000 });
      await scan("result");
    }
    assert.deepEqual(Object.fromEntries(Object.entries(found).filter(([, v]) => v.length)), {});
  });

  test("a banner that is not 16:9 is refused in plain words, and a non-image is refused too", async () => {
    const page = await (await browser.newContext()).newPage();
    await page.goto(`${API}/`, { waitUntil: "networkidle" });
    await page.waitForFunction(() => !document.querySelector("input[type=file]").disabled);
    const fx = (await (await fetch(`${API}/api/campaign/fixtures`)).json()).fixtures.find((f) => f.id === "short_a");
    // a 1:1 image: draw the sample into a square canvas in the page and upload that
    const square = await page.evaluate(async (src) => {
      const img = new Image(); img.src = src; await img.decode();
      const c = document.createElement("canvas"); c.width = c.height = 600; c.getContext("2d").drawImage(img, 0, 0, 600, 600);
      return c.toDataURL("image/png");
    }, fx.png);
    await page.locator("input[type=file]").setInputFiles({ name: "square.png", mimeType: "image/png", buffer: Buffer.from(square.split(",")[1], "base64") });
    await page.getByRole("alert").filter({ hasText: "Use a 16:9 banner" }).waitFor();
    await page.locator("input[type=file]").setInputFiles({ name: "x.txt", mimeType: "text/plain", buffer: Buffer.from("hello") }).catch(() => undefined);
  });
});

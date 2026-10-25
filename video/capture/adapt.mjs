// Records "Adapt a banner" as one continuous, real session on the deployed app (same screencast method as campaign.mjs):
// drop a German banner -> Nemotron-3.5-Super-VL reads its parts (live) -> check the parts -> rebuilt layers -> the overflow
// question -> the answer -> the independent checks -> what it cannot do yet. Spends one live vision call (about $0.03).
//   node capture/adapt.mjs [--url https://…]   → capture/frames/*.png, capture/frames.json, capture/marks.json
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "../../node_modules/playwright/index.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const URL_ = arg("--url", "https://open-apprentice-md76de375q-uc.a.run.app").replace(/\/$/, "");
const FRAMES = path.join(HERE, "frames");
fs.rmSync(FRAMES, { recursive: true, force: true });
fs.mkdirSync(FRAMES, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
await ctx.addInitScript(() => {
  const make = () => {
    if (document.getElementById("rec-cursor") || !document.body) return;
    const c = document.createElement("div");
    c.id = "rec-cursor";
    c.style.cssText =
      "position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;z-index:2147483647;" +
      "pointer-events:none;border:3px solid #9be15d;background:rgba(155,225,93,.25);box-shadow:0 0 0 2px rgba(0,0,0,.35);" +
      "transition:transform .12s ease;";
    document.body.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => (c.style.transform = "scale(.7)"), true);
    addEventListener("mouseup", () => (c.style.transform = "scale(1)"), true);
  };
  document.addEventListener("DOMContentLoaded", make);
  setInterval(make, 500);
});
const page = await ctx.newPage();
const cdp = await ctx.newCDPSession(page);
const frames = [];
let t0 = null;
let firstFrameWall = null;
cdp.on("Page.screencastFrame", async (f) => {
  const ts = f.metadata.timestamp;
  if (t0 === null) {
    t0 = ts;
    firstFrameWall = Date.now();
  }
  const file = `${String(frames.length).padStart(6, "0")}.png`;
  fs.writeFileSync(path.join(FRAMES, file), Buffer.from(f.data, "base64"));
  frames.push({ file, t: +(ts - t0).toFixed(3) });
  await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
});
const wall0 = Date.now();
const marks = [];
const now = () => +((Date.now() - wall0) / 1000).toFixed(3);
const mark = async (name, selector) => {
  let box = null;
  if (selector) box = await page.locator(selector).first().boundingBox().catch(() => null);
  marks.push({ name, t: now(), box });
  console.log(`${now().toFixed(1)}s  ${name}`);
};
const moveTo = (x, y, steps = 28) => page.mouse.move(x, y, { steps });
const click = async (locator, pause = 350) => {
  await locator.scrollIntoViewIfNeeded();
  const b = await locator.boundingBox();
  await moveTo(b.x + b.width / 2, b.y + b.height / 2);
  await sleep(pause);
  await page.mouse.down();
  await sleep(90);
  await page.mouse.up();
};
const scrollTo = async (selector, offset = 90) => {
  await page.evaluate(([s, o]) => {
    const el = document.querySelector(s);
    if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - o - 72, behavior: "smooth" }); // 72: the sticky header
  }, [selector, offset]);
  await sleep(900);
};
const banner = (id) => page.getByRole("button", { name: new RegExp(`^${id}\\b`) });
/** Click and wait for the API call it triggers; returns its JSON. */
const clickFor = async (locator, re) => {
  const done = page.waitForResponse((r) => re.test(r.url()) && r.request().method() === "POST", { timeout: 300_000 });
  await click(locator);
  const r = await done;
  if (!r.ok()) throw new Error(`${r.url()} → HTTP ${r.status()}`);
  await page.waitForLoadState("networkidle");
  return r.json();
};
const RUNS = /\/api\/campaign\/workspaces\/[0-9a-f]+\/runs$/;

await cdp.send("Page.startScreencast", { format: "png", everyNthFrame: 1, maxWidth: 1920, maxHeight: 1080 });
try {
  const fx = (await (await page.request.get(`${URL_}/api/campaign/fixtures`)).json()).fixtures.find((f) => f.id === "de_long_a");
  const buffer = Buffer.from(fx.png.split(",")[1], "base64");
  await page.goto(`${URL_}/`, { waitUntil: "networkidle" });
  await moveTo(640, 360, 1);
  await sleep(1800);
  await mark("home");

  // drop a banner: the cursor goes to the button, then the German banner is loaded and Nemotron reads it
  const choose = page.locator("label.filebtn");
  const cb = await choose.boundingBox();
  await moveTo(cb.x + cb.width / 2, cb.y + cb.height / 2);
  await sleep(700);
  await mark("drop");
  const read = page.waitForResponse((r) => /\/uploads$/.test(r.url()) && r.request().method() === "POST", { timeout: 300_000 });
  await page.locator("input[type=file]").setInputFiles({ name: "headphones-de.png", mimeType: "image/png", buffer });
  const up = await (await read).json();
  console.log(`  read: origin ${up.origin}, model ${up.model}, problems ${JSON.stringify(up.problems)}, layers ${up.layers.map((l) => l.role).join(",")}`);
  if (up.origin !== "model") throw new Error(`the narration says Nemotron read the banner, but origin is ${up.origin}: ${up.note}`);
  await page.getByRole("heading", { name: "Check what Nemotron found" }).waitFor({ timeout: 60_000 });
  await sleep(1200);
  await scrollTo(".editor", 40);
  await mark("parts", ".editor");
  await sleep(4500);
  await mark("parts-read");

  // the model's logo and product boxes are tight: the owner drags each onto the whole picture
  const stage = await page.locator(".lstage").boundingBox();
  const k = stage.width / 1280;
  const fitBox = async (legend, cls, T) => {
    const row = page.locator("fieldset.lrow", { has: page.locator("legend", { hasText: legend }) });
    const num = async (label) => Number(await row.getByLabel(label, { exact: true }).inputValue());
    const box = page.locator(`.lbox.${cls}`);
    let bb = await box.boundingBox();
    await moveTo(bb.x + bb.width / 2, bb.y + bb.height / 2);
    await sleep(450);
    await page.mouse.down();
    await moveTo(bb.x + bb.width / 2 + (T.x - (await num("Left"))) * k, bb.y + bb.height / 2 + (T.y - (await num("Top"))) * k, 16);
    await page.mouse.up();
    await sleep(400);
    const hb = await box.locator(".lhandle").boundingBox();
    await moveTo(hb.x + hb.width / 2, hb.y + hb.height / 2);
    await sleep(350);
    await page.mouse.down();
    await moveTo(hb.x + hb.width / 2 + (T.w - (await num("Width"))) * k, hb.y + hb.height / 2 + (T.h - (await num("Height"))) * k, 16);
    await page.mouse.up();
    await sleep(700);
  };
  await mark("fix-start");
  await fitBox("Logo", "r-brand_mark", { x: 64, y: 50, w: 196, h: 44 }); // the wordmark on the 1280 x 720 banner
  await fitBox("Product image", "r-product_image", { x: 128, y: 205, w: 400, h: 375 }); // the headphones
  await sleep(1200);
  await mark("fix-done");

  // and a box by keyboard, the way an owner without a mouse would
  await page.locator(".lbox.r-headline").focus();
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("ArrowRight");
    await sleep(350);
  }
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press("ArrowLeft");
    await sleep(350);
  }
  await mark("keys");
  await sleep(1500);

  // rebuild, adapt, and the overflow question
  const confirmBtn = page.getByRole("button", { name: "Looks right: make the story card" });
  await confirmBtn.scrollIntoViewIfNeeded();
  await mark("confirm");
  const runs = page.waitForResponse((r) => /\/runs$/.test(r.url()) && r.request().method() === "POST", { timeout: 300_000 });
  await click(confirmBtn);
  const run = await (await runs).json();
  if (run.status !== "question") throw new Error(`the narration says it asks, but the run is ${run.status}`);
  await page.getByLabel("Question").waitFor();
  await sleep(1000);
  await scrollTo(".trio", 60);
  await mark("rebuilt", ".trio");
  await sleep(3500);
  await scrollTo(".question", 20);
  await mark("question", ".question");
  await sleep(6500);
  await mark("question-read");
  const answered = page.waitForResponse((r) => /\/answer$/.test(r.url()) && r.request().method() === "POST", { timeout: 300_000 });
  await click(page.getByRole("button", { name: /Split across two cards/ }).first());
  const a = await (await answered).json();
  if (a.status !== "applied") throw new Error(`answer: ${a.status}`);
  await page.getByRole("heading", { level: 2, name: "Your story card" }).waitFor({ timeout: 60_000 });
  await sleep(800);
  await scrollTo(".trio", 60);
  await mark("answered", ".trio");
  await sleep(3500);

  // the independent checks, and the download
  await page.getByText("See every check").click();
  await sleep(600);
  await scrollTo(".table-wrap", 120);
  await mark("checks");
  await sleep(5000);
  await mark("checks-read");

  // what it cannot do yet
  await page.getByText("See every check").click(); // fold the table away so the limits panel is the thing on screen
  await sleep(500);
  await page.getByText("What it cannot do yet").click();
  await sleep(500);
  await scrollTo("details.limits", 40);
  await mark("limits", "details.limits");
  await sleep(7000);
  await mark("limits-read");
} finally {
  await cdp.send("Page.stopScreencast").catch(() => {});
  await sleep(300);
  fs.writeFileSync(path.join(HERE, "frames.json"), JSON.stringify(frames));
  fs.writeFileSync(path.join(HERE, "marks.json"), JSON.stringify({ url: URL_, live: true, scale: 1.5, marks, frameOffset: firstFrameWall ? (firstFrameWall - wall0) / 1000 : 0 }, null, 1));
  console.log(`${frames.length} frames, ${marks.length} marks`);
  await browser.close();
}

// Records the Campaign lane as one continuous, real session on the deployed app (same screencast method as capture.mjs):
// learn the banner -> story card layout, reuse it, the overflow question, the saved preference, Nemotron's live role
// proposal, and the same rule on Fabric. Then saves real before/after renders for the opening montage.
//   node capture/campaign.mjs [--url https://…]   → capture/frames/*.png, capture/frames.json, capture/marks.json,
//                                                  public/cmontage/*.png
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
    if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - o, behavior: "smooth" });
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
  await page.goto(`${URL_}/#campaign`, { waitUntil: "networkidle" });
  await moveTo(600, 330, 1);
  await sleep(1500);
  await mark("home");

  // teach: one banner -> story card example
  await mark("learn-click");
  await clickFor(page.getByRole("button", { name: "Learn this layout" }), /\/api\/campaign\/workspaces$/);
  await scrollTo("#c-teach", 20);
  await mark("learned", "section[aria-labelledby=c-teach] .svgpair");
  await sleep(4000);
  await mark("learned-read");

  // the example fits two readings of the product image: it renders both on a test banner and asks once
  await scrollTo("[aria-label='Teaching question']", 20);
  await mark("reading", "[aria-label='Teaching question']");
  await sleep(6000);
  await mark("reading-read");
  await clickFor(page.getByRole("button", { name: "Same frame every time" }), /\/reading$/);
  await scrollTo("[aria-label='Learned rule']", 20);
  await mark("rule", "[aria-label='Learned rule']");
  await sleep(4000);
  await mark("rule-read");

  // reuse on a new banner (Konva), the verifier's checks
  await scrollTo("#c-run", 20);
  await mark("reuse-start");
  const r1 = await clickFor(banner("short_b"), RUNS);
  if (r1.status !== "ready") throw new Error(`short_b: ${r1.status}`);
  await scrollTo(".runout", 20);
  await mark("reuse-done", ".runout");
  await sleep(3500);
  await mark("reuse-read");

  // the overflow question on a long German headline
  await scrollTo("#c-run", 20);
  await mark("ask-start");
  const r2 = await clickFor(banner("de_long_a"), RUNS);
  if (r2.status !== "question") throw new Error(`de_long_a: ${r2.status}`);
  await scrollTo(".question", 20);
  await mark("question", ".question");
  await sleep(5000);
  await mark("question-read");
  const a = await clickFor(page.getByRole("button", { name: "Split across two cards" }), /\/answer$/);
  if (a.status !== "applied") throw new Error(`answer: ${a.status}`);
  await scrollTo(".runout", 20);
  await mark("answered", ".runout");
  await sleep(2500);
  await scrollTo("#c-run", 20);
  const r3 = await clickFor(banner("de_long_b"), RUNS);
  if (r3.status !== "applied" || r3.previews.length) throw new Error(`de_long_b did not reuse the preference: ${r3.status}`);
  await scrollTo(".runout", 20);
  await mark("pref-reused", ".runout");
  await sleep(3000);
  await scrollTo("#c-prefs", 20);
  await mark("prefs", "#c-prefs");
  await sleep(2500);
  await mark("prefs-read");

  // an untagged banner: Nemotron proposes roles live, a checker validates, the owner confirms
  await scrollTo("#c-run", 20);
  await mark("roles-start");
  const roles = await clickFor(banner("untagged_short_b"), /\/roles$/);
  console.log(`  roles: origin ${roles.origin}, model ${roles.model}, problems ${JSON.stringify(roles.problems)}`);
  if (roles.origin !== "model") throw new Error(`the narration says Nemotron proposed the roles, but origin is ${roles.origin}`);
  await scrollTo(".runout", 20);
  await mark("roles", ".runout");
  await sleep(4500);
  const r4 = await clickFor(page.getByRole("button", { name: "Confirm roles and run" }), RUNS);
  if (r4.status !== "ready") throw new Error(`untagged_short_b: ${r4.status}`);
  await scrollTo(".runout", 20);
  await mark("roles-run", ".runout");
  await sleep(2500);

  // the same learned rule in a second engine
  await scrollTo("#c-run", 20);
  await mark("fabric-start");
  await click(page.getByLabel("Fabric"));
  await sleep(700);
  const r5 = await clickFor(banner("short_b"), RUNS);
  if (r5.status !== "ready" || r5.backend !== "fabric") throw new Error(`fabric short_b: ${r5.status} ${r5.backend}`);
  await scrollTo(".runout", 20);
  await mark("fabric-done", ".runout");
  await sleep(4000);
  await mark("fabric-read");

  // the Try-it lane's question shows its work: candidate rules, Z3's pair searches, how the chosen input splits them
  await page.goto(`${URL_}/#home`, { waitUntil: "networkidle" });
  await click(page.getByText("Try it live", { exact: true }).first());
  await page.waitForLoadState("networkidle");
  await click(page.getByLabel("Reference learner (free, no model)"));
  await mark("tryit-start");
  await clickFor(page.getByRole("button", { name: "Start teaching" }), /\/api\/teach$/);
  await page.getByLabel("Show the work").waitFor({ timeout: 60_000 });
  await scrollTo("[aria-label='Show the work']", 120);
  await mark("tryit-work", "[aria-label='Show the work']");
  await sleep(7000);
  await mark("tryit-read");
  await cdp.send("Page.stopScreencast").catch(() => {});

  // real before/after renders for the opening montage, through the same public API (Konva)
  const OUT = path.join(HERE, "..", "public", "cmontage");
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  const api = async (p, data) => {
    for (let i = 0; ; i++) {
      try {
        const r = await page.request.post(`${URL_}/api/campaign${p}`, { data, timeout: 120_000 });
        if (!r.ok()) throw new Error(`${p} → HTTP ${r.status()}`);
        return await r.json();
      } catch (e) {
        if (i === 2) throw e; // a flaky connection, not the server: try twice more (runs are side-effect free here)
        console.log(`  retry ${p}: ${e.message.split("\n")[0]}`);
      }
    }
  };
  const fx = (await (await page.request.get(`${URL_}/api/campaign/fixtures`)).json()).fixtures;
  const ws = await api("/workspaces", { reading: "fixed" });
  const save = (name, dataUrl) => fs.writeFileSync(path.join(OUT, name), Buffer.from(dataUrl.split(",")[1], "base64"));
  const tiles = [];
  for (const [id, choice] of [["short_a"], ["fr_long", "builtin_shrink_hero"], ["short_b"], ["de_long_a", "builtin_split_two_cards"]]) {
    let r = await api(`/workspaces/${ws.workspace_id}/runs`, { fixture_id: id, backend: "konva" });
    if (r.status === "question") r = await api(`/workspaces/${ws.workspace_id}/runs/${r.run_id}/answer`, { choice });
    if (!r.result?.png) throw new Error(`montage ${id}: ${r.status}`);
    save(`${id}-before.png`, fx.find((f) => f.id === id).png);
    save(`${id}-after.png`, r.result.png);
    tiles.push({ id, locale: fx.find((f) => f.id === id).locale });
  }
  fs.writeFileSync(path.join(OUT, "index.json"), JSON.stringify(tiles));
  console.log(`${tiles.length} montage pairs`);
} finally {
  await cdp.send("Page.stopScreencast").catch(() => {});
  await sleep(300);
  fs.writeFileSync(path.join(HERE, "frames.json"), JSON.stringify(frames));
  fs.writeFileSync(path.join(HERE, "marks.json"), JSON.stringify({ url: URL_, live: true, scale: 1.5, marks, frameOffset: firstFrameWall ? (firstFrameWall - wall0) / 1000 : 0 }, null, 1));
  console.log(`${frames.length} frames, ${marks.length} marks`);
  await browser.close();
}

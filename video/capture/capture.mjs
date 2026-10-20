// Records the demo as one continuous, real session on the deployed app: Chrome's screencast (lossless PNG frames with their
// own timestamps) at 1920x1080, a visible cursor, real mouse drags, and timestamped marks that the Remotion edit cuts on.
// Nothing is staged: every screen is the product responding to these clicks; the live part calls Nemotron for real.
//   node capture/capture.mjs [--url https://…] [--no-live]      → capture/frames/*.png, capture/frames.json, capture/marks.json
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "../../node_modules/playwright/index.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const URL_ = arg("--url", "https://open-apprentice-md76de375q-uc.a.run.app").replace(/\/$/, "");
const LIVE = !process.argv.includes("--no-live");
const FRAMES = path.join(HERE, "frames");
fs.rmSync(FRAMES, { recursive: true, force: true });
fs.mkdirSync(FRAMES, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const n = (s) => (String(s).includes("/") ? Number(s.split("/")[0]) / Number(s.split("/")[1]) : Number(s));
const TERMINAL = ["committed", "failed", "cancelled", "activated", "activation_rejected", "override", "dismissed"];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1.5 });
await ctx.addInitScript(() => {
  // a visible cursor for the recording (headless Chrome draws none)
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
const until = async (fn, what, ms = 300_000) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn().catch(() => false);
    if (v) return v;
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await sleep(250);
  }
};
let mouse = { x: 640, y: 360 };
const moveTo = async (x, y, steps = 28) => {
  await page.mouse.move(x, y, { steps });
  mouse = { x, y };
};
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
  await page.evaluate(
    ([s, o]) => {
      const el = document.querySelector(s);
      if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - o, behavior: "smooth" });
    },
    [selector, offset],
  );
  await sleep(900);
};
const state = () => page.locator("[data-state]").getAttribute("data-state");

async function docInfo(name) {
  const ids = JSON.parse(await page.evaluate(() => localStorage.getItem("oa.v2.docs") ?? "[]"));
  for (const id of ids) {
    const d = await (await page.request.get(`${URL_}/api/v2/documents/${id}`)).json();
    if (d.name === name) return d;
  }
  throw new Error(`document ${name} not found`);
}

/** Which alternative of the open question places every note left-aligned, 8 below its box (within 0.5)? */
async function intendedChoice() {
  const sid = page.url().match(/s\/([0-9a-f]+)/)[1];
  const st = await (await page.request.get(`${URL_}/api/v2/sessions/${sid}`)).json();
  const req = st.outstanding?.request;
  if (!req || req.type !== "ChooseOutput") return null;
  const [docId, pageId] = req.scene_id.split(":");
  const d = await (await page.request.get(`${URL_}/api/v2/documents/${docId}`)).json();
  const p = d.pages.find((x) => x.page_id === pageId);
  const sc = await (await page.request.get(`${URL_}/api/v2/documents/${docId}/pages/${pageId}/scene?mapping_hash=${p.mapping_hash}`)).json();
  const objs = Object.fromEntries(sc.objects.map((o) => [o.id, o]));
  const want = Object.fromEntries(sc.objects.filter((o) => o.kind === "label" && sc.movable.includes(o.id))
    .map((o) => [o.id, [n(objs[o.attached].x), n(objs[o.attached].y) + n(objs[o.attached].h) + 8]]));
  const ok = (out) => Object.entries(want).every(([k, [x, y]]) => out[k] && Math.abs(n(out[k][0]) - x) <= 0.5 && Math.abs(n(out[k][1]) - y) <= 0.5);
  return req.alternatives.find(([, out]) => ok(out))?.[0] ?? null;
}

async function answerAll(waitMs) {
  for (let i = 0; i < 10; i++) {
    const s = await until(async () => {
      const st = await state();
      if (st && TERMINAL.includes(st)) return st;
      return (await page.locator("section.question").count()) ? "question" : null;
    }, "a question or the end", waitMs);
    if (s !== "question") return s;
    await scrollTo("section.question", 120);
    const before = await page.locator("section.question").getAttribute("data-request-id");
    if (await page.locator("fieldset[data-item]").count()) {
      await mark("preview");
      await sleep(2500);
      for (const f of await page.locator("fieldset[data-item]").all()) {
        const a = f.getByLabel("Approve");
        if (await a.isEnabled()) await click(a, 200);
        else await click(f.getByLabel("Reject"), 200);
      }
      await sleep(600);
      await click(page.getByRole("button", { name: "Submit verdicts" }));
    } else {
      await mark("question", "section.question");
      await sleep(4500); // time to read the alternatives
      // the person's intent: every note left-aligned, 8 below its box. Pick the option whose rendered outcome matches it on
      // the diagram shown (the same test the product check scores with), never by the wording of the rule.
      const opts = page.locator("label.v2-option.choice");
      const want = await intendedChoice();
      let pick = 0;
      for (let k = 0; k < (await opts.count()); k++) {
        if ((await opts.nth(k).locator('input[name="alt"]').getAttribute("value")) === want) pick = k;
      }
      console.log(`  question: picking ${want ?? "(no match: first)"}`);
      await click(opts.nth(pick).locator('input[name="alt"]'));
      await sleep(900);
      await click(page.getByRole("button", { name: "Submit answer" }));
    }
    await mark("answered");
    await until(async () => {
      const st = await state();
      if (st && TERMINAL.includes(st)) return true;
      return (await page.locator("section.question").getAttribute("data-request-id").catch(() => null)) !== before;
    }, "the next step", waitMs);
  }
  return "too many questions";
}

await cdp.send("Page.startScreencast", { format: "png", everyNthFrame: 1, maxWidth: 1920, maxHeight: 1080 });
try {
  await page.goto(`${URL_}/#apprentice`, { waitUntil: "networkidle" });
  await moveTo(600, 330, 1);
  await sleep(1500);
  await mark("home");

  // 1 · bring diagrams: two hero samples, then the whole library
  await click(page.getByRole("button", { name: "Try a sample: Online order journey" }));
  await until(async () => (await page.getByRole("button", { name: "Confirm mapping" }).count()) === 1, "first sample");
  await click(page.getByRole("button", { name: "Try a sample: Hiring process" }));
  await until(async () => (await page.getByRole("button", { name: "Confirm mapping" }).count()) === 2, "second sample");
  await mark("samples");
  await sleep(1200);
  await page.mouse.wheel(0, 520);
  await sleep(1800);
  await mark("mapping-table", "table.mapping");
  await sleep(2500);
  for (let i = 0; i < 2; i++) {
    await click(page.getByRole("button", { name: "Confirm mapping" }).first());
    await until(async () => (await page.getByText("Mapping confirmed ✓").count()) === i + 1, `confirmation ${i + 1}`);
  }
  await mark("mapped");
  await scrollTo("#h-teach", 40);

  // 2 · show it once: real drags, each note left-aligned, 8 below its box
  const d = await docInfo("order-journey.drawio");
  const pg = d.pages.find((p) => p.status === "ok");
  const sc = await (await page.request.get(`${URL_}/api/v2/documents/${d.doc_id}/pages/${pg.page_id}/scene?mapping_hash=${pg.mapping_hash}`)).json();
  const objs = Object.fromEntries(sc.objects.map((o) => [o.id, o]));
  await page.getByLabel("Document to edit").selectOption({ label: d.name });
  await page.waitForSelector("button[data-label]");
  await scrollTo(".docview-stage", 140);
  await mark("teach-start", ".docview-stage");
  const geo = await page.evaluate(() => {
    const img = document.querySelector(".docview-stage img");
    return { scale: img.clientWidth / img.naturalWidth };
  });
  for (const [lid, m] of Object.entries(pg.mapping.labels)) {
    const a = objs[m.node_id], o = objs[lid];
    const btn = page.getByRole("button", { name: `label ${lid}`, exact: true });
    await btn.scrollIntoViewIfNeeded();
    const b = await btn.boundingBox();
    // offline dry runs use the centred rule (the offline learner's grammar has no left-aligned rule)
    const tx = LIVE ? n(a.x) : n(a.x) + (n(a.w) - n(o.w)) / 2;
    const dx = (tx - n(o.x)) * geo.scale, dy = (n(a.y) + n(a.h) + 8 - n(o.y)) * geo.scale;
    const sx = b.x + 6, sy = b.y + b.height / 2;
    await moveTo(sx, sy, 18);
    await page.mouse.down();
    await moveTo(sx + dx, sy + dy, 22);
    await page.mouse.up();
    await sleep(250);
  }
  const confirm = page.getByRole("button", { name: "This whole document is right" });
  await until(async () => confirm.isEnabled(), "the draft render");
  await mark("taught", ".docview-stage");
  await sleep(1500);

  // 3 · watch it think (live Nemotron through Nebius Token Factory)
  if (LIVE) {
    await click(page.getByLabel("Use the live model"));
    await sleep(500);
  }
  await click(confirm);
  await until(async () => /#apprentice\/s\/[0-9a-f]+/.test(page.url()), "the session");
  await scrollTo("#h-session", 30);
  await mark("session-start", ".notebook");
  const end = await answerAll(600_000);
  await mark(`session-${end}`, ".notebook");
  await scrollTo("#h-session", 30);
  await sleep(4000);
  if (!["committed", "activated"].includes(end)) throw new Error(`the session ended ${end}`);

  // 4 · teach once, fix 100: load the library, confirm all, apply everywhere
  await scrollTo("#h-import", 30);
  await click(page.getByRole("button", { name: "Load the 100-diagram library" }));
  await mark("library-loading");
  await until(async () => {
    const m = (await page.locator("text=/diagrams imported/").innerText()).match(/(\d+) of (\d+)/);
    return m && m[1] === m[2];
  }, "library import", 600_000);
  await until(async () => (await page.getByRole("button", { name: /Confirm all \d+ suggested/ }).count()) === 1 && (await page.locator(".rendering-count").count()) === 0 && (await page.locator("text=Rendering in the locked engine").count()) === 0, "renders", 600_000);
  await mark("library-loaded", ".cards");
  await click(page.getByRole("button", { name: /Confirm all \d+ suggested/ }));
  await until(async () => !(await page.getByRole("button", { name: /Confirm all \d+ suggested/ }).count()), "confirm all", 600_000);
  await mark("library-confirmed");
  await scrollTo("#h-reuse", 30);
  await until(async () => (await page.getByRole("button", { name: /Select all/ }).count()) === 1, "the reuse step", 120_000);
  await click(page.getByRole("button", { name: /Select all/ }));
  await sleep(800);
  await click(page.getByRole("button", { name: "Apply" }));
  await mark("apply", ".tally");
  await sleep(1500);
  await scrollTo(".tally", 60);
  await until(async () => {
    const m = (await page.locator(".tally").innerText()).match(/(\d+) of (\d+) checked/);
    return m && m[1] === m[2] && !(await page.getByText(/Run running/).count());
  }, "the wall", 900_000);
  await mark("wall-done", ".tally");
  const tally = (await page.locator(".tally").innerText()).match(/(\d+) published/);
  marks.push({ name: `published-${tally ? tally[1] : 0}`, t: now(), box: null });
  const tiles = await page.locator("article.result.published").evaluateAll((els) =>
    els.slice(0, 40).map((e) => ({ name: e.getAttribute("data-result"), after: e.querySelector(".tile-img img")?.getAttribute("src") })));

  await sleep(2500);
  await page.mouse.wheel(0, 700);
  await sleep(2500);
  await page.mouse.wheel(0, 900);
  await sleep(2000);

  // before / after
  const tile = page.locator(".tile-img:not([disabled])").nth(4);
  await click(tile);
  await page.waitForSelector(".beforeafter img");
  await sleep(1200);
  await mark("compare", ".slider");
  const r = await page.locator(".range input").boundingBox();
  await moveTo(r.x + r.width * 0.5, r.y + r.height / 2);
  await page.mouse.down();
  for (const f of [0.1, 0.9, 0.3, 0.75]) {
    await moveTo(r.x + r.width * f, r.y + r.height / 2, 40);
    await sleep(500);
  }
  await page.mouse.up();
  await sleep(1200);
  await click(page.getByRole("button", { name: "Close" }));
  await mark("compare-closed");
  await sleep(800);

  // the finale: a 217-object platform map, fixed with the same skill in one click
  await scrollTo("#h-import", 30);
  await click(page.getByRole("button", { name: /Try a sample: The big one/ }));
  await mark("finale-start");
  await until(async () => {
    const d = await docInfo("ai-platform-map.drawio").catch(() => null);
    return d && d.render === "done";
  }, "the big map", 300_000);
  await sleep(1500);
  const big = await docInfo("ai-platform-map.drawio");
  await page.request.post(`${URL_}/api/v2/documents/${big.doc_id}/mapping`, { data: { page_id: big.pages[0].page_id, labels: {}, confirm: true } });
  await page.reload({ waitUntil: "networkidle" });
  await scrollTo("#h-reuse", 30);
  await until(async () => (await page.getByRole("button", { name: /Select all/ }).count()) === 1, "the reuse step", 120_000);
  if (await page.getByRole("button", { name: "Select none" }).count()) await click(page.getByRole("button", { name: "Select none" }));
  await click(page.locator("label.pick", { hasText: "ai-platform-map.drawio" }).locator("input"));
  await sleep(600);
  await click(page.getByRole("button", { name: "Apply" }));
  await mark("finale-apply");
  await until(async () => (await page.locator('article.result[data-result="ai-platform-map.drawio"] h3').innerText().catch(() => "")).match(/Published|Blocked|Failed|Unchanged/), "the big result", 300_000);
  await scrollTo('article.result[data-result="ai-platform-map.drawio"]', 120);
  await sleep(2500);
  await mark("finale-result", 'article.result[data-result="ai-platform-map.drawio"]');
  const bigTile = page.locator('article.result[data-result="ai-platform-map.drawio"] .tile-img');
  if (await bigTile.isEnabled()) {
    await click(bigTile);
    await page.waitForSelector(".beforeafter img");
    await sleep(2500);
    await mark("finale-compare", ".slider");
    const r2 = await page.locator(".range input").boundingBox();
    await moveTo(r2.x + r2.width * 0.5, r2.y + r2.height / 2);
    await page.mouse.down();
    for (const f of [0.02, 0.98, 0.5]) {
      await moveTo(r2.x + r2.width * f, r2.y + r2.height / 2, 70);
      await sleep(700);
    }
    await page.mouse.up();
    await sleep(1500);
    await mark("finale-compare-end");
    await click(page.getByRole("button", { name: "Close" }));
  }
  await sleep(800);

  // 5 · another world: the same apprentice approach on UI components (earlier prototype, reference learner, no model)
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
  await sleep(900);
  await click(page.getByRole("tab", { name: /Earlier prototype/ }));
  await sleep(1500);
  await click(page.getByRole("tab", { name: "Try it live" }));
  await sleep(1500);
  await mark("prototype");
  const story = page.getByRole("button", { name: "Watch the story with the free reference learner" });
  if (await story.count()) {
    await click(story);
    await sleep(22_000);
  }
  await mark("prototype-done");
  await sleep(1500);
  await cdp.send("Page.stopScreencast").catch(() => {});
  // real before/after renders of published documents, for the opening montage (after the recording; slow renders are skipped)
  const MONT = path.join(HERE, "..", "public", "montage");
  fs.rmSync(MONT, { recursive: true, force: true });
  fs.mkdirSync(MONT, { recursive: true });
  const montage = [];
  for (const [i, t] of tiles.entries()) {
    try {
      const q = new URL(t.after, URL_).searchParams;
      const before = `${URL_}/api/v2/documents/${q.get("doc_id")}/pages/${q.get("page_id")}/preview.png`;
      const b = await page.request.get(before, { timeout: 120_000 });
      const a = await page.request.get(new URL(t.after, URL_).href, { timeout: 120_000 });
      if (!b.ok() || !a.ok()) continue;
      fs.writeFileSync(path.join(MONT, `${i}-before.png`), await b.body());
      fs.writeFileSync(path.join(MONT, `${i}-after.png`), await a.body());
      montage.push({ i, name: t.name });
    } catch (e) {
      console.log(`  montage ${i}: skipped (${e.message.split("\n")[0]})`);
    }
  }
  fs.writeFileSync(path.join(MONT, "index.json"), JSON.stringify(montage));
  console.log(`${montage.length} montage pairs`);

} finally {
  await cdp.send("Page.stopScreencast").catch(() => {});
  await sleep(300);
  fs.writeFileSync(path.join(HERE, "frames.json"), JSON.stringify(frames));
  fs.writeFileSync(path.join(HERE, "marks.json"), JSON.stringify({ url: URL_, live: LIVE, scale: 1.5, marks, frameOffset: firstFrameWall ? (firstFrameWall - wall0) / 1000 : 0 }, null, 1));
  console.log(`${frames.length} frames, ${marks.length} marks`);
  await browser.close();
}

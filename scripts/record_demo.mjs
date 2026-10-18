// Records the narrated demo: drives the deployed app in real Chromium (Playwright video), speaks each beat with macOS `say`,
// and writes beats.json (start time + audio file per beat) for scripts/mux_demo.sh to lay the narration over the video.
//   OA_URL=https://… node scripts/record_demo.mjs [--live]      (--live runs one real Nemotron session; costs ~$0.1-0.3)
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const URL_ = (process.env.OA_URL ?? "https://open-apprentice-md76de375q-uc.a.run.app").replace(/\/$/, "");
const LIVE = process.argv.includes("--live");
const OUT = process.env.OA_OUT ?? path.join(ROOT, "results/demo_video");
const VOICE = process.env.OA_VOICE ?? "Daniel";
const RATE = process.env.OA_RATE ?? "165";
fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(path.join(OUT, "audio"), { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const until = async (fn, what, ms = 90_000) => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await sleep(250);
  }
};
const TERMINAL = ["committed", "failed", "cancelled", "activated", "activation_rejected", "override", "dismissed"];
const state = (page) => page.locator("[data-state]").getAttribute("data-state");
const n = (s) => (String(s).includes("/") ? Number(s.split("/")[0]) / Number(s.split("/")[1]) : Number(s));

const SLIDE = `<body style="margin:0;background:#101418;color:#eee;font:20px system-ui,sans-serif;padding:70px 90px">
<h1 style="margin:0 0 6px">Frozen battery: 36 held-out episodes x 3 repeats, live Nemotron</h1>
<p style="color:#9ab;margin:0 0 24px">Scored by an independent oracle in an isolated process. Synthetic label-placement family; one model; small n.</p>
<table style="border-collapse:collapse;width:100%">
<tr style="color:#9ab;text-align:left"><th style="padding:8px">Question</th><th>Apprentice</th><th>Same model, free agent</th></tr>
<tr><td style="padding:8px">Learns the rule</td><td>22/48</td><td><b>28/48</b></td></tr>
<tr><td style="padding:8px">Corrects a wrong result</td><td>18/36</td><td><b>22/36</b></td></tr>
<tr><td style="padding:8px">Surfaces conflicting demonstrations</td><td><b>12/12</b></td><td>6/12</td></tr>
<tr><td style="padding:8px">Refuses inconsistent or unsupported</td><td><b>18/24</b></td><td>9/24</td></tr>
<tr><td style="padding:8px">Cost per run</td><td><b>$0.17</b></td><td>$0.26</td></tr></table>
<p style="margin-top:28px;color:#fc6">The hypothesis that asking beats acting freely is not supported by this run. We publish the loss.</p></body>`;

const beats = [];
let T0 = 0;
let page;
let k = 0;

function speak(text) {
  const file = path.join(OUT, "audio", `b${String(k++).padStart(2, "0")}.aiff`);
  execFileSync("say", ["-v", VOICE, "-r", RATE, "-o", file, text]);
  const info = execFileSync("afinfo", [file]).toString();
  const secs = Number(/estimated duration: ([\d.]+)/.exec(info)[1]);
  return { file, secs };
}

async function caption(text) {
  await page.evaluate((t) => {
    let el = document.getElementById("oa-demo-caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "oa-demo-caption";
      el.style.cssText =
        "position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:99999;max-width:1500px;padding:8px 16px;border-radius:8px;" +
        "background:rgba(10,10,10,.86);color:#fff;font:600 26px/1.35 system-ui,sans-serif;text-align:center;pointer-events:none";
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
}

/** Narrate `text` (caption = `cap`) while `action` runs; the beat lasts until both the voice and the action are done. */
async function beat(text, cap, action) {
  const { file, secs } = speak(text);
  const start = (Date.now() - T0) / 1000;
  beats.push({ start, file: path.basename(file), secs, text });
  await caption(cap ?? text);
  const t = Date.now();
  if (action) await action();
  const left = secs * 1000 + 600 - (Date.now() - t);
  if (left > 0) await sleep(left);
}

async function slowType(loc, value) {
  await loc.click();
  await loc.fill(String(value));
}

async function placeBelow(pageInfo, objs) {
  for (const [lid, m] of Object.entries(pageInfo.mapping.labels)) {
    const a = objs[m.node_id], o = objs[lid];
    await page.getByRole("button", { name: `label ${lid}`, exact: true }).click();
    await slowType(page.getByLabel(`x of ${lid}`), n(a.x) + (n(a.w) - n(o.w)) / 2);
    await slowType(page.getByLabel(`y of ${lid}`), n(a.y) + n(a.h) + 8);
    await sleep(500);
  }
}

async function docInfo(name) {
  const ids = JSON.parse(await page.evaluate(() => localStorage.getItem("oa.v2.docs") ?? "[]"));
  for (const id of ids) {
    const d = await (await page.request.get(`${URL_}/api/v2/documents/${id}`)).json();
    if (d.name === name) return d;
  }
  throw new Error(`document ${name} not found`);
}

async function answerOne() {
  const before = await page.locator("section.question").getAttribute("data-request-id");
  if (await page.locator("fieldset[data-item]").count()) {
    for (const fs_ of await page.locator("fieldset[data-item]").all()) {
      const approve = fs_.getByLabel("Approve");
      if (await approve.isEnabled()) await approve.check();
      else await fs_.getByLabel("Reject").check();
      await sleep(400);
    }
    await page.getByRole("button", { name: "Submit verdicts" }).click();
  } else {
    await page.locator('input[name="alt"], input[name="interp"]').first().check();
    await sleep(800);
    await page.getByRole("button", { name: "Submit answer" }).click();
  }
  await until(async () => {
    const st = await state(page).catch(() => null);
    if (st && TERMINAL.includes(st)) return true;
    return (await page.locator("section.question").getAttribute("data-request-id").catch(() => null)) !== before;
  }, "the next step", 300_000);
}

/** Wait for a question or the end; narrate the first question, answer every question until done. Returns the end state. */
async function runSession(questionNarration, previewNarration, waitMs) {
  let narratedQ = false;
  let narratedP = false;
  for (let i = 0; i < 12; i++) {
    const s = await until(async () => {
      const st = await state(page).catch(() => null);
      if (st && TERMINAL.includes(st)) return st;
      return (await page.locator("section.question").count()) ? "question" : null;
    }, "a question or the end", waitMs);
    if (s !== "question") return s;
    const preview = (await page.locator("fieldset[data-item]").count()) > 0;
    if (preview && !narratedP) {
      narratedP = true;
      await page.locator("section.question").scrollIntoViewIfNeeded();
      await beat(previewNarration, "Preview on other documents before anything is applied", answerOne);
    } else if (!preview && !narratedQ) {
      narratedQ = true;
      await page.locator("section.question").scrollIntoViewIfNeeded();
      await beat(questionNarration, "It asks which outcome you meant", answerOne);
    } else {
      await answerOne();
    }
  }
  return "too many questions";
}

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: path.join(OUT, "video"), size: { width: 1280, height: 720 } },
});
page = await ctx.newPage();
T0 = Date.now();
let ended = "not finished";
try {
  await page.goto(`${URL_}/#apprentice`, { waitUntil: "networkidle" });
  await beat(
    "Layout rules are easy to show and hard to specify. Open Apprentice learns one from a demonstration on a real draw dot io file, asks when your example is ambiguous, and edits files only through checked patches.",
    "Open Apprentice: teach a layout rule by demonstration",
  );

  await beat("I start from sample diagrams. It first asks which node each label describes, so nothing is guessed silently.", "Import, then confirm the label-to-node mapping", async () => {
    await page.getByRole("button", { name: "Try a sample: Training workflow" }).click();
    await until(async () => (await page.getByRole("button", { name: "Confirm mapping" }).count()) === 1, "first sample");
    await page.getByRole("button", { name: "Try a sample: Checkout service" }).click();
    await until(async () => (await page.getByRole("button", { name: "Confirm mapping" }).count()) === 2, "second sample");
    for (let i = 0; i < 2; i++) {
      await page.getByRole("button", { name: "Confirm mapping" }).first().click();
      await until(async () => (await page.getByText("Mapping confirmed ✓").count()) === i + 1, `confirmation ${i + 1}`);
      await sleep(600);
    }
    await page.evaluate(() => window.scrollTo(0, 0));
  });

  const d = await docInfo("training-workflow.drawio");
  const p1 = d.pages.find((p) => p.status === "ok");
  const scene = await (await page.request.get(`${URL_}/api/v2/documents/${d.doc_id}/pages/${p1.page_id}/scene?mapping_hash=${p1.mapping_hash}`)).json();
  const objs = Object.fromEntries(scene.objects.map((o) => [o.id, o]));

  await beat(
    "That is the whole demonstration: on one document I place each label below its node. The engine re-renders every change with real draw dot io.",
    "Demonstrate: place the labels below their boxes",
    async () => {
      await page.getByLabel("Document to edit").selectOption({ label: "training-workflow.drawio" });
      await page.waitForSelector("button[data-label]");
      await page.locator(".docview-stage").first().scrollIntoViewIfNeeded();
      await placeBelow(p1, objs);
      await until(async () => page.getByRole("button", { name: "This whole document is right" }).isEnabled(), "draft render");
    },
  );

  if (LIVE) await page.getByLabel("Use the live model").uncheck().catch(() => {});
  await beat("I confirm the document is right, using the offline learner first. It costs nothing and is labelled as such.", "Offline learner: no model, no spend", async () => {
    await page.getByRole("button", { name: "This whole document is right" }).click();
    await until(async () => /#apprentice\/s\/[0-9a-f]+/.test(page.url()), "session");
    await page.getByRole("heading", { name: "Session" }).scrollIntoViewIfNeeded();
  });

  const taught = await runSession(
    "Several rules fit my example. The apprentice found a case where they disagree and shows each outcome. I pick the one I meant.",
    "Before anything is applied it previews the rule on my other documents. Anything that would break the layout is shown as blocked and cannot be approved.",
    120_000,
  );
  await beat(
    taught === "committed" || taught === "activated"
      ? "The rule is committed as a versioned skill, and the page states which model and which teacher produced it."
      : `The session ended in the state ${taught}. I show that as it happened.`,
    `Session result: ${taught}`,
    async () => {
      await page.locator(".prov").scrollIntoViewIfNeeded().catch(() => {});
    },
  );

  await beat("Now I reuse the skill on another document it has never seen.", "Reuse the skill on other documents", async () => {
    await page.locator("label.pick", { hasText: "checkout-service.drawio" }).locator("input").check();
    await sleep(500);
    await page.getByRole("button", { name: "Apply" }).click();
    await until(async () => (await page.locator("article.result").count()) === 1 && !(await page.getByText("Run running").count()), "two results", 180_000);
    await page.locator("article.result").first().scrollIntoViewIfNeeded();
  });

  await beat(
    "Each result shows the checks it passed, or says why it was blocked. The edit is a byte exact patch of label x and y, and I can download the file.",
    "Checked results; download the edited .drawio",
    async () => {
      const r = page.locator("article.result").first();
      const [dl] = await Promise.all([page.waitForEvent("download"), r.getByRole("link", { name: ".drawio" }).click()]);
      await dl.path();
    },
  );

  await beat("If a result is wrong, I correct it. I nudge one label with the keyboard, and the correction becomes a new skill version.", "Correct a result", async () => {
    const r = page.locator("article.result").first();
    await r.getByRole("button", { name: "Correct this document" }).click();
    await page.waitForSelector("#h-correct");
    await until(async () => !(await page.locator("[data-pending]").count()), "output rendered");
    const first = page.locator("#h-correct ~ figure button[data-label]").first();
    await first.scrollIntoViewIfNeeded();
    await first.focus();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    const submit = page.getByRole("button", { name: "Submit correction" });
    await until(async () => submit.isEnabled(), "corrected render");
    await sleep(800);
    await submit.click();
  });
  const corrected = await runSession(
    "It asks the one question the correction leaves open.",
    "It previews the corrected rule before it is accepted.",
    300_000,
  );
  await beat(`The correction session ended as ${corrected}. Every step is logged and can be replayed.`, `Correction result: ${corrected}`);

  if (LIVE) {
    await beat(
      "Now one real session with NVIDIA Nemotron through Nebius Token Factory. This is live, not recorded. It can take a minute, it costs a few cents under a durable cap, and it may abstain. I will show whatever it does.",
      "LIVE: Nemotron-3-Ultra via Nebius Token Factory",
      async () => {
        await page.getByRole("button", { name: "Start over with these documents" }).click();
        await page.getByLabel("Document to edit").selectOption({ label: "training-workflow.drawio" });
        await page.waitForSelector("button[data-label]");
        await placeBelow(p1, objs);
        const confirm = page.getByRole("button", { name: "This whole document is right" });
        await until(async () => confirm.isEnabled(), "draft render");
        await page.getByLabel("Use the live model").check();
        await sleep(600);
        await confirm.click();
        await until(async () => /#apprentice\/s\/[0-9a-f]+/.test(page.url()), "live session");
      },
    );
    const liveEnd = await runSession(
      "The live model proposed candidate rules, and this is the question my example leaves open.",
      "LIVE: the model's candidates, rendered as outcomes",
      360_000,
    );
    await beat(
      liveEnd === "committed" || liveEnd === "activated"
        ? "The live session committed a rule. The provenance line says Nemotron produced it."
        : `The live session ended as ${liveEnd}. A live run can abstain, and I report it as it happened.`,
      `LIVE session result: ${liveEnd}`,
      async () => {
        await page.locator(".prov").scrollIntoViewIfNeeded().catch(() => {});
      },
    );
    ended = `live ${liveEnd}`;
  }

  await beat(
    "How well does this work in general? On a frozen battery of thirty six held out episodes, three repeats, scored by an independent oracle, the apprentice does not beat the same model acting freely on learning success: twenty two of forty eight against twenty eight of forty eight. It does better at refusing inconsistent demonstrations, twelve of twelve against six of twelve, and it costs seventeen cents a run against twenty six. We published the loss.",
    "Frozen battery: apprentice 22/48 vs free agent 28/48 on learning; 12/12 vs 6/12 on conflicts",
    async () => {
      await page.setContent(SLIDE);
    },
  );
  await beat(
    "Four evidence axes, intent, symbolic, native and held out, are kept separate. There is no single verified badge. The code, the evaluation and every failure are in the repository.",
    "Four evidence axes, never one score",
  );
} finally {
  const video = page.video();
  await ctx.close();
  fs.writeFileSync(path.join(OUT, "beats.json"), JSON.stringify({ beats, ended, live: LIVE }, null, 2));
  console.log("video:", await video.path(), "beats:", beats.length, "ended:", ended);
  await browser.close();
}

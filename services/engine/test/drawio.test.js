import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { Engine } from "../src/engine.js";
import { buildServer } from "../src/server.js";

const page = (cells, w = 600, h = 400) =>
  `<mxfile><diagram id="p" name="p"><mxGraphModel page="1" pageScale="1" pageWidth="${w}" pageHeight="${h}"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${cells}</root></mxGraphModel></diagram></mxfile>`;
const node = (id, x, y, w = 100, h = 50) =>
  `<mxCell id="${id}" value="N" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="${x}" y="${y}" width="${w}" height="${h}" as="geometry"/></mxCell>`;
const label = (id, x, y, value = "note", align = "left", w = 80) =>
  `<mxCell id="${id}" value="${value}" style="text;html=1;align=${align};verticalAlign=middle;strokeColor=none;fillColor=none;" vertex="1" parent="1"><mxGeometry x="${x}" y="${y}" width="${w}" height="20" as="geometry"/></mxCell>`;

let engine, app;
before(async () => { engine = new Engine(); await engine.start(); app = buildServer(engine); });
after(async () => { await app.close(); await engine.close(); });

const render = async (xml, extra = {}) => {
  const r = await app.inject({ method: "POST", url: "/drawio/render", payload: { xml, ...extra } });
  return { status: r.statusCode, body: r.json() };
};

test("nodes map back to their geometry and labels measure their glyphs, not the container", async () => {
  const { status, body } = await render(page(node("n1", 40, 40) + label("l1", 200, 100)));
  assert.equal(status, 200, JSON.stringify(body));
  const s = body.nodes.n1.state;
  assert.deepEqual([s.x, s.y, s.w, s.h], [40, 40, 100, 50]);
  const b = body.labels.l1.box;
  assert.ok(b.x >= 200 && b.x < 206 && b.w > 10 && b.w < 80 && b.h < 20, JSON.stringify(b));
  assert.equal(body.labels.l1.lines, 1);
  assert.match(body.profile.viewer_sha256, /^bc7586cb/);
  assert.ok(body.png && Buffer.from(body.png, "base64").subarray(1, 4).toString() === "PNG");
});

test("content far from the origin still measures in document coordinates (nonzero viewer translate)", async () => {
  const { body } = await render(page(node("n1", 400, 300), 900, 700));
  const s = body.nodes.n1.state;
  assert.deepEqual([s.x, s.y], [400, 300]);
});

test("Helvetica resolves to the bundled Liberation Sans on every host", async () => {
  const a = await engine.textWidthForTest("Helvetica", "Hamburgefonstiv 0123");
  const b = await engine.textWidthForTest("OA Liberation Probe", "Hamburgefonstiv 0123");
  assert.ok(Math.abs(a - b) < 0.01, `${a} vs ${b}`);
});

test("a label that wraps reports more than one line", async () => {
  const { body } = await render(page(label("l1", 10, 10, "a long label that cannot fit in thirty units", "left", 30).replace("html=1;", "html=1;whiteSpace=wrap;")));
  assert.ok(body.labels.l1.lines > 1, JSON.stringify(body.labels));
});

test("an empty-looking label is reported missing, not measured as zero", async () => {
  const { body } = await render(page(label("l1", 10, 10, "&amp;nbsp;")));
  assert.ok(body.missing.includes("l1"), JSON.stringify(body));
});

test("no network request leaves the render context", async () => {
  const img = `<mxCell id="i" style="shape=image;image=https://example.com/x.png;" vertex="1" parent="1"><mxGeometry x="10" y="10" width="20" height="20" as="geometry"/></mxCell>`;
  const { status, body } = await render(page(img));
  assert.equal(status, 200);
  assert.ok(body.blocked_requests.includes("https://example.com/x.png"), JSON.stringify(body.blocked_requests));
});

test("oversized and non-string input is refused", async () => {
  assert.equal((await render(123)).status, 400);
  assert.equal((await render("x".repeat(5 * 1024 * 1024))).status, 400);
});

test("a render that times out still closes its browser context", async () => {
  const quick = new Engine({ renderTimeoutMs: 300 }); // long enough that the context exists, short enough to cut the viewer load
  await quick.start();
  try {
    const base = quick.contextCountForTest();
    await assert.rejects(quick.renderDrawio(page(node("n1", 40, 40))), (e) => e.code === "TIMEOUT");
    assert.equal(quick.contextCountForTest(), base);
  } finally {
    await quick.close();
  }
});

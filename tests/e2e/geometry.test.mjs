// Pure overlay geometry and session-state helpers, imported straight from the web app's TypeScript (node type stripping).
// Run: node --experimental-strip-types --test tests/e2e/geometry.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { frameFor, toDisplay, toDoc, step, snap64, parseNum, fmt } from "../../apps/web/src/v2/geometry.ts";

test("doc → display → doc round trip at any displayed size", () => {
  for (const shown of [300, 640, 1024]) {
    const f = frameFor({ x: -32, y: 12 }, 640, shown);
    const d = toDisplay(f, { x: 100, y: 50, w: 30, h: 14 });
    const back = toDoc(f, d.x, d.y);
    assert.ok(Math.abs(back.x - 100) < 1e-9 && Math.abs(back.y - 50) < 1e-9, `${shown}: ${JSON.stringify(back)}`);
    assert.ok(Math.abs(d.w - 30 * (shown / 640)) < 1e-9);
  }
});

test("image pixel = document coordinate + offset at natural size", () => {
  const d = toDisplay(frameFor({ x: 8, y: -4 }, 500, 500), { x: 10, y: 20, w: 5, h: 5 });
  assert.deepEqual([d.x, d.y], [18, 16]);
});

test("nudge steps, 1/64 snapping and exact parsing", () => {
  assert.equal(step({ shiftKey: false, altKey: false }), 1);
  assert.equal(step({ shiftKey: true, altKey: false }), 10);
  assert.equal(step({ shiftKey: false, altKey: true }), 1 / 64);
  assert.equal(snap64(10.007), 10);
  assert.equal(parseNum("105/2"), 52.5);
  assert.equal(parseNum("12"), 12);
  assert.equal(fmt(52.5 + 1 / 64), "52.515625");
});

// Session lifecycle: the engine is shared by every visitor, so a leaked or raced session can lock everyone out.
import test from "node:test";
import assert from "node:assert/strict";
import { Engine } from "../src/engine.js";

const SCENE = { canvas: { width: 200, height: 100 }, nodes: [{ id: "a", type: "rect", x: 1, y: 1, width: 5, height: 5 }] };

test("parallel creates never exceed the session cap", async () => {
  const e = new Engine();
  await e.start();
  try {
    const results = await Promise.allSettled(Array.from({ length: 7 }, () => e.create(SCENE, { owner: "u" })));
    const ok = results.filter((r) => r.status === "fulfilled");
    const limited = results.filter((r) => r.status === "rejected" && r.reason.code === "LIMIT");
    assert.equal(ok.length, 4);
    assert.equal(limited.length, 3);
    assert.equal(e.sessionCount, 4);
  } finally {
    await e.close();
  }
});

test("a scene that fails to load does not hold a slot", async () => {
  const e = new Engine();
  await e.start();
  try {
    const orphan = { canvas: { width: 10, height: 10 }, nodes: [{ id: "c", type: "rect", parent: "missing", x: 0, y: 0, width: 1, height: 1 }] };
    for (let i = 0; i < 6; i++) await assert.rejects(e.create(orphan, { owner: "u" }), /unresolved parents/);
    assert.equal(e.sessionCount, 0);
    await e.create(SCENE, { owner: "u" });
  } finally {
    await e.close();
  }
});

test("idle sessions expire, so abandoned visitors cannot exhaust the cap", async () => {
  const e = new Engine({ idleMs: 1500 }); // longer than creating four sessions takes
  await e.start();
  try {
    for (let i = 0; i < 4; i++) await e.create(SCENE, { owner: "u" });
    await assert.rejects(e.create(SCENE, { owner: "u" }), /session limit/);
    await new Promise((r) => setTimeout(r, 1700));
    await e.create(SCENE, { owner: "u" }); // the idle ones were reclaimed
    assert.equal(e.sessionCount, 1);
  } finally {
    await e.close();
  }
});

test("a crashed browser is reported unhealthy instead of silently failing every request", async () => {
  const e = new Engine();
  await e.start();
  assert.equal(e.healthy, true);
  await e.killBrowserForTest();
  assert.equal(e.healthy, false);
  await e.close();
});

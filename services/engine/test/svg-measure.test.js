import test from "node:test";
import assert from "node:assert/strict";
import { Engine } from "../src/engine.js";

const SVG = `<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200">
  <g transform="translate(40 30)"><g transform="translate(10 0)"><rect id="r" x="5" y="7" width="20" height="10"/></g></g>
</svg>`;

test("world geometry comes from the browser's own matrices, through nested translates", async () => {
  const e = new Engine();
  await e.start();
  try {
    const [r, missing] = await e.measureSvg(SVG, ["r", "nope"]);
    assert.deepEqual([r.x, r.y, r.width, r.height], [55, 37, 20, 10]);
    assert.equal(missing.missing, true);
  } finally {
    await e.close();
  }
});

test("a scaled viewBox is reported in the SVG's own user units, not screen pixels", async () => {
  const e = new Engine();
  await e.start();
  try {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400" viewBox="0 0 300 200"><rect id="s" x="10" y="20" width="30" height="40"/></svg>`;
    const [s] = await e.measureSvg(svg, ["s"]);
    assert.deepEqual([s.x, s.y, s.width, s.height].map((n) => Math.round(n * 100) / 100), [10, 20, 30, 40]);
  } finally {
    await e.close();
  }
});

test("active content and oversized or malformed requests are refused", async () => {
  const e = new Engine();
  await e.start();
  try {
    await assert.rejects(e.measureSvg('<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>', []), /active content/);
    await assert.rejects(e.measureSvg('<svg xmlns="http://www.w3.org/2000/svg"><rect onload="x()" id="a"/></svg>', ["a"]), /active content/);
    await assert.rejects(e.measureSvg("x".repeat(200_001), []), /invalid/);
    await assert.rejects(e.measureSvg(SVG, "r"), /invalid/);
  } finally {
    await e.close();
  }
});

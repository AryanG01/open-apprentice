import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const root = new URL("../vendor/", import.meta.url);
const manifest = JSON.parse(readFileSync(new URL("MANIFEST.json", root)));

test("every vendored file matches its recorded hash", () => {
  for (const [rel, meta] of Object.entries(manifest.files)) {
    const buf = readFileSync(new URL(rel, root));
    assert.equal(createHash("sha256").update(buf).digest("hex"), meta.sha256, rel);
    assert.equal(buf.length, meta.bytes, rel);
  }
});

test("the viewer is the spike-pinned build", () => {
  assert.equal(manifest.files["drawio/viewer-static.min.js"].sha256,
    "bc7586cb62eec98018c13b78619078d3a7179cc7bfc711c566dda19527520a30");
});

test("both font weights are bundled", () => {
  for (const w of ["Regular", "Bold"]) assert.ok(manifest.files[`fonts/LiberationSans-${w}.ttf`], w);
});

test("campaign assets are vendored with their intrinsic size", () => {
  for (const [rel, w, h] of [["assets/h7-headphones.svg", 1000, 1000], ["assets/halden-wordmark.svg", 480, 120]]) {
    const meta = manifest.files[rel];
    assert.ok(meta, rel);
    assert.equal(meta.width, w, rel);
    assert.equal(meta.height, h, rel);
    const svg = readFileSync(new URL(rel, root), "utf8");
    assert.doesNotMatch(svg, /<\s*(script|text|foreignObject)\b|\son[a-z]+\s*=/i, rel);
  }
});

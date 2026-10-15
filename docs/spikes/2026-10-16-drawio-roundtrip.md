# Spike: draw.io round trip (spec gate 2.3, part 1)

**Date:** 2026-10-15 (SGT). **Verdict: PASS on all four criteria, with one finding that changes Plan 3 (whole-unit label coordinates).**

## Setup
- Viewer: `viewer-static.min.js` from `jgraph/drawio` tag `v32.4.1` (Apache-2.0), SHA-256
  `bc7586cb62eec98018c13b78619078d3a7179cc7bfc711c566dda19527520a30`, 4,360,162 bytes; downloaded with the owner's approval
  (`scripts/spikes/vendor/README.md`). The installed desktop app bundles `app.min.js` but not this file.
- Renderer: Playwright Chromium (repo `node_modules`), **all network requests blocked**; viewer injected inline.
- Fixture: `scripts/spikes/fixtures/spike.drawio` (3 rectangle nodes, 1 edge, 3 `text;html=1` labels aligned left/centre/right).
- Scripts: `scripts/spikes/drawio_roundtrip.mjs` (render + measure), `scripts/spikes/drawio_patch.py` (structural x/y patch).
- Re-open check: draw.io desktop 32.4.1 CLI (`drawio -x -f svg --embed-svg-fonts false`).

## Results
| Criterion | Result | Evidence |
|---|---|---|
| Viewer works offline | PASS | `GraphViewer` constructed; `blocked_requests: []`, `page_errors: []` |
| 1. Cell ID → rendered label | PASS | located through `graph.view.getState(cell).text.node` for `l1..l3` (draw.io's cell→state→node association; no DOM ids needed) |
| 2. Measurement in document coordinates | PASS | viewer translate was (−32, −32); node states map back to their geometry exactly (`n1` 40,40,100,50 = geometry). Labels: `l1` left-aligned box x=42 (2 px inset), `l2` centred box centre 270.5 vs cell centre 270, `l3` right-aligned ends at 539; each one rendered line, height 14 at 12 px |
| 3. Patch gives the requested measured displacement | PASS (whole units) | patch `l2` by (+37.5, −12) → measured (+38.0, −12.0), width/height unchanged, `l1`/`l3` unchanged; see finding |
| 4. Re-open in draw.io keeps the edit | PASS | CLI exports of original and patched files differ only in the `l2` group; its `<text>` moved from (230, 74) to (268, 62) = (+38, −12); viewBox unchanged |

## Findings
1. **Measurement primitive.** A `Range` over the whole label node measures the `foreignObject` container (100% width/height, about 20,000 units). The correct primitive is one `Range` per non-empty **text node** inside the label (union of their client rects). Plan 3 must use that.
2. **HTML labels render at whole document units.** Measured displacement for requested dx: 0.5→1, 1.5→2, 37.25→37, 37.5→38, 37.75→38 (`Math.round`-style, half rounds up). The spec's "serialize to the nearest 1/64" therefore does not match what is rendered. **Change for Plan 3:** serialize label geometry to whole units (round half up, matching the renderer) and include that rounding (≤ 0.5) in the conformance tolerance; keep the exact rational target, serialized value and measured result separate as the spec requires. The spec's §6 arithmetic line is to be amended accordingly.
3. **Font.** On this Mac the renderer used the system Helvetica (12 px text, height 14). On Cloud Run (Linux) Helvetica is absent; the bundled-font substitution and drift report of spec §6 remain required and untested here.
4. **No Xvfb fallback needed** for rendering or measurement; the CLI is used only as the re-open cross-check on the authoring machine.

## Not covered by this spike (Plan 3)
Compressed pages, multi-page files, missing `x`/`y` (attribute insertion), wrappers, groups, out-of-rectangle content, refusal paths,
font substitution, and the full round-trip matrix of spec §6.

# headphones3d via img2threejs (v2.0.0), complexity simple

The result is a stylised 3D interpretation of the flat illustration `services/engine/vendor/assets/h7-headphones.svg`,
not a reconstruction. Only one flat front view exists, so all depth, cross-sections, cup thickness and rear faces
are invented. The module is `apps/web/src/headphones3d.ts` (not yet imported by any page).

## What the pipeline produced
Skill state, spec, assessment, PBR evidence and screenshots live in `/tmp/claude-501/i2t/work` (not committed).
The spec has 7 components (headband as a bevelled extrude, 2 cups, 2 cushions, accent dot, root), 4 materials, 5 details.
The shipped TS is hand-written from that spec. The skill's generated factory (1191 lines) was produced for the
`blockout` pass only and was not rendered or shipped.

## Gates run
| Gate | Result |
| --- | --- |
| state init, image-analysis, suitability | done (suitability pass) |
| check_reference_admission | FAILED: 100% foreground, the opaque #1d1240 backdrop defeats segmentation. Recorded, not fixed |
| pre-spec assessment, detail inventory (grid-3x3, 5 real details) | done |
| projection-first route | skipped with reason (flat solid colours) |
| validate_sculpt_spec, then --strict-quality | PASS |
| extract_pbr_evidence per material | band 0.727, cup 0.725, pad 0.787, coral 0.757 (>= 0.7; pad crop includes some cup rim) |
| turntable_gate (4 azimuths) | FAIL on the #1d1240 backdrop (unsegmentable), PASS on a #ebebeb matte backdrop |
| diagnose_render tier 1 (matte ref vs matte render) | first run FAIL (IoU 0.377, framing), after matching framing PASS: IoU 0.852 (threshold 0.85), scale delta 0.024 |
| comparison sheet, append_review (blockout, fidelity 0.82, continue) | recorded, blockout pass completed |
| check_part_coverage (manifest dumped from the live scene) | 0 errors, 0 warnings |

## Not run
Structural, form, material and lighting passes were never walked through the state machine (`next.py` still reports
`structural-pass`). The self-intersection and attachment-anchor gates, interior_difference, multi-angle diagnose and
the VLM gate were not run. The review scores are my own judgement, not an independent evaluation.

## Visual verdict (2 render iterations, headless Chromium)
Band arc, cup shape and placement, and the coral dot match the reference proportions. Iteration 1 showed a gap where
the band legs meet the rounded cup corners, fixed by running the legs into the cups. Colours render duller than the
flat reference under the test lights (band reads light grey), a lighting issue, not the palette values.
## Bundle cost
`npm run build:web` shows no three chunk because nothing imports the module yet (main `index-*.js` 302.22 kB, 94.55 kB gzip,
unchanged). A throwaway library build of an entry that imports the module gives 395.6 kB minified, 80.9 kB gzip, mostly
three.js (the `import * as THREE` form still tree-shakes under Vite/Rollup). Expect to load it lazily.

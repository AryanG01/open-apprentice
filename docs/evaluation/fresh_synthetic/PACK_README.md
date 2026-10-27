# Open Apprentice: Claude prompt and four-banner input pack

**How to use:** extract this ZIP into a folder Claude Code can access. Tell Claude: “Read START_HERE_CLAUDE.md and continue the authorized offline sprint work. The four banner inputs are included.”

## Contents

- `START_HERE_CLAUDE.md`: complete response prompt and ordered implementation/evaluation tasks.
- `inputs/banner_01.png` through `banner_04.png`: four original raster inputs; upload these through the app.
- `evaluator_only/EXPECTED_TEXT_AND_BRIEF.md`: exact visible text and the target story-card brief.
- `evaluator_only/expected_content.json`: machine-readable scoring annotations.
- `evaluator_only/results_template.csv`: blank application evaluation sheet.
- `evaluator_only/manual_timing_template.csv`: blank human comparator sheet.
- `provenance/PROVENANCE.md`: generation history, intended use and evidence limitations.
- `provenance/generation_prompts.json`: exact generation prompts; never give these to the extraction model.
- `run_order.txt`: fixed input order.
- `SHA256SUMS.txt`: integrity hashes for all other files.

## Cases

| File | Product | Case | Intended support |
|---|---|---|---|
| banner_01.png | Teal desk lamp | Short copy; product left | Intended supported, preflight pending |
| banner_02.png | Orange insulated bottle | Different product and reversed composition | Intended supported, preflight pending |
| banner_03.png | Navy portable speaker | Long headline stresses available space | Intended supported, preflight pending |
| banner_04.png | Orange bottle in a forest | Detailed photographic background cannot be preserved by simple flat-background reconstruction | Deliberately unsupported for faithful reconstruction |

All four originals are **1672×941 RGB PNG**. Their aspect ratio is close to 16:9; use existing app letterboxing rather than stretching or replacing originals. They were generated once each, inspected visually for copy accuracy, and not tested in Open Apprentice. No application outcome or timing is supplied or implied.

The simple cases contain mild image-generation shading/product shadows; they are not pixel-uniform backgrounds. Their eligibility must be determined from the documented support policy before model execution. Do not classify them from whether the app succeeds.

## Evidence limitations

These are newly generated fictional examples created for this request with knowledge of the product's support scope. They replace the missing input files for a synthetic smoke test, **not** the evidence value of independently sourced real customer banners. No client, endorsement, actual product offer, external product page or real usage history is claimed.

The headline strings were visually checked against the generated images, ignoring presentation line breaks. See the evaluator notes for normalization rules. Keep evaluation annotations outside inference payloads. Record user correction effort; do not quietly substitute expected text before assessing extraction.

No hand-drawn sketches are included. Real-sketch testing still requires actual owner drawings and its existing protocol. Manual comparator timing and the final audio listening pass still require a person.

# Promo banner to story card: design

**Date:** 2026-10-22 · **Status:** draft for owner approval · **Lane:** new, separate from draw.io and the badge prototype

## 1. Intent and why

Today's demo teaches one thing: where a note sits beside a box (an x/y rule). A demanding judge, or a real user, sees label
placement. This lane proves the apprentice can learn a *compound* visual edit from one demonstration, ask about the one case
where the right answer is a matter of taste, and reuse the approved result on a different asset, with every result checked by an
independent verifier against an authored expected output.

The scenario: an authored, layered 16:9 promo banner for a fictional headphone brand is adapted by the owner into a 1080×1920
(9:16) social story card. The apprentice learns that base layout and applies it to other banners. When a localized banner's copy
cannot fit one story card legibly, it stops, renders two real editable outcomes from **built-in, labelled** overflow
procedures, and asks which one the owner wants.

The campaign/promo category is a **provisional test asset, not a validated user need**. Owner interviews decide whether it
becomes the product direction; they do not block this vertical slice.

## 2. Goals

1. **Teach the base layout.** One before/after pair (16:9 banner, 1080×1920 story) on separate, editable nodes: background,
   brand mark, product image, headline, price, CTA button, legal line. The learned layout:
   - places the brand mark in the top safe area;
   - makes the product image the hero, uncropped, aspect ratio and focal point preserved;
   - stacks headline, price and CTA in reading order (regroups them into one offer group);
   - makes the CTA full width and applies the taught CTA style (corner radius);
   - anchors the legal line inside the bottom safe area;
   - is conditioned on the requested output format (16:9 to 9:16), not inferred from accidental geometry.
2. **Preserve.** Exact copy, CTA destination URL, logo, legal text, image aspect ratio and focal point. Any change blocks commit.
3. **Reuse by role, not coordinates.** The layout applies to another authored banner with different node IDs, dimensions and
   copy. A result that replays the teaching coordinates fails.
4. **Ask on overflow, with built-in outcomes.** The teaching pair has short copy, so it cannot teach overflow behaviour. The two
   outcomes are fixed **reference procedures**, labelled as built-in in the UI, receipts and evidence, never credited to the
   learner or to Nemotron. A deterministic fit check (rendered text, real font) decides whether everything fits one card within
   safe areas and minimum sizes; Nemotron never decides fit and does not invent the outcomes. On overflow the apprentice renders
   both outcomes as real native scenes and asks:
   - **A. Shrink the hero (built-in):** scale the product image proportionally (no crop, no distortion) down to a validated
     minimum. If the card still fails the fit check, do not partially apply; show A as "does not fit" and offer B.
   - **B. Split into two cards (built-in):** two 1080×1920 artboards in sequence. Card 1: brand mark, full headline, hero image.
     Card 2: brand mark, price, the original CTA with its URL, full legal line. Each copy string appears exactly once; the brand
     mark repeats on both cards by design.
   - **Neither:** source unchanged.
5. **Apply, verify, save the preference.** The chosen outcome is applied, rendered natively, checked by the independent verifier
   and shown as a diff. The choice is saved as a **user-selected preference** (not a learned branch), versioned and editable,
   scoped by default to `(promo_card, 9:16, overflow, de)`. The next German long-copy banner uses it without asking; a banner in
   another language asks again.
6. **Konva first, then Fabric.** Full scenario including both outcomes in Konva. Then the same scene/action contract in Fabric
   (including groups and artboards). No parity claim until the same learned layout passes the same fixtures on both.

## 3. Non-goals

- Figma, React, Canva, PowerPoint or Blender adapters.
- General layout learning beyond this transformation family.
- Learning the overflow strategies themselves.
- Extending the z3 symbolic compiler or witness search to the new constructs (see 7.9).
- Replacing or tuning the draw.io lane. The frozen benchmark (`docs/evaluation/final_results.md`) stays unchanged.
- Model-comparison claims. Any learner/policy results from this lane are labelled **development results**.
- Changing the submitted hackathon video. It stays on draw.io unless this lane is integrated and demonstrated live first.

## 4. Anti-goals (would be failure even if it "works")

- A recorded, component-specific script or coordinate replay presented as a learned layout.
- A flattened screenshot or image swap presented as an editable result.
- A preview that cannot actually be applied presented as an option.
- Nemotron guessing whether text fits.
- A built-in or reference procedure presented as learned or as model output (same discipline as `repaired_by`).
- Calling the public development banners "held out", or claiming generalization without the private sealed set.
- One German answer applying to other languages without asking.
- Partial application: a card that half-fits, or a split with dropped copy, ever being committed.
- The verifier sharing measurement or geometry code with the engine or calling `measure_node`.

## 5. Constraints (from the repo rules)

- Restricted JSON-AST only (`skills/interpreter.py`, `concepts/rules.py`); no eval/exec or dynamic loading.
- Agent-visible packages never import `evaluation/verifier.py` or `benchmarks/final/` (`lint-imports` contract unchanged). Gold
  outputs are evaluator-side data and get the same isolation.
- Four evidence axes stay separate; no single "verified" badge.
- `PROVIDER_MODE=mock` default; deterministic behaviour fully testable with no Nemotron credit. Live calls only within the
  existing ledger cap; spendable credit is about $1.40-3, so live evidence from this lane will be small and labelled.
- Only owner-authored or provenance-verified assets. The fictional brand, product image and copy are authored for this repo;
  fonts are the vendored Liberation Sans files with their recorded provenance (`services/engine/vendor/MANIFEST.json`).
- Python 3.12; tests on 3.12.

## 6. What exists and the gap

| Area | Today | Needed |
|---|---|---|
| Engine scene (`dispatcher.browser.js`) | Konva `Rect` and `Group` only; style fields fill/stroke/strokeWidth/opacity | `Text`, `Image`, `Shape`, `Artboard` (plus Rect/Group); corner radius; z-order; CTA URL metadata; text wrap settings |
| Engine tools | move, resize, style, clone, group, ungroup | `create_artboard`, `reparent_nodes`, `set_order`, `set_style` (incl. cornerRadius), type-aware text and image-contain-fit operations; all allowlisted |
| Fabric (`dispatcher.fabric.js`) | flat rects; groups rejected | same node and tool contract as Konva |
| Text measurement | browser measurement inside `drawio.js` and a test helper only | an engine fit observation: measured line boxes per text node, safe-area and minimum-size violations |
| Rule language (`concepts/rules.py`) | Fraction geometry; `move_existing`, `resize_existing`, `clone_place` | format condition, observed-overflow fact, regroup, set_order, set_style, image contain-fit, `ask` |
| Procedures (`skills/interpreter.py`) | badge/label procedures | per-backend procedures using the new tools; reference procedures for the base layout and both overflow outcomes |
| Verifier (`evaluation/verifier.py`) | world-space geometry of rects/groups | independent text layout, invariants (7.7), comparison with authored gold outputs |
| UI | badge prototype (`TryIt.tsx`), SVG lane, draw.io Apprentice tab | a Campaign tab: teach, question, apply, diff, save preference |

## 7. Decided design

### 7.1 Scene model (shared schema, both backends)

Each node: `id`, `type` (`rect | shape | group | text | image | artboard`), `parent`, `role`, `x, y, width, height`,
`scaleX/Y`, `z` (explicit order within its parent), style (`fill, stroke, strokeWidth, opacity, cornerRadius`).
Text nodes add `text`, `fontFamily` (vendored font id), `fontSize`, `fontWeight`, `lineHeight`, `align`, `wrap: "word"`.
Image nodes add `asset` (stable asset id, bytes vendored with hash), `crop` (must stay full-frame), `focal` (x, y in image space).
The CTA is a group of a rect and a text with `link` metadata. Artboards are exactly 1080×1920 for the story format and carry
`format`, `safe` (insets) and `sequence` (order within a story set). Source banners keep their own 16:9 size.

Roles: `background, brand_mark, product_image, headline, price, cta, legal`. Authored assets carry them on each node. A node
with no role, or two nodes claiming one role, stops the run and asks the owner to confirm the mapping (no guessing).

### 7.2 Fit is an observation, not a rule computation

The engine renders text with the vendored font and returns, per text node, measured line boxes and total height, plus any
safe-area or minimum-size violation for a proposed layout. The rule receives this as an input fact (`overflows` and measured
heights); it never measures text. Run order: apply the learned layout to a scratch copy, observe fit, then either commit the
layout or raise the overflow question.

### 7.3 Rule language extension

Add, inside the existing validator and step/expression caps:
- a top-level condition on `output_format`;
- reading the observed `overflows` fact;
- new emit kinds: `regroup` (parent change), `set_order` (z within parent), `set_style` (allowlisted fields incl. cornerRadius),
  `fit_image_contain` (proportional scale into a box, never crop);
- an `ask` statement naming built-in outcomes (`builtin_shrink_hero`, `builtin_split_two_cards`). It emits no edit; it stops
  the run and returns the question. A saved preference for the matching scope resolves the `ask` to that outcome.

Every emit kind declares its writable properties; the validator rejects anything else (text content, URL, asset, crop are never
writable). Artboard creation and routing belong only to the built-in split procedure, not to the learned rule.

### 7.4 Learning and procedures

From the teaching pair the learner derives the base layout from role-matched before/after diffs. A deterministic enumerator
covers this family; Nemotron may propose alternative rule ASTs through the existing hybrid path (`concepts/hybrid.py`), with
origin tagged. Every candidate runs in the exact interpreter on the teaching pair and must reproduce the owner's target.

The rule reaches each backend through checked JSON-AST procedures (`skills/interpreter.py`) using the new allowlisted tools. The
procedures start as labelled reference procedures. Nemotron-written procedures are optional; if used, they are identified by
source in receipts and UI and evaluated separately against the reference procedure. No reference-procedure result is credited
to Nemotron.

### 7.5 Overflow question and outcomes

When the fit observation reports overflow, the run returns both built-in outcomes already applied to scratch copies of the scene,
rendered natively, each with its own verifier result. If A cannot meet minimums it is shown as "does not fit" and is not
applicable. Choosing applies that exact scratch result; choosing neither leaves the source untouched.

### 7.6 Preference and reuse

The answer creates a versioned preference record: scope `(promo_card, 9:16, overflow, de)`, chosen outcome, parent version,
provenance (teaching pair, fit observation, previews, answer, verifier report). The owner can change or roll it back (existing
versioning pattern from Plan 2). The next German long-copy banner runs without asking and is verified; another language asks.
The UI and evidence always show the preference as the owner's choice of a built-in outcome, distinct from the learned layout.

### 7.7 Independent verifier and gold outputs

A separate Python module under `evaluation/` reads the final native scene state and checks:
copy strings, CTA URL, legal text and logo asset are byte-identical to the source; each copy string appears exactly once across
cards; image aspect ratio and full-frame crop are unchanged and the focal point is inside the visible frame; role order on each
card; card count and sequence; every node within its artboard's safe area; text, CTA and image minimum sizes; text fits its box;
properties outside the edit allowlist are unchanged.

It also compares the result with an **authored gold output** for that banner and outcome, within predeclared geometric
tolerances. Gold outputs are evaluator-side: the learner and agent-facing tools never see them.

Text fit is recomputed independently from the vendored font files with a separate Python implementation (font tables read
directly, likely via a new `fonttools` dependency), not from the engine's measurements. The two can disagree by kerning or
rounding, so the verifier uses a stated tolerance, and the tests include deliberate disagreement cases where the engine says
"fits" and the verifier must reject.

### 7.8 Test assets

**Public development fixtures**, authored in-repo with provenance: the teaching pair; at least two short-copy banners (different
IDs, sizes, copy); at least two German long-copy banners (longer headline, larger product image, longer legal line); one
non-German long-copy banner (must ask again); one asset with a missing role and one with a duplicated role (must stop and ask).
Each fixture has an authored gold output per applicable outcome. These are development tests, never called held out.

**Private sealed set** (later, before any generalization claim): separate banners and gold outputs authored before evaluation,
held like `benchmarks/final/`, not committed and not visible to agent code.

### 7.9 Evidence axes for this lane

- **Intent:** the owner's teaching pair, role confirmations and overflow answer.
- **Symbolic:** reported **not used** for this lane. The z3 compiler handles rectangle geometry only, and the question here comes
  from a deterministic fit check, not from disagreeing candidate rules or a witness search. Disclosed, not hidden.
- **Native:** engine render plus fit observation on each backend.
- **Held-out:** only from the private sealed set; public fixtures report as development.

## 8. Success bar

- Both built-in outcomes produce complete, editable native outputs; "neither" changes nothing.
- Each output matches its gold output within tolerance and passes every verifier invariant; any failure blocks commit and leaves
  the source intact.
- The owner's answer changes the applied result.
- A later German long-copy banner uses the saved preference without asking and verifies; a non-German one asks again.
- A banner with different node IDs is handled by role, not by replayed coordinates.
- Konva first; Fabric parity claimed only when the same learned layout passes the same fixtures on Fabric.
- Generalization claimed only after the private sealed set passes.

## 9. Build order (by dependency, not a scope cut)

1. Scene schema and Konva node types (text, image, shape, artboard, corner radius, z-order, link metadata).
2. Engine fit observation.
3. Fixtures and gold outputs; independent verifier including the disagreement tests.
4. New allowlisted tools and reference procedures.
5. Rule language extension and learner for the base layout.
6. Overflow question, both built-in outcomes, "neither".
7. Preference record, versioning and reuse.
8. Campaign UI tab.
9. Fabric: the same contract, then parity on the fixtures.
10. Private sealed set, before any generalization claim.

Every step lands with its tests; no branch ships as "unsupported yet".

## 10. Left to the builder

- Internal module layout and naming within the constraints above.
- Exact minimum sizes, safe-area insets and verifier/gold tolerances (stated in code and the plan, frozen before any evaluation).
- How the Campaign tab is laid out, following the existing web app's styles.
- Choice of Python font library for the verifier, if not `fonttools`.

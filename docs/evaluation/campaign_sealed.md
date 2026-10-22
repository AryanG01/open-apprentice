# Campaign lane: sealed held-out set, result (2026-10-22)

**Who wrote the set.** A fresh Claude agent wrote it, not the owner. It followed only the written rules
(`campaign_sealed_howto.md`, `campaign/limits.py`, `campaign/builtins.py`, `campaign/plan.py`) and format examples (the
public teaching pair, `de_long_a`, and its gold). It never saw the learner, the verifier, the engine or the tests, and it
never ran the system on its banners. It decided fit with its own fontTools script. The banners and gold stay private in
`benchmarks/final/campaign/` (git-ignored). Their hashes were committed in `campaign_sealed_manifest.json` (combined
`7a53dd3ad32afdd5…`) before the first run.

**The set.** 8 banners in 4 locales the development fixtures do not use (es, nl, pl, it), with new copy and new source
layouts:
- 3 short banners that should fit the story card;
- 3 long-headline banners where shrink and split are both correct;
- 2 extra-long banners where only split is correct.

**Result** (`oa eval campaign-sealed-run`; learned from the public teaching pair only; questions answered with the gold
outcome):
- **22 of 22 verifier rows pass on Konva and Fabric** against the sealed gold.
- **Asking, checked separately:** it never asked on the 3 short banners and always asked on the 5 long ones. On both
  extra-long banners the shrink preview was marked "does not fit" and split "fits". So 16 of 16 banner-engine cases
  matched the expected question and options.

**What this does and does not show:**
- It shows that the rule carries over to new copy, new languages and new source positions in both engines, and that the
  overflow decision matches an independent font measurement.
- The authoring agent is the same model family that built the system, so "held out" here means "not seen during
  building", not "written by a different person".
- The cases were picked to be clear: each headline is at least half a line away from a wrap boundary. Borderline copy
  is not tested.
- Font sizes match the teaching example, and the story layout is fixed by role, so the gold is close to determined by
  the written rules. This tests applying the rule correctly, not learning a new layout.
- Reproduce with `oa eval campaign-sealed-run`; the raw rows are in `results/campaign_sealed/2026-10-22/` (local, not
  committed).

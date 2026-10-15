# Claims and limitations (redesign: teach conditional edit programs)

What Open Apprentice can be said to do, with the evidence behind each statement. Numbers come from `results/redesign/*`
(git-ignored; the run ids are in `docs/redesign_gate.md`) and every one is a single run of one model unless it says otherwise.

## Claims we make
1. **Learns a small conditional edit program from 1-2 demonstrations and applies it to unseen diagrams.** On a frozen gate set of
   15 episodes (5 layouts x relative / conditional / scope) the apprentice, driven by Nemotron-3-Ultra, was 15/15 in two
   assembled runs, with zero accepted wrong commits and zero preservation or layout violations on the fresh scoring documents.
2. **Asks only when the demonstrations leave the behaviour open, and commits only to what it has checked.** Held-out split
   (seed base 50000, one run): 8/8 unambiguous, 8/8 ambiguous (asked, then committed correctly).
3. **Abstains rather than guess when the behaviour is not expressible.** Held-out unsupported episodes: 2 appropriate abstains,
   0 wrong commits (2 episodes ended in provider errors, no answer).
4. **The checker is independent of the learner.** The oracle that scores fresh documents is plain Python sharing no code with the
   rule evaluator; intent, preservation and layout are separate axes.
5. **Real SVG files, byte-exact edits.** Learned rules become typed patches that change only the `x`/`y` of label `<text>` tags;
   every patch showed 0 unrelated byte changes.
6. **A same-model baseline exists and is weaker on the conditional intention** in the two valid runs (2/5 in `gate-3`, 1/5 in
   `gate-9`, vs the apprentice 5/5 both times), with no wrong commits in `gate-9`. Both receive identical evidence and the same
   language help in the final protocol. (An earlier "0/5" was a harness bug of ours and is retracted in the gate doc.)

## Limits we must state with those claims
- **Small n, one model, one run each.** 5 per intention cell. Same-model variance is real: the same episode flipped between
  commit and abstain on re-run. No confidence intervals are claimed.
- **Synthetic task family, authored fixtures.** Documents come from our generator (boxes + labels on a grid). The "real files"
  are five SVGs authored for this project, not third-party or user-exported files. Label boxes on them are ESTIMATED from font size,
  not browser-measured.
- **Catalogue-relative ambiguity.** "Ambiguous" means several of 24 catalogue behaviours fit the demonstrations; it says nothing
  about behaviours outside the catalogue, and the oracle-assisted reference learner is a ceiling, not a result.
- **Noisy demonstrations are NOT handled.** When one demonstrated label is displaced, the learner often fits it with a special-case
  rule: 7 wrong commits in 20 noisy episode-runs (development repeats the same 4 episodes while the learner changed; held-out
  1/4). The constants guard misses special cases written with computed values.
- **Held-back validation reads teacher answers on batch diagrams** (never the fresh scoring documents). It costs some
  correct commits (some ambiguous episodes abstain instead) and is not free of tuning: it was added after development runs.
- **Provider instability.** The endpoint intermittently ignored the system turn, echoed the evidence, truncated, or stalled. Both
  systems now send instructions in the user turn and compact evidence; several runs were discarded or stopped (listed in the gate
  doc). Provider errors are reported as errors, never as abstains or successes.
- **Post-hoc changes.** Prompt example, parser fixes, validation, compact evidence and the user-turn protocol were added after
  seeing failures on development and, for the last two, gate episodes. The gate set was not tuned on episode content, but it
  was seen in aggregate during diagnosis.
- **Real-file conditional coverage is thin.** One live real-file run (`realfile-2`) had 51/52 applications correct with one
  accepted layout violation (a rule that ignored the canvas edge). The teaching batches have since been widened; the rerun is
  recorded in the gate doc.
- **Not measured:** external users, other models, other task families, diagrams with curved or rotated shapes, text measured by a
  real renderer, any claim about reduced human editing time.

## What must NOT be said
- "Verified" or "correct" without naming the axis and the document set.
- That the apprentice "generalises" beyond this label-placement family, or that it beats other agents in general.
- That held-out results are a rate; they are one run of 24 episodes.
- Anything about the Gym calibrated-asking environment's numbers in this document: that is a separate result in `docs/HANDOFF.md`.

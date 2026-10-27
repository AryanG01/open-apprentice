# Strict scoring rubric (frozen 27 Oct 2026, before the final sprint work)

Used for every self-assessment and for the independent judge. Four criteria of 25 points each (the hackathon weights them
equally); the sprint targets three of them: Design/Completeness, Potential Impact, Idea/Originality. A score is what a sceptical
judge could defend from artifacts alone (video, live app, repository, written results). Claims without an artifact score zero.
Self-estimates are not allowed to count anything that depends on an unmeasured future event.

## Design / Completeness (25)
| Points | What a judge must be able to see |
|---|---|
| 22-25 | Inputs the team never tried (a held-out set of at least 8 banners that includes tall products, gradients, long copy and a photo) produce a visually clean finished card on at least 6 of 8, with no stray fragments, no clipped products, no overlaps; every other input is stopped early with a plain reason and a next step (never a silent bad card). The result screen leads with the finished card at phone scale. A downloadable change report exists. Keyboard and screen-reader paths work. First useful card within 30 s of opening the app. No dead ends in any state (error, quota, expired workspace, refused input). |
| 17-21 | Clean cards on most supported inputs, but some visible flaws pass the checks, or refusals are late/unclear. |
| 12-16 | Works end to end on curated inputs; visible flaws on new inputs. (Where we were on 27 Oct: 15.) |
| 0-11 | Breaks or confuses on ordinary inputs. |

## Potential Impact (25)
| Points | What a judge must be able to see |
|---|---|
| 22-25 | A sharply defined user with a real recurring cost, sourced. Real adoption evidence beyond the team: dozens of outside users or a named organisation using it on real work. A credible path to scale. |
| 17-21 | At least 10 outside people used it on their own banners; at least 6 got a usable card; at least 3 give permissioned quotes that they would use it on real work; at least 2 practitioner interviews; measured time saved; the problem is sourced and sized. |
| 12-16 | A real problem and a coherent demo, but no outside evidence (where we were: 11). |
| 0-11 | Problem unclear or not shown. |

## Idea / Originality (25)
| Points | What a judge must be able to see |
|---|---|
| 22-25 | A new idea that is not already a shipping feature of the obvious incumbents, stated in one sentence that a stranger can repeat; a mechanism that is demonstrably different (not a wrapper); a live proof moment that makes the difference obvious in 30 s. |
| 17-21 | A distinctive combination or wedge on a known problem, honestly positioned against the incumbents with their real features, with a mechanism and a proof moment of its own. |
| 12-16 | Competent application of known pieces. (Where we were: 16.) |
| 0-11 | Indistinguishable from a template. |

## Rules that keep the scoring honest
- Ceilings are stated, not hidden: an input type we refuse counts as correct handling only if it is refused before a bad output.
- "Clean" is judged by a checklist on the exported card at phone scale: every approved word present and legible; product complete and
  undistorted; no fragment of another element; logo intact; nothing outside the safe area; no accidental overlap; spacing balanced.
  The judge is not the author of the change under test (an independent reviewer, plus the owner).
- Held-out means: not used to tune any code or threshold. After a held-out run, any fix is a development change and the set is spent.
- Evidence from the team's own generated banners never counts toward Impact.

# Plan: lift Design/Completeness, Potential Impact and Idea/Originality (written 27 Oct 2026, ~17:50 SGT)

Deadline: 31 Oct 01:00 SGT. Submission target: **Fri 30 Oct 18:00 SGT**. Hours left: about 72, of which roughly 45 are working
hours for me and an unknown number for you.

## 0. What I can and cannot promise (read this first)
I will not tell you I have "full confidence" in 22+/25 on all three. That would be a lie, and you asked me not to lie.
- **Design/Completeness: 22 is reachable by engineering**, because it depends on things I can build and measure (a held-out set,
  a checklist, a blind reviewer). The independent baseline is 13, not 15, and a held-out mix that includes gradients and photos cannot reach 6 of 8 clean inside the flat-background envelope. My honest odds of a defensible 22: about 10%; of 18 or more: about 65%; of 20 or more: about 35%.
- **Idea/Originality: 22 is not reachable in 3 days by building.** The concept (a banner to story-card adapter) sits next to
  shipping features of Canva and Adobe. I can move it from 16 to about 19-20 by sharpening the wedge and adding proof moments that
  do not exist elsewhere. Odds of a defensible 22: under 10%; of 19 or more: about 60%.
- **Potential Impact: 22 requires real adoption**, which no code can create in 3 days. With 10+ outside users, practitioner
  quotes and measured time saved I can defend 17-18 (odds about 55%, and it depends entirely on you recruiting). Without outside
  users it stays at 11-12. Odds of a defensible 22: under 5%.
- Expected total on these three if every gate below passes: **about 52 to 58 of 75, not 66** (from a baseline of 35 by the independent judge). That is a strong, honest result; it
  is not the number you asked for. The point of the plan is to take every point that can be earned honestly and to stop claiming
  the ones that cannot.

Why the last estimate dropped (65 to 63): the evidence got worse (the first honest test on new banners failed to produce a clean
card), not because the plan changed. This plan is built on the failures, and its gates are fixed **now**, before any work, in
`docs/plan/strict_rubric.md`. A gate that fails will be reported as failed; I will not re-score the rubric afterwards.

## 0b. Independent baseline (fresh-context judge, artifacts only, frozen rubric, 27 Oct)
**Design 13, Impact 9, Idea 13** (my own estimate was 15, 11, 16; the lower numbers are the ones to quote). Its decisive points:
0 of 4 new inputs gave a clean card; "You chose neither, so nothing was changed" blames the user instead of giving the real reason;
the photo background was never refused; no outside user; the submission never answers "why not Canva or Adobe resize"; the README
sprawls across several projects so there is no single repeatable sentence; and the green "15 of 15 checks passed" panel is
presented as trust although the video later admits both built cards had visible flaws. Its verdict on reaching 22: Design only
partly achievable (a held-out mix with tall products, gradients and a photo cannot reach 6 of 8 clean, because gradients and photos
are outside the flat-background envelope and can at best be refused correctly); Impact 22 not achievable; Idea 22 not achievable.
I agree with all of that and have changed the plan below accordingly.

## 1. Root causes found on 27 Oct (evidence, not opinion)
1. Clean output fails on new inputs: logo fragment inside the product crop (lamp), product clipped by a loose box (speaker, bottle),
   three boxes on the wrong lines when a headline wraps to five lines, a tall narrow product refused by a frozen min-width rule,
   a photographic background silently flattened, a sparse second split card. Checks passed 15/15 on both built cards.
2. The product builds one format (9:16). Real campaigns need more; I will not widen formats in 3 days (see section 5).
3. Zero outside users, zero real sketches, zero third-party banners.
4. Pitch overlaps incumbents; the difference (approved words survive, with proof) is not yet something a stranger can see and
   check in 30 seconds.

## 2. Workstream D: Design/Completeness (target gate: rubric 22)
All work is on flat backgrounds first (the documented envelope), plus honest handling beyond it.
| # | Work | Why it moves the score | Acceptance gate | Time box / kill |
|---|---|---|---|---|
| D1 | **Clean-crop engine** in the browser: (a) tighten the product box to its true extent (largest non-background component), (b) paint other layers' boxes (logo, text) with the background colour inside every crop, (c) detect a crop whose content touches its own edge (clipped) and grow or flag it, (d) sanity-check each text box for ink coverage and, when the box covers little ink and the text column has exactly as many ink blocks as text roles, reassign boxes in reading order | Fixes the four visible defects found (fragment, clipped product, misplaced boxes). Deterministic, no model call | On the four fresh banners and the 6 development fixtures: 0 stray fragments, 0 clipped products, text boxes on target; unit tests for each primitive | 6 h. Kill (d) if it mis-assigns on any dev fixture; keep (a)-(c) |
| D2 | **Tall and narrow products**: amend the minimum-size rule to "width at least 432 px **or** height at least 700 px" (a superset of the old rule, so every earlier result stays valid), use the existing contain placement | The bottle banners build instead of failing | Both bottle banners build a clean card; sealed/gold/verifier tests unchanged; mutation table re-run | 4 h. Kill if the layout rule needs a new learned rule: then the app refuses tall products early and says so |
| D3 | **Early honest refusal**: preflight the background before spending a model call; for a photo or busy background show one screen (why, and two buttons: "Use a flat-colour version (lossy, labelled on the card and in the report)" or "Start over") | Removes the silent-flattening failure; no dead end | Forest banner: stopped before the model call with the screen; the lossy path produces a card labelled "simplified" | 3 h |
| D4 | **Result screen**: finished card first, phone-frame preview, zoom, before/after, report download; plain empty, error, quota and expired-workspace states | "Completeness" is mostly absence of dead ends | Walkthrough checklist of 12 states, each with a screenshot; axe scan of the new states | 5 h |
| D5 | **Split card 2** (versioned, not silent): improve composition behind a new outcome id, keep v1 for the frozen fixtures, document that fixtures still run v1 | The sparse card is the first thing a judge sees on the German demo | Before/after at phone scale; if it cannot be done without touching frozen gold, the demo uses shrink and the limit stays documented | 3 h, drop first if time is short |
| D6 | **Held-out check**: 8 new banners (you generate them from my spec: 2 tall products, 1 soft gradient, 1 photographic, 2 long headlines, 2 reversed or different layouts) | The only honest test of D1-D5, because the four banners are now spent | Reported as two numbers: clean cards among the **in-envelope** inputs (target at least 5 of 5: the tall, long and reversed ones) and correct early refusals among the **out-of-envelope** inputs (gradient, photo: target 3 of 3). It is **not** 6 of 8 clean: gradients and photos are outside the envelope and the rubric's 22 band is therefore not claimed. A non-author scores the exports | run once; never tuned on |
| D7 | **Say the real reason** on every stop: replace "You chose neither, so nothing was changed" with the cause ("the product picture would have to be narrower than the minimum") and one next step; same for blocked editor states | Removes a message that blames the user | Every refusal path has a reason string asserted in a test | 2 h |
| D8 | **Reframe the checks**: call them "structural checks (copy, link, logo, sizes, overlaps)" and show beside them the new "picture check" from D1 (no foreign fragment, product not clipped); stop presenting a green panel as trust | The first-minute contradiction the judge found | The result panel and video wording never imply the checks judge the pictures | 1 h |

## 3. Workstream I: Idea/Originality (target gate: defensible 19-20)
The wedge, in one sentence a stranger can repeat: **"Resize your ad for vertical formats without changing a word of the approved
copy, and get a receipt you can check."** Incumbents resize and regenerate; none (to my reading of their public pages) hands you a
verifiable record that the approved words, price, link and picture survived. I will say "to our reading", not "no one".
| # | Work | Acceptance gate | Time box |
|---|---|---|---|
| I1 | **Receipt**: downloadable JSON plus printable page: source and output hashes, every approved string with a byte-for-byte compare, link, price with the page-check scope, picture hashes and aspect, the checks list, the choice made and its saved scope, the models and tools that ran | A stranger can recompute the hashes from the exported files with a 30-line standalone script that ships in the repo and passes | 5 h |
| I2 | **"Try to break it"** live proof moment: one button mutates a copy of the finished result (delete the product, change a price digit, push the headline out of bounds) and shows the independent checker failing it | Works for all three mutations in the UI and on Konva and Fabric; appears in the video at second 30 | 3 h |
| I3 | **Honest positioning table** in README and submission: Canva Magic Resize/Layers, Adobe Express resize versus this, using only what their public pages say, with the links and the date read | Each row cites a page; no superlatives | 2 h (I need web access for it) |
| I4 | The ask-before-guess and per-language memory stay, shown once, briefly | Already proven in the browser test | 0 |
| I5 | Plain statement of what is not novel (resizing, layer extraction) | In the submission | 0 |
| I6 | **Side-by-side with an incumbent**: the owner runs the same German banner through Canva (or Adobe Express) resize and we show their real output beside ours; I report whatever it does, including if it does the job well | A screenshot pair, dated, with the tool and plan named | 1 h of yours, 1 h of mine |
| I7 | **One-sentence README**: the first screen of README says the wedge and nothing else; the diagram, badge and Gym material move below a divider labelled "earlier work" | A stranger can repeat the sentence after 10 seconds | 1 h |

## 4. Workstream U: Potential Impact (target gate: defensible 17-18; needs you)
| # | Work | Acceptance gate | Owner needed |
|---|---|---|---|
| U1 | In-app feedback (3 questions, no image stored) and a consent line; stored server-side for the pilot | Works on the candidate; no image leaves the page except to the models, as today | no |
| U2 | **Pilot**: at least 10 outside people, each running their **own** banner (at least 5 real banners, not ours); I supply a 10-minute script, a consent text and a form | n >= 10 sessions logged; at least 6 usable cards by the tester's own rating; time to first card; at least 3 permissioned quotes about real use | **Yes: recruit 10+ people by Wed night** |
| U3 | **2-3 practitioner interviews** (a marketer, an agency or ad-ops person, an SME owner): does a verifiable change record matter? | Notes plus one permissioned quote each | **Yes: introductions** |
| U4 | Sourced problem statement: why vertical formats and copy accuracy matter (platform ad specs, price-mismatch disapprovals), with links and dates | Every number has a source I fetched | no |
| U5 | Time saved: tester's own estimate of the manual time versus measured time to a card; reported as a small, self-selected sample | Table with n and the caveat | covered by U2 |
Without U2 and U3 the Impact ceiling is about 12. I will say so in the submission rather than imply otherwise.

## 5. What I am deliberately not doing
New output formats (1:1, 4:5, 16:9): each needs its own taught layout, constants and verifier; too risky to add safely in 3 days
and it would spend the time D1-D6 need. Image generation (Token Factory offers none). Photographic backgrounds (D3 refuses
them honestly). Accounts or durable memory. A new learner. Real-sketch evaluation unless you send five drawings.

## 6. Schedule (SGT)
| When | Work | Gate |
|---|---|---|
| Tue 27 night | D1 (a)-(c), D2 spike, request the held-out set and the pilot | unit tests green |
| Wed 28 | D1 (d), D2, D3, D4, I1, I2, U1; independent blind review of the exports against the rubric | G1: dev fixtures and four spent banners clean |
| Wed 28 late | Full gates; **you deploy candidate A**; pilot starts | smoke on the candidate |
| Thu 29 | Held-out run D6 (once); pilot sessions; only P0 fixes; I3, U4; interviews; re-record video | G2: held-out result reported as is |
| Thu 29 night | Final suite, `lint-imports`, **you deploy final**; listening pass | all gates |
| Fri 30 | Upload, form, submit by 18:00 | buffer 7 h before the deadline |

## 7. Confidence by gate (my estimates; they will be updated with evidence, never silently)
| Gate | Odds | If it fails |
|---|---|---|
| D1 (a)-(c) clean crops | 85% | cards still flawed; Design stays at 17-18 |
| D1 (d) text reassignment | 55% | boxes still need dragging; keep the sanity flag only |
| D2 tall products | 65% | refuse them early (D3 wording) |
| D3 early refusal | 95% | none |
| D4 result screen, no dead ends | 85% | |
| D5 split polish | 50% | demo uses shrink |
| D6 in-envelope 5 of 5 clean and out-of-envelope 3 of 3 refused | 40% | report the real numbers; Design 17-19 |
| D7, D8 honest messages and wording | 95% | |
| I6 incumbent comparison (needs you) | 70% | skip it and say it was not run |
| I1 receipt and verifier script | 90% | |
| I2 break-it | 90% | |
| U2 pilot n >= 10 | 55% (your recruiting) | Impact stays at 12 |

## 8. How I keep myself honest
1. Rubric frozen before work (`docs/plan/strict_rubric.md`, committed).
2. A fresh-context judge agent scores artifacts only (a baseline is running now); it re-scores after Wednesday and Thursday. I
   report its numbers next to mine, and the lower one is the one I quote.
3. The held-out set is run once. Anything fixed afterwards is a development change.
4. Every number in the video and submission links to a committed file. No prize or placement probabilities in any public text.
5. If a gate fails I say so in the next message, with the artifact.

## 9. What I need from you, in order
1. Say "go" (or change anything above) so I start D1 tonight.
2. Names or channels for **at least 10 outside people** (classmates, friends who run or work for a shop or a campaign) and 2-3
   practitioners, by **Wed 28 noon**; tell them it takes 10 minutes and they bring their own banner.
3. Generate the **held-out set of 8 banners** from my spec (I will write it) by **Wed 28 noon**, and do not show me the images before
   I freeze the code; drop them in a folder and tell me the folder name.
4. Two deploys: candidate **Wed late**, final **Thu night** (the commands are in `docs/release_plan_2026-10-27.md`).
5. Spend: the pilot and the held-out run need about $1 in total; confirm you are fine with that inside your $5 and with raising the
   public cap for judging.
6. Optional: five hand-drawn sketches, which would let the sketch door stop being labelled a prototype.

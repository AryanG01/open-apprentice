# Submission checklist: Nebius × NVIDIA Global AI Hackathon

**Deadline: 30 Oct 2026, 10:00 PDT = 31 Oct 2026, 01:00 SGT.** The demo must stay free and reachable until judging ends
(15 Dec 2026). Rules: a runtime NVIDIA open model on Nebius, a public licensed repo with a setup README, a working
accessible demo, a public YouTube video under 3 minutes, the Devpost form.

Owner = the person who must do it (some steps need the owner's accounts or are outward-facing).

## 1. Code and repository
- [ ] **Secret scan before any push** (agent): no `.env`, keys, private manifests (`benchmarks/final/`), or the sealed set.
- [ ] **Push `master`** (owner approves; 58+ commits ahead of `origin`, nothing pushed since 21 Oct). Then CI green on
      GitHub (Python 3.12, lint, contracts, web build, engine, browser).
- [ ] LICENSE (MIT) present: yes. README setup steps re-run from a clean clone (agent).

## 2. Decide what the judges see (owner decides; agent recommends deploying)
- [ ] **Campaign lane in production?** Production (revision `open-apprentice-00027-jif`) predates Plans 9A-9E. Deploying
      means a new image, the canary routine in `docs/deploy.md`, and the e2e journey against the candidate URL.
      Environment: model mode as today; `CAMPAIGN_MODEL_PROCEDURES` unset (procedures off).
- [ ] If deployed: the full browser journey and the campaign journey pass against the public URL (agent).

## 3. Claims (agent drafts, owner approves)
- [ ] `docs/submission.md`: add a short Campaign paragraph with only measured claims (parity 16/16 on development
      fixtures; Nemotron roles 6/6 with a heuristic also 6/6; explanations 0/3 under the strict check; procedures off in
      production; no held-out result yet). Keep the honest A vs B results and the Ultra (evaluation) / Super (product)
      distinction.
- [ ] README "Live demo" section lists the Campaign tab only if it is deployed.
- [ ] One pass of every number in README and submission against its source file.

## 4. Video (owner records or approves; under 3:00, public on YouTube)
- [ ] Current cut: 2:37, draw.io lane (Remotion, `video/`). Either keep it, or add a ~20 s Campaign segment if the lane is
      deployed (labelled "development fixtures"). Any live Nemotron call shown must be real; the recorded tape stays
      labelled REPLAY.
- [ ] Upload as public; put the link in `docs/submission.md` and the Devpost form.

## 5. Keep the demo alive until 15 Dec (owner)
- [ ] Nebius credit stays above the $10 reserve (about $11.97 after 22 Oct, to confirm); top up if judging traffic
      appears. The server-wide demo cap and the replay fallback protect the rest.
- [ ] Raise the GCP budget alert from SGD 1 to about SGD 20 (console: Billing > Budgets & alerts); keep billing open.
- [ ] Note the rollback command for the deployed revision in `docs/HANDOFF.md`.

## 6. Devpost (owner)
- [ ] Track: Best Apps and Agents. Demo URL, repo URL, video URL, text from `docs/submission.md`, built-with list.
- [ ] Submit before 31 Oct 01:00 SGT; leave a day of margin.

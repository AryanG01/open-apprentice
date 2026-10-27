# Submission checklist: Nebius × NVIDIA Global AI Hackathon

**Deadline: 30 Oct 2026, 10:00 PDT = 31 Oct 2026, 01:00 SGT.** The demo must stay free and reachable until judging ends
(15 Dec 2026). Rules: a runtime NVIDIA open model on Nebius, a public licensed repo with a setup README, a working
accessible demo, a public YouTube video under 3 minutes, the Devpost form.

Owner = the person who must do it (some steps need the owner's accounts or are outward-facing).

## 1. Code and repository
- [x] **Secret scan before any push** (agent): no `.env`, keys, private manifests (`benchmarks/final/`), or the sealed set.
- [x] **Push `master`** (owner approves; 58+ commits ahead of `origin`, nothing pushed since 21 Oct). Then CI green on
      GitHub (Python 3.12, lint, contracts, web build, engine, browser).
- [x] LICENSE (MIT) present: yes. README setup steps re-run from a clean clone (22 Oct, HEAD 7078517: all pass; `.python-version` added so uv picks 3.12 on any machine).

## 2. Decide what the judges see (owner decides; agent recommends deploying)
- [x] **Campaign lane in production?** Yes: revision `open-apprentice-00048-wuq` (25 Oct, image `prod-dc3f884`; `00046-wuc` before it: Adapt-a-banner landing with vision reads, optional price/button/small print; rollback `00043-voj`); `00043-voj` (24 Oct, the revision the video was captured on: show-the-work panels, Campaign reading question; `00038-naj` 23 Oct: durable $3 cap, role and explanation checker fixes; `00036-poz`, `00032-dux` and `00034-xuj` earlier that day, `00030-vel` on 22 Oct). Before it, `00027-jif` predated Plans 9A-9E. Deploying
      means a new image, the canary routine in `docs/deploy.md`, and the e2e journey against the candidate URL.
      Environment: model mode as today; `CAMPAIGN_MODEL_PROCEDURES` unset (procedures off).
- [x] If deployed: the full browser journey and the campaign journey pass against the public URL (agent).

## 3. Claims (agent drafts, owner approves)
- [x] `docs/submission.md`: add a short Campaign paragraph with only measured claims (parity 16/16 on development
      fixtures; Nemotron roles 6/6 with a heuristic also 6/6; explanations 0/3 under the strict check; procedures off in
      production; no held-out result yet). Keep the honest A vs B results and the Ultra (evaluation) / Super (product)
      distinction.
- [x] README "Live demo" section lists the Campaign tab only if it is deployed.
- [x] One pass of every number in README and submission against its source file.

## 4. Video (owner records or approves; under 3:00, public on YouTube)
- [x] **Current video: honest two-door cut v2, 1:52 (26 Oct, recorded live on candidate 00053-zat (production is now 00056-roj, same UI plus accessibility fixes); the banner flow first, then the sketch and page flow with its generated sample sketch said to be generated; re-record with a real hand-drawn sketch when the owner sends one; `video/out/open_apprentice_demo.mp4`; upload this one).** Earlier: banner-led cut, 1:42 (25 Oct, recorded live on production 00048-wuq, `video/out/open_apprentice_demo.mp4`; upload this one). Earlier: cut rebuilt around the Campaign lane (23 Oct, 2:55, `video/out/open_apprentice_demo.mp4`; captured on the public
      demo, live Nemotron role proposal; draw.io appears as one beat). Re-render: `node video/capture/campaign.mjs`,
      `video/.venv/bin/python video/tools/encode.py`, `video/.venv/bin/python video/tools/tts.py`, `npm run render` in `video/`.
- [ ] Upload as public; put the link in `docs/submission.md` and the Devpost form.

## 5. Keep the demo alive until 15 Dec (owner)
- [ ] Nebius credit stays above the $10 reserve ($12.26 owner-reported on 22 Oct); top up if judging traffic
      appears. The server-wide demo cap and the replay fallback protect the rest.
- [x] Raise the GCP budget alert from SGD 1 to about SGD 20 (console: Billing > Budgets & alerts); keep billing open.
- [x] Note the rollback command for the deployed revision in `docs/HANDOFF.md`.

## 6. Devpost (owner)
- [ ] Track: Best Apps and Agents. Demo URL, repo URL, video URL, text from `docs/submission.md`, built-with list.
- [ ] Submit before 31 Oct 01:00 SGT; leave a day of margin.

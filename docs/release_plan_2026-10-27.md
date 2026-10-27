# Release, spend and judge-access plan (prepared 27 Oct 2026; nothing here has been executed)

## Spend path and concurrency (read from the code, not tested under load)
- Campaign model calls (reading, question wording, facts, copy) pass `_require_model_budget` (`api/teach.py`) **before** the call
  and are accounted **after** it. The code comments the gap: "checked per request, not reserved atomically; concurrent first
  requests can overshoot by about one session" (`ponytail:` at `RESERVE_USD`). Concretely: a request is allowed if
  `spend + RESERVE_USD (about $0.48) <= DEMO_MODEL_MAX_USD`, so the overshoot is bounded by the number of requests in flight times
  their real cost (about $0.003 to $0.01 each), not by the reserve. The durable GCS ledger is shared by all instances.
- Per-address limits (rightmost `X-Forwarded-For`): 10 vision reads/hour, 6 page reads/hour, 6 model sessions/hour, 3 pages per
  workspace. Cloud Run: concurrency 20, max instances 1 to 3. There is no unlimited paid endpoint, and none was added.
- I did **not** load-test concurrent paid calls, and the stronger atomic reservation used elsewhere is **not** wired into this
  lane. Do not describe this lane's cap as a hard guarantee; describe it as "a durable cap checked before each call, with a small
  documented overshoot".
- Fresh-set run spend: about $0.0147 (4 reads + 3 wordings), well inside the owner's $5 total (earlier tally about $0.6 to $0.8;
  the Nebius dashboard is authoritative).

## Judge access (decisions for the owner)
1. Read the live ledger and balance: `curl -s <service>/health/ready` shows `spend_usd` and `cap_usd` (reported earlier: cap $3,
   about $1.23 used, so about $1.77 left). Check the Nebius dashboard balance too.
2. The cap is what keeps the demo up until 15 Dec: ordinary traffic can consume it. Options: (a) leave $3 and accept that heavy
   judging could exhaust it, after which the app falls back to the manual editor and the recorded replay (it says so); (b) raise
   `DEMO_MODEL_MAX_USD` to a number you are willing to lose, keeping a reserve outside it. Each real banner costs about
   $0.004 to $0.015, so $1 is roughly 70 to 250 banners, but the per-address quotas above still apply.
3. A judge who lands on an exhausted cap still sees a working manual flow; keep that wording honest in the README.

## What the owner runs (the agent cannot: the auto-mode classifier blocks gcloud deploy and update-traffic)
Replace `<sha>` with the final commit, `<rev>` with the new revision. Verify first: `git log -1 --oneline` equals the commit you intend.
```
gcloud builds submit --config deploy/cloudbuild.tagged.yaml --project oa-demo-1013-19737 --region us-central1 --substitutions=_TAG=prod-<sha> .
gcloud run deploy open-apprentice --project oa-demo-1013-19737 --region us-central1 --image us-central1-docker.pkg.dev/oa-demo-1013-19737/oa/demo:prod-<sha> --no-traffic --tag next
curl -s https://next---<service-host>/health/ready        # engine true, model can_start true
# smoke on the tag URL: Adapt a sample banner; the German sample asks; one live read; then
gcloud run services update-traffic open-apprentice --project oa-demo-1013-19737 --region us-central1 --to-revisions <rev>=100
# rollback, instant, data untouched
gcloud run services update-traffic open-apprentice --project oa-demo-1013-19737 --region us-central1 --to-revisions open-apprentice-00056-roj=100
```
(Use the same flags and secrets your earlier deploys used; the commands above only show the shape. Check `deploy/cloudbuild.tagged.yaml`
for the substitution name.) Rollback chain so far: 00056-roj (prod-cd9f35d), 00053-zat, 00048-wuq, 00046-wuc.

## Before release
- Full suite, browser suite and `lint-imports` (see `docs/final_sprint_audit.md` for the latest run).
- The existing MP4 still contains the old narration (the absent-name rejection and the pre-fix checks); the script file is
  corrected, the rendered video is not. Do not upload `video/out/open_apprentice_demo.mp4` as is.
- Owner steps: manual comparator timing (`evaluator_only/manual_timing_template.csv`), a listening pass on the final video, the
  spending decision above, push and deploy.

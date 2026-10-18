# Production cutover proposal (awaiting the owner's approval; nothing here has been run)

**Purpose.** The public service `open-apprentice` still runs the older badge build (`demo:latest`, 2026-10-13). Judges open
that URL. This replaces it with the product (teach → clarify → correct → reuse on real `.drawio` files), with durable
state, a durable spend cap, and a one-command rollback. Project `oa-demo-1013-19737`, region `us-central1`.

## What changes for visitors

- The Apprentice screen becomes the product; the badge demo stays under "Earlier prototype". **"Try a sample" buttons**
  (three owner-authored diagrams, `docs/corpus/drawio_provenance.md`) let a visitor start without a `.drawio` file.
- Sessions, skills and versions live in a Cloud Storage bucket, so they survive restarts and a second instance.
- Long steps run through Cloud Tasks with an authenticated callback (verified on staging, `docs/staging_results.md`).
- Live Nemotron on Nebius Token Factory stays the default (hackathon requirement), under a **durable** cap. The cap that
  leaked about $4 before was an in-memory counter that reset on every cold start; the new one is the storage-backed ledger
  (`Ledger(store, cap)`, compare-and-set), shared by every instance and surviving restarts.

## Resources to create (new, separate from staging)

| Resource | Name | Settings |
|---|---|---|
| Bucket | `oa-prod-<6 random chars>` | Standard, uniform access, public access prevention, **no** expiry (skills and sessions are kept); versioning on |
| Queue | `oa-prod` | 2 dispatches/s, 4 concurrent, 3 attempts |
| Service account | `oa-prod@oa-demo-1013-19737.iam.gserviceaccount.com` | `objectAdmin` on the prod bucket only; `run.invoker` on the service; `secretmanager.secretAccessor` on `nebius-api-key` only; `cloudtasks.enqueuer` on the queue; `serviceAccountUser` on itself (OIDC tokens) |

The existing service, its secret and its budget alert are reused. The old revision stays available for rollback.

## Sequence (every step is reversible until traffic moves)

1. **Build** the image from master at a pinned commit under a tag that does not touch `latest`
   (`deploy/cloudbuild.yaml` hard-codes `:latest`; use a one-off substitution or a tagged copy, as the staging build did).
   Cloud Run revisions pin an image digest, so pushing a tag never changes what is running.
2. **Create the resources** above (commands mirror `docs/deploy_staging_proposal.md`, with the names above).
3. **Run the integration job once** against the new image and bucket (`oa staging-check`, mock provider): render, lost race,
   restart survival, authenticated Tasks dispatch.
4. **Deploy as a no-traffic candidate** on the production service:
   `gcloud run deploy open-apprentice --image …:prod-<sha> --no-traffic --tag candidate --service-account oa-prod@… --max-instances 3 --update-env-vars OA_STORE=gcs,OA_BUCKET=<bucket>,OA_DISPATCH=cloudtasks,OA_TASKS_QUEUE=…,OA_TASKS_SERVICE_URL=<service url>,OA_TASKS_SERVICE_ACCOUNT=oa-prod@…,DEMO_MODEL_MAX_USD=<cap>`
   (the Nebius key and model variables are already on the service; only the new variables are added).
   Public traffic is still on the old revision.
5. **Smoke-test the candidate URL** (the `candidate---` tag URL) from a browser: import a sample, teach, answer, commit, apply,
   download, correct, then once with the live model. Check `/health/ready`, and that restarting the revision keeps the skill.
6. **Move traffic:** `gcloud run services update-traffic open-apprentice --to-latest`. Watch logs and the ledger for an hour.
7. **Rollback, one command, instant:** `gcloud run services update-traffic open-apprentice --to-revisions <old-revision>=100`
   (the old revision name is recorded before step 6). Data in the bucket is not touched by a rollback.

## Settings and limits

- `--min-instances 0` (free tier; first request after idle takes about 16 s, measured on staging) or `--min-instances 1` for
  the judging window (about US$0.10 per hour for 1 vCPU and 1 GiB; owner's call). `--max-instances 3`, `--concurrency 20`,
  1 vCPU, 2 GiB.
- Live cap `DEMO_MODEL_MAX_USD`: measured cost is about $0.09–$0.28 per full story, so **$5 covers 20–50 stories**. The
  protected $10 reserve in `results/redesign/budget.json` exists for exactly this demo; the funded run's end balance decides
  the cap, and the cap should never exceed it. When it is reached the UI offers the labelled recording, never a silent downgrade.
- Per-client live sessions: 3 per hour per instance (in-process; with 3 instances up to 9). The durable cap is the real guard.
- `FORWARDED_ALLOW_IPS`: set it to Cloud Run's proxy range, never `*` (`docs/deploy.md`, "Behind a proxy").

## Cost

Bucket and Tasks: effectively $0 (a few MB; first million Tasks operations free). Cloud Run: scales to zero under the free
tier, plus about $0.10/hour only if min-instances 1 is chosen for the judging window. Nebius: bounded by the cap. The SGD 1
budget alert on the project emails but does not stop spending; it should be raised to about SGD 20 for the judging window so
it does not fire on legitimate use.

## What it does not prove

Behaviour under many simultaneous visitors, and cold-start latency of the full product under a real network (staging
measured 16 s for the first Tasks dispatch). Both are checked once in step 5.

## Decisions for the owner

1. Approve the cutover (steps 1–7) in this project, with rollback as above?
2. Live model default on, with what cap (recommended: $5, never above the balance left after the funded run)?
3. `--min-instances 1` for the judging window (about $0.10/hour), or accept a 16 s first load?
4. Raise the budget alert to about SGD 20 for the window?

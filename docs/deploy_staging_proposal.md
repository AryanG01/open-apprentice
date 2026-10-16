# Staging proposal (NOT created — needs the owner's approval)

**Purpose (spec §10, early staging integration).** Prove the deployed environment before the product depends on it. Each check
is one `oa staging-check` invocation run inside the staging image (Cloud Run job below), printing one JSON line per check:
1. **Render and measure** one supported draw.io diagram with the pinned viewer and the bundled font in Cloud Run's Chromium:
   `oa staging-check --file samples/drawio/d1.drawio --only render`; the job's command starts the engine first
   (`sh -c 'node services/engine/src/server.js & sleep 5; oa staging-check …'`, `ENGINE_URL=http://127.0.0.1:8090`).
2. **GCS conditional update with a deliberately lost race:** `OA_STORE=gcs oa staging-check --only race`
   (two writers on one generation; pass = exactly one winner and one precondition failure).
3. **Restart survival:** `oa staging-check --only survival --phase write`, then force a new revision
   (`gcloud run jobs update … --update-env-vars OA_RESTART=<n>`), then `--only survival --phase read` (commands below).

4. **Authenticated Cloud Tasks dispatch:** with the service in Cloud Tasks mode, `oa staging-check --only tasks` (run as the job
   below, same env) enqueues a `ping` job; Cloud Tasks delivers it to `POST /internal/tasks/{id}` on the staging service with an
   OIDC token for `oa-staging-worker`; the route verifies audience and service account, runs the job, and the check sees the
   `staging/ping-…` object appear in the bucket (≤ 60 s). A request without that token is refused with 403 (unit-tested; checked
   once by hand with `curl` against the staging URL).

## Resources (project `oa-demo-1013-19737`, region `us-central1`)

| Resource | Name | Settings |
|---|---|---|
| Cloud Storage bucket | `oa-staging-<6 random chars>` | Standard class, uniform bucket-level access, public access prevention on, lifecycle: delete objects older than 7 days |
| Cloud Tasks queue | `oa-staging` | max dispatches 1/s, max concurrent 2, max attempts 3 |
| Service account | `oa-staging-worker@oa-demo-1013-19737.iam.gserviceaccount.com` | `roles/storage.objectAdmin` on the bucket only; `roles/run.invoker` on the staging service only |
| Cloud Run job | `oa-staging-check` | same image, command starts the engine then runs `oa staging-check`, 1 GiB, service account `oa-staging-worker`, env `OA_STORE=gcs`, `OA_BUCKET=<bucket>`, `PROVIDER_MODE=mock`; max retries 0 |
| Cloud Run service | `open-apprentice-staging` | same image as production, `--min-instances 0 --max-instances 1 --memory 1Gi`, NOT public (`--no-allow-unauthenticated`), env `OA_STORE=gcs`, `OA_BUCKET=<bucket>`, `PROVIDER_MODE=mock` |

The production service `open-apprentice` is not touched.

## Commands (run only after approval)

```bash
P=oa-demo-1013-19737; R=us-central1; B=oa-staging-$(openssl rand -hex 3)
gcloud services enable cloudtasks.googleapis.com --project $P
gcloud storage buckets create gs://$B --project $P --location $R --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://$B --lifecycle-file=<(printf '{"rule":[{"action":{"type":"Delete"},"condition":{"age":7}}]}')
gcloud iam service-accounts create oa-staging-worker --project $P --display-name "Open Apprentice staging worker"
gcloud storage buckets add-iam-policy-binding gs://$B --member serviceAccount:oa-staging-worker@$P.iam.gserviceaccount.com --role roles/storage.objectAdmin
gcloud tasks queues create oa-staging --project $P --location $R --max-dispatches-per-second 1 --max-concurrent-dispatches 2 --max-attempts 3
gcloud run deploy open-apprentice-staging --project $P --region $R --image us-central1-docker.pkg.dev/$P/oa/demo:latest \
  --service-account oa-staging-worker@$P.iam.gserviceaccount.com --min-instances 0 --max-instances 1 --memory 1Gi \
  --no-allow-unauthenticated --set-env-vars OA_STORE=gcs,OA_BUCKET=$B,PROVIDER_MODE=mock
URL=$(gcloud run services describe open-apprentice-staging --project $P --region $R --format 'value(status.url)')
SA=oa-staging-worker@$P.iam.gserviceaccount.com
TASKS="OA_DISPATCH=cloudtasks,OA_TASKS_QUEUE=projects/$P/locations/$R/queues/oa-staging,OA_TASKS_SERVICE_URL=$URL,OA_TASKS_SERVICE_ACCOUNT=$SA"
gcloud run services update open-apprentice-staging --project $P --region $R --update-env-vars "$TASKS"
gcloud tasks queues add-iam-policy-binding oa-staging --project $P --location $R --member serviceAccount:$SA --role roles/cloudtasks.enqueuer
gcloud iam service-accounts add-iam-policy-binding $SA --project $P --member serviceAccount:$SA --role roles/iam.serviceAccountUser  # mint OIDC tokens for itself
gcloud run jobs create oa-staging-check --project $P --region $R --image us-central1-docker.pkg.dev/$P/oa/demo:latest \
  --service-account oa-staging-worker@$P.iam.gserviceaccount.com --max-retries 0 --memory 1Gi --command sh \
  --args=-c,'node services/engine/src/server.js & sleep 5; exec oa staging-check --file samples/drawio/d1.drawio' \
  --set-env-vars OA_STORE=gcs,OA_BUCKET=$B,PROVIDER_MODE=mock,ENGINE_URL=http://127.0.0.1:8090
gcloud run jobs update oa-staging-check --project $P --region $R --update-env-vars "$TASKS"
gcloud run jobs execute oa-staging-check --project $P --region $R --wait   # race + survival(write) + tasks + render
# then force a new revision and read the marker back:
gcloud run jobs update oa-staging-check --project $P --region $R --update-env-vars OA_RESTART=1 \
  --args=-c,'exec oa staging-check --only survival --phase read'
gcloud run jobs execute oa-staging-check --project $P --region $R --wait
gcloud run services add-iam-policy-binding open-apprentice-staging --project $P --region $R \
  --member serviceAccount:oa-staging-worker@$P.iam.gserviceaccount.com --role roles/run.invoker
```

## Teardown

```bash
gcloud run jobs delete oa-staging-check --project $P --region $R --quiet
gcloud run services delete open-apprentice-staging --project $P --region $R --quiet
gcloud tasks queues delete oa-staging --project $P --location $R --quiet
gcloud storage rm -r gs://$B
gcloud iam service-accounts delete oa-staging-worker@$P.iam.gserviceaccount.com --project $P --quiet
```

## Cost estimate (to be confirmed in the console after a week)
- Cloud Storage: a few MB for 7 days, effectively $0 (Standard storage in us-central1 is billed per GB-month).
- Cloud Tasks: the first million operations per month are free; the test uses a handful.
- Cloud Run job: billed per execution second; each check runs for well under a minute.
- Cloud Run: scales to zero; the integration test runs for minutes; covered by the free tier already used by production.
- Expected total: well under SGD 1 for the week. The existing SGD 1 budget alert on the project emails but does not stop spending.

## What it does not prove
Production load, cold-start latency of the full demo (measured at release, Plan 6), or any live-model behaviour (the staging run uses
`PROVIDER_MODE=mock`; no Nebius calls).

# Staging proposal (NOT created — needs the owner's approval)

**Purpose (spec §10, early staging integration, 17–20 Oct).** Prove the deployed environment before the product depends on it:
1. render and measure one supported draw.io diagram with the pinned viewer and the bundled font in Cloud Run's Chromium;
2. one real GCS conditional update, including a deliberately lost race (two writers, one precondition failure);
3. one authenticated Cloud Tasks dispatch to a worker endpoint, with a scripted provider (no paid model call);
4. restart the service and verify that a session, a skill version and the ledger survive.

## Resources (project `oa-demo-1013-19737`, region `us-central1`)

| Resource | Name | Settings |
|---|---|---|
| Cloud Storage bucket | `oa-staging-<6 random chars>` | Standard class, uniform bucket-level access, public access prevention on, lifecycle: delete objects older than 7 days |
| Cloud Tasks queue | `oa-staging` | max dispatches 1/s, max concurrent 2, max attempts 3 |
| Service account | `oa-staging-worker@oa-demo-1013-19737.iam.gserviceaccount.com` | `roles/storage.objectAdmin` on the bucket only; `roles/run.invoker` on the staging service only |
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
gcloud run services add-iam-policy-binding open-apprentice-staging --project $P --region $R \
  --member serviceAccount:oa-staging-worker@$P.iam.gserviceaccount.com --role roles/run.invoker
```

## Teardown

```bash
gcloud run services delete open-apprentice-staging --project $P --region $R --quiet
gcloud tasks queues delete oa-staging --project $P --location $R --quiet
gcloud storage rm -r gs://$B
gcloud iam service-accounts delete oa-staging-worker@$P.iam.gserviceaccount.com --project $P --quiet
```

## Cost estimate (to be confirmed in the console after a week)
- Cloud Storage: a few MB for 7 days, effectively $0 (Standard storage in us-central1 is billed per GB-month).
- Cloud Tasks: the first million operations per month are free; the test uses a handful.
- Cloud Run: scales to zero; the integration test runs for minutes; covered by the free tier already used by production.
- Expected total: well under SGD 1 for the week. The existing SGD 1 budget alert on the project emails but does not stop spending.

## What it does not prove
Production load, cold-start latency of the full demo (measured at release, Plan 6), or any live-model behaviour (the staging run uses
`PROVIDER_MODE=mock`; no Nebius calls).

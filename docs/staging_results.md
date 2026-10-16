# Staging integration results (spec 10)

Run on 2026-10-16 (09:10–09:31 UTC) with the owner's approval, project `oa-demo-1013-19737`, region `us-central1`, following
`docs/deploy_staging_proposal.md`. Image `us-central1-docker.pkg.dev/oa-demo-1013-19737/oa/demo:staging-2613786` (Cloud Build,
3 min 31 s; built from master at `2613786` plus the `.gcloudignore` fix `55b9942`). Production (`open-apprentice`, `demo:latest`) was not touched.

| Resource | Name |
|---|---|
| Bucket | `oa-staging-1f7298` (uniform access, public access prevention, delete after 7 days) |
| Queue | `oa-staging` |
| Service account | `oa-staging-worker@oa-demo-1013-19737.iam.gserviceaccount.com` |
| Service | `open-apprentice-staging` (private, max 1 instance, 1 GiB, `PROVIDER_MODE=mock`, `OA_DISPATCH=cloudtasks`) |
| Job | `oa-staging-check` |

| Check | Result | Evidence (job log) |
|---|---|---|
| Render and measure `samples/drawio/d1.drawio` in Cloud Run's Chromium with the bundled font | **pass** | 5 movable labels, 5 fixed nodes, none missing, none demoted |
| GCS conditional update with a deliberately lost race | **pass** | `{"winners": 1, "precondition_failures": 1}` |
| Authenticated Cloud Tasks dispatch to `POST /internal/tasks/{id}` (OIDC token for the worker service account) | **pass** | ping object written; 16.1 s cold, 0.8 s warm |
| Restart survival (marker written, new job revision, marker read) | **pass** | `phase write ok`, then `phase read ok` after `OA_RESTART=1` |
| A forged call is refused by the app | **pass** | owner's identity token (has invoker): app answered 403, nothing ran; no token: 403 |

Findings while running:
1. **`.gcloudignore` excluded `tests/`** although the demo image copies `tests/fixtures/drawio_corpus/dev` (since Plan 3): every Cloud Build
   would have failed. Fixed in `55b9942`.
2. **The engine inside the job listened on 8000**, because the image sets `PORT=8000` for the API; the job command now starts it with
   `PORT=8090 HOST=127.0.0.1`. The proposal is updated.
3. With the owner's identity token the app reported "missing token" (not "invalid token"): Cloud Run did not forward that user
   token's `Authorization` header to the app, while Cloud Tasks' OIDC tokens are forwarded (the dispatch check passed). The
   refusal is the intended outcome either way; the reason is recorded as observed, not explained.

Not proven here: production load, cold start of the full demo, live-model behaviour (no Nebius call was made; `PROVIDER_MODE=mock`).
The resources stay up for later staging runs (they scale to zero; bucket objects expire after 7 days). Teardown commands are in the proposal.

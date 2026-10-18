# Deployment runbook

Two artifacts. Neither needs a database.

## 1. Static recorded build (insurance link; no backend, no cost)
`npm ci && npm run build:web`, then publish `apps/web/dist` to any static host. It serves Home, the recorded walkthrough and Compare.
**Try it live** shows a clear "needs the backend" message there. (Vercel: `vercel login`, then `vercel deploy apps/web/dist --prod`.)

## 2. Live demo container (API + web + engine with Chromium)
```
docker build -f docker/demo.Dockerfile -t open-apprentice-demo .
docker run --rm -p 8000:8000 open-apprentice-demo                                   # reference mode: no model, no credentials
docker run --rm -p 8000:8000 --env-file .env -e DEMO_MODEL_ENABLED=1 -e DEMO_MODEL_MAX_USD=1.5 open-apprentice-demo   # adds Nemotron mode
```
Open `http://<host>:8000`. Health: `/health/ready` reports engine and model availability and spend (never keys).

### Safety defaults
- **Public configuration: live Nemotron on Nebius Token Factory** (`DEMO_MODEL_ENABLED=1`, the hackathon requires running on Token Factory with an NVIDIA open model). The model path is **off** unless `DEMO_MODEL_ENABLED=1`; a global cap `DEMO_MODEL_MAX_USD` (default 1.5) refuses new model sessions instead of degrading silently, and the UI then offers the labelled recording. Measured cost: about $0.085 per full story (5 calls, 36k tokens), so $1.5 is about 17 stories; top up Nebius credit before judging and keep the cap at what you are willing to lose. The Nebius key goes in the host's secret store (Cloud Run: Secret Manager), never in the image or the repo.
- Per-client limits: 60 free and 60 replay sessions/hour, 3 live model sessions/hour. Per-session ceiling 120k tokens / 24 calls (a measured full session used 32k tokens / 3 calls).
- Security headers (CSP same-origin, no framing, no sniffing). No cookies, no accounts, no uploads except a user-chosen JSON file that is only parsed.
- The engine child runs with a minimal environment (no API keys); the evaluator token is random per process and never leaves the server.

### Known limits (state them if asked)
- Sessions live in server memory (lost on restart); one process only. The engine allows 4 concurrent browser sessions; long actions queue.
- Rate limiting is in-process by client address; put a proxy limit in front of a public host.
- `docker compose` (db/worker/web) is not the demo path: the worker command is not implemented. Use the container above.

## 3. Hugging Face Space
**Cost correction (2026-10-12):** creating a Docker Space on free CPU Basic returned `402 Payment Required` (it now needs a PRO subscription, about $9/month); only **static** Spaces are free. The steps below are
correct for a PRO account (2 vCPU, 16 GB RAM; sleeps after 48 h idle) but were not run to completion. **Free static copy (deployed 2026-10-12):** `https://huggingface.co/spaces/AryanG01/open-apprentice-static`
(built from `apps/web/dist` plus a Space README with `sdk: static`; Home, Compare and the walkthrough work, "Try it live" shows that it needs the backend). Measured memory for the full app, one session on macOS: ~384 MB idle,
~585 MB peak (Node engine ~186 MB, Python ~110 MB, Chromium ~280 MB), (macOS figure, overstated: see the Linux measurements below, where 512 MiB is enough).
**Linux container measurements (2026-10-12, Docker Desktop, image `docker/demo.Dockerfile`, 2.47 GB on disk, `docker stats`, sampled about every 2 s):** unlimited: ~205 MiB idle, peak 335 MiB across a replay flow, a reference flow and three parallel replay flows (all passed).
Hard limits, replay flow (teach, 2 answers, Konva, Fabric, tool change) then reference flow: **512 MiB + 1 CPU: 3/3 and 5/5 passed, no OOM, ~290 MiB used**; 0.5 CPU: replay flow 5 s, 3/3; 0.25 CPU: 13 s, 3/3, start 4 s;
**0.1 CPU: start took 18 s and the session ended UNRESOLVED (`solver status=incomplete`), because the symbolic search runs against a wall-clock budget**, so outcomes depend on CPU speed. Memory is therefore NOT the constraint (512 MiB is enough for one visitor at a time);
CPU is: plan for at least 0.5 vCPU, 1 vCPU preferred. **Update (same day): after decisions #51 the solver budget is deterministic, so 0.1 vCPU no longer changes the answer (INTENT_READY, same rule, about 50 s per flow instead of about 2 s); a 0.1-CPU host is slow but correct.** Free tiers that give 0.1 CPU (Render, Koyeb) are too slow. Not measured: many simultaneous visitors, the Nemotron live mode under load, an ARM or Cloud Run runtime.
Front-matter gotchas: `short_description` must be at most 60 characters and must not contain a colon.
`scripts/make_hf_space.sh dist/hf-space` builds a push-ready folder (no `.env`, no secrets; Dockerfile for UID 1000 on port 7860; README with the Space front matter). It was built and run locally exactly as
the Space would (port 7860, UID 1000): layout flow and the SVG lane both pass. Then, with your own Hugging Face login:
```
hf auth login                                   # write-scope token, entered by you in the terminal prompt, never pasted into chat
hf repo create <you>/open-apprentice --repo-type space --space_sdk docker
cd dist/hf-space && git init && git remote add space https://huggingface.co/spaces/<you>/open-apprentice
git add -A && git commit -m "deploy" && git push space HEAD:main
```
Reference mode needs nothing else. To enable Nemotron mode (optional, capped), add in Space Settings: **Secret** `NEBIUS_API_KEY`; **Variables** `PROVIDER_MODE=nebius`, `LIVE_RUN_MAX_USD=2`,
`NEBIUS_MODEL=nvidia/Nemotron-3-Ultra-550b-a55b`, `NEBIUS_REASONING_EFFORT=low`, `NEBIUS_COMPLETION_CAP=32000`, `INPUT_USD_PER_MILLION=1`, `OUTPUT_USD_PER_MILLION=3`, `DEMO_MODEL_ENABLED=1`, `DEMO_MODEL_MAX_USD=1.5`.
Cost: host $0; reference mode $0; Nemotron mode is bounded by `DEMO_MODEL_MAX_USD` (measured $0.09-0.28 per full session). Unverified until the first real build: Space build memory limits and Chromium behaviour on Hugging Face's runtime. The static Vercel build remains the fallback link.

## Behind a proxy (Cloud Run, a load balancer)
- Per-visitor rate limits key on the rightmost `X-Forwarded-For` entry (the address Cloud Run's front end appended, which a visitor cannot choose), not on `FORWARDED_ALLOW_IPS`; the limiter is in memory per instance, so the global spend cap (`DEMO_MODEL_MAX_USD`) is the real protection.
- Teaching sessions live in memory: run a single instance (`--max-instances=1` on Cloud Run) or requests for a session can land on another instance and 404.
- Memory: measured ~335 MiB peak for one visitor (section 3); allow 1-2 GiB for several. CPU: no longer changes results (decisions #51) but sets speed; 1 vCPU recommended.

## 4. Google Cloud Run (deployed 2026-10-13; this is the live public demo)
- **URL:** https://open-apprentice-664860383135.us-central1.run.app  (project `oa-demo-1013-19737`, region `us-central1`, service `open-apprentice`; billing account `019589-14D134-77B39F`, currency SGD).
- **What runs:** `docker/demo.Dockerfile` built by Cloud Build (`gcloud builds submit --config deploy/cloudbuild.yaml --project oa-demo-1013-19737 --region us-central1 .`; the upload is limited by `.gcloudignore` to 159 files, no `.env`, no local virtualenvs) and pushed to Artifact Registry `us-central1-docker.pkg.dev/oa-demo-1013-19737/oa/demo`.
- **Settings:** 1 vCPU, 2 GiB, `--min-instances=0 --max-instances=1 --concurrency=20 --timeout=300`, second-generation execution environment, public (`--allow-unauthenticated`). One instance only because teaching sessions live in memory. Live Nemotron on Nebius Token Factory is ON (`DEMO_MODEL_ENABLED=1`, `DEMO_MODEL_MAX_USD=1.0`); the model and rates come from non-secret env vars, and the API key comes from **Secret Manager** (`nebius-api-key`, readable only by the Cloud Run service account), never from the image or the repo.
- **Deploy command (secret and env values stay out of it):** `gcloud run deploy open-apprentice --project oa-demo-1013-19737 --region us-central1 --image us-central1-docker.pkg.dev/oa-demo-1013-19737/oa/demo:latest --port 8000 --cpu 1 --memory 2Gi --min-instances 0 --max-instances 1 --concurrency 20 --timeout 300 --execution-environment gen2 --env-vars-file <yaml of the non-secret variables> --set-secrets NEBIUS_API_KEY=nebius-api-key:latest --allow-unauthenticated`.
- **Cost guard:** a budget alert of **SGD 1** (about US$0.75) with notifications at 50% and 100% on this project only. It emails; it does NOT stop spending. Cloud Run's free tier (2M requests, 180,000 vCPU-seconds, 360,000 GiB-seconds per month per billing account, applied at Tier 1 prices) covers about 2,000 live stories by a rough sizing (one story is about 90 s of request time); asia-southeast1's tier was not confirmed, so us-central1 (Tier 1) is used.
- **Known weakness:** the app's global dollar cap (`DEMO_MODEL_MAX_USD`) lives in MEMORY and resets whenever the instance restarts or scales from zero, so each cold start grants a fresh cap. The real protection is the finite Nebius balance (when it runs out, calls fail and the UI offers the labelled recording). A durable counter (for example in Cloud Storage) has not been built.
- **Verified on the live URL:** `/health/ready` reports engine up, model available, replay tape installed; the reference flow (teach, Konva, Fabric, tool change, repair, re-run) passes in 1 to 3 s per step; a full live Nemotron flow on Token Factory ran (3 model calls, 25k tokens, about $0.068 at the configured rates, all verifier checks passed; the tool change did not break the model's procedure, so no repair was needed); in a real browser the default learner is live Nemotron, the live-story button is present and the reference story completes in 40 s with no console errors.
- **Teardown:** `gcloud run services delete open-apprentice --region us-central1 --project oa-demo-1013-19737` and `gcloud projects delete oa-demo-1013-19737` (deleting the project removes the secret, the registry and the budget filter target).


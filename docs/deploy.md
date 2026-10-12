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
- Model mode is **off** unless `DEMO_MODEL_ENABLED=1`; a global cap `DEMO_MODEL_MAX_USD` (default 1.5) refuses new model sessions instead of degrading silently.
- Per-client limits: 60 free and 60 replay sessions/hour, 3 live model sessions/hour. Per-session ceiling 120k tokens / 24 calls (a measured full session used 32k tokens / 3 calls).
- Security headers (CSP same-origin, no framing, no sniffing). No cookies, no accounts, no uploads except a user-chosen JSON file that is only parsed.
- The engine child runs with a minimal environment (no API keys); the evaluator token is random per process and never leaves the server.

### Known limits (state them if asked)
- Sessions live in server memory (lost on restart); one process only. The engine allows 4 concurrent browser sessions; long actions queue.
- Rate limiting is in-process by client address; put a proxy limit in front of a public host.
- `docker compose` (db/worker/web) is not the demo path: the worker command is not implemented. Use the container above.

## 3. Hugging Face Space (free CPU Basic: 2 vCPU, 16 GB RAM; sleeps after 48 h without visitors)
`scripts/make_hf_space.sh dist/hf-space` builds a push-ready folder (no `.env`, no secrets; Dockerfile for UID 1000 on port 7860; README with the Space front matter). It was built and run locally exactly as
the Space would (port 7860, UID 1000): layout flow and the SVG lane both pass. Then, with your own Hugging Face login:
```
hf auth login                                   # write-scope token, entered by you in the terminal prompt, never pasted into chat
hf repo create <you>/open-apprentice --type space --space_sdk docker
cd dist/hf-space && git init && git remote add space https://huggingface.co/spaces/<you>/open-apprentice
git add -A && git commit -m "deploy" && git push space HEAD:main
```
Reference mode needs nothing else. To enable Nemotron mode (optional, capped), add in Space Settings: **Secret** `NEBIUS_API_KEY`; **Variables** `PROVIDER_MODE=nebius`, `LIVE_RUN_MAX_USD=2`,
`NEBIUS_MODEL=nvidia/Nemotron-3-Ultra-550b-a55b`, `NEBIUS_REASONING_EFFORT=low`, `NEBIUS_COMPLETION_CAP=32000`, `INPUT_USD_PER_MILLION=1`, `OUTPUT_USD_PER_MILLION=3`, `DEMO_MODEL_ENABLED=1`, `DEMO_MODEL_MAX_USD=1.5`.
Cost: host $0; reference mode $0; Nemotron mode is bounded by `DEMO_MODEL_MAX_USD` (measured $0.09-0.28 per full session). Unverified until the first real build: Space build memory limits and Chromium behaviour on Hugging Face's runtime. The static Vercel build remains the fallback link.

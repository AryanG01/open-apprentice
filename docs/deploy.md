# Deployment runbook

Two artifacts. Neither needs a database.

## 1. Static recorded build (insurance link; no backend, no cost)
`npm ci && npm run build:web`, then publish `apps/web/dist` to any static host. It serves Home, the recorded walkthrough and Compare.
**Try it live** shows a clear "needs the backend" message there. (Vercel: `vercel login`, then `vercel deploy apps/web/dist --prod`.)

## 2. Live demo container (API + web + engine with Chromium)
```
docker build -f docker/demo.Dockerfile -t open-apprentice-demo .
docker run --rm -p 8000:8000 open-apprentice-demo                                   # reference mode: no model, no credentials
docker run --rm -p 8000:8000 --env-file .env -e DEMO_MODEL_ENABLED=1 -e DEMO_MODEL_MAX_USD=2 open-apprentice-demo   # adds Nemotron mode
```
Open `http://<host>:8000`. Health: `/health/ready` reports engine and model availability and spend (never keys).

### Safety defaults
- Model mode is **off** unless `DEMO_MODEL_ENABLED=1`; a global cap `DEMO_MODEL_MAX_USD` (default 2) refuses new model sessions instead of degrading silently.
- Per-client limits: 60 free sessions/hour, 8 model sessions/hour. Per-session ceiling 250k tokens / 40 calls.
- Security headers (CSP same-origin, no framing, no sniffing). No cookies, no accounts, no uploads except a user-chosen JSON file that is only parsed.
- The engine child runs with a minimal environment (no API keys); the evaluator token is random per process and never leaves the server.

### Known limits (state them if asked)
- Sessions live in server memory (lost on restart); one process only. The engine allows 4 concurrent browser sessions; long actions queue.
- Rate limiting is in-process by client address; put a proxy limit in front of a public host.
- `docker compose` (db/worker/web) is not the demo path: the worker command is not implemented. Use the container above.

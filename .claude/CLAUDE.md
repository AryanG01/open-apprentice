# What this project is
Open Apprentice: teach an agent a visual layout rule by demonstration; it finds a revealing test
case, asks a clarifying question when genuinely ambiguous, and reuses the rule through checked
procedures in two real graphics backends (Konva, then Fabric). Built for the Nebius x NVIDIA
Global AI Hackathon. Full spec: Open_Apprentice_Claude_Code_Build_Spec.md (v1.3) at repo root —
treat it as authoritative; this file is the short operational pointer to it.

# Stack
FastAPI + Pydantic 2 + SQLAlchemy 2 + PostgreSQL (API/worker), Python 3.12 via uv, React + TS +
Vite (apps/web), a Node/Playwright engine service driving real Konva/Fabric in a locked browser
(services/engine), z3-solver for bounded witness search, Docker Compose for local/deploy.

# Commands
- Offline bootstrap: `docker compose build && docker compose up -d` then `oa db upgrade`,
  `oa admin create --username owner`, `oa doctor` (see docs/status.md for exact tested commands).
- Test (Python): `uv run pytest tests/unit tests/integration tests/contracts tests/evaluation`
- Trust-boundary check: `uv run lint-imports`
- Test (web/engine): `npm test -w services/engine`; `npx playwright test`
- CLI entry point: `oa <command>` — see §24.5 of the spec for the full surface.

# Rules for this repo
- Agent-visible code (`src/open_apprentice/agent,concepts,skills,providers,environments`) must
  never import the evaluator (`evaluation/verifier.py`, `evaluation/episodes.py`) or anything
  under `benchmarks/final/`. Enforced by `uv run lint-imports` — do not weaken that contract.
- No `eval`/`exec`/dynamic code loading anywhere. Model-generated procedures run only through the
  restricted JSON-AST interpreter in `skills/interpreter.py` (§7.2).
- The independent verifier (`evaluation/verifier.py`) must never call the agent-facing
  `measure_node` tool or share geometry code with the engine's native tool implementation (§12.1).
- Four evidence axes (intent, symbolic, native, held-out) stay structurally separate — never
  collapse them into one confidence score or a single "Verified" badge (§7.5, §17.7).
- `PROVIDER_MODE=mock` is the default. Never claim a live Nemotron/Token Factory result without an
  actual `oa provider probe --live` run; a blocked live check is reported blocked, not passed.
- Never commit `.env`, real credentials, or private evaluator manifests (`benchmarks/final/`).
- Only owner-authored or provenance-verified design assets ship in the public demo — see
  docs/decisions.md for the Vector-Bench asset-exclusion list enforced for the v1.3 SVG lane.

# Gotchas
- This sandbox denies writes to any path literally named `.git` — `git init`/`git add -A` of a
  fresh `.git` dir must be run by the user directly (`! git init`), not by the agent.
- Host Node is 25.6.0 (not an LTS line); containers pin `node:22-slim` to match spec §3.4 — don't
  assume host `node --version` reflects what ships.
- Python project targets 3.12 via uv even though the host system Python is 3.13.5.

# Memory
claude-mem is injecting context from past sessions automatically.
For deeper history, query the "Claude Memory" NotebookLM notebook.

#!/usr/bin/env bash
# Build a ready-to-push Hugging Face Space folder from the current checkout (no credentials involved).
# Usage: scripts/make_hf_space.sh [outdir]   -> then:  cd outdir && git init && git remote add space https://huggingface.co/spaces/<user>/<name> && git add -A && git commit -m deploy && git push space HEAD:main
set -euo pipefail
OUT="${1:-dist/hf-space}"
rm -rf "$OUT" && mkdir -p "$OUT"
for p in src prompts configs services/engine apps/web pyproject.toml uv.lock package.json package-lock.json docs/capabilities.json LICENSE; do
  mkdir -p "$OUT/$(dirname "$p")"
  rsync -a --exclude node_modules --exclude dist --exclude __pycache__ --exclude '.venv' "$p" "$OUT/$(dirname "$p")/"
done
cp README.md "$OUT/PROJECT_README.md"                 # pyproject references README.md for the package metadata
sed 's/^ENV PORT=8000$/ENV PORT=7860/; s/^EXPOSE 8000$/EXPOSE 7860/' docker/demo.Dockerfile > "$OUT/Dockerfile"
cp deploy/hf-space-README.md "$OUT/README.md"           # Space front matter (sdk: docker, app_port: 7860)
cp .dockerignore "$OUT/.dockerignore"
echo "Space folder ready: $OUT ($(du -sh "$OUT" | cut -f1)). Contains no .env and no secrets."

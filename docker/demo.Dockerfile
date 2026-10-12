# One container for the whole interactive demo: API + built web app + Node/Playwright engine with Chromium.
# Build:  docker build -f docker/demo.Dockerfile -t open-apprentice-demo .
# Run:    docker run --rm -p 8000:8000 open-apprentice-demo            (no model, no credentials needed)
#         docker run --rm -p 8000:8000 --env-file .env -e DEMO_MODEL_ENABLED=1 -e DEMO_MODEL_MAX_USD=2 open-apprentice-demo   (Nemotron mode)
FROM node:22-bookworm-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /usr/local/bin/uv
WORKDIR /app
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    UV_PROJECT_ENVIRONMENT=/opt/venv UV_CACHE_DIR=/tmp/uv-cache UV_PYTHON_INSTALL_DIR=/opt/python \
    PATH="/opt/venv/bin:$PATH" HOME=/tmp/home OA_CHROMIUM_NO_SANDBOX=1

COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY services/engine/package.json services/engine/
RUN npm ci --no-audit --no-fund
RUN npx playwright install --with-deps chromium && chmod -R a+rX /ms-playwright

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --python 3.12 && chmod -R a+rX /opt/venv /opt/python

COPY apps/web apps/web
RUN npm run build -w apps/web
COPY services/engine services/engine
COPY prompts prompts
COPY configs configs
COPY docs/capabilities.json docs/capabilities.json
COPY docs/replay docs/replay

RUN mkdir -p /tmp/home && chmod 1777 /tmp/home
# UID 1000 is the `node` user in this base image; Hugging Face Spaces also runs containers as UID 1000.
USER 1000:1000
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||8000)+'/health/ready').then(r=>r.json()).then(j=>process.exit(j.engine?0:1)).catch(()=>process.exit(1))"
CMD ["sh", "-c", "exec uvicorn open_apprentice.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]

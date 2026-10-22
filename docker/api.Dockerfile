FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_CACHE_DIR=/tmp/uv-cache PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# the campaign verifier reads the vendored fonts/assets/manifest and the learner reads its prompt (repo-relative paths)
COPY services/engine/vendor ./services/engine/vendor
COPY prompts ./prompts
RUN uv sync --frozen --no-dev --python 3.12 && chmod -R a+rX /opt/venv
USER 10001:10001

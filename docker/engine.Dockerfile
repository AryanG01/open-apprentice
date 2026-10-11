FROM node:22-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
COPY services/engine/package.json services/engine/
COPY apps/web/package.json apps/web/
RUN npm ci --no-audit --no-fund -w services/engine --include-workspace-root=false
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npx playwright install --with-deps chromium && chmod -R a+rX /ms-playwright
COPY services/engine services/engine
USER 10001:10001
EXPOSE 8090
CMD ["node", "services/engine/src/server.js"]

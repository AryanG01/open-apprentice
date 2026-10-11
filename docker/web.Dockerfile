FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY services/engine/package.json services/engine/
COPY apps/web/package.json apps/web/
RUN npm ci --no-audit --no-fund -w apps/web --include-workspace-root=false
COPY apps/web apps/web
RUN npm run build -w apps/web

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html

# 1段目：Node.js で画面をビルドする
FROM node:24-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2段目：ビルドしたファイルだけを Caddy に移す（Node.js は入れない）
FROM caddy:2
COPY caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

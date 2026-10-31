# Panel: Node ile derlenir, Caddy ile servis edilir.
#
# Caddy tek giriş kapısı: statik dosyaları verir, `/api` isteklerini
# API kapsayıcısına aktarır. Böylece panel ile API **aynı kaynakta**
# olur — CORS yapılandırması dağıtımda devreye girmez ve imzalı kanıt
# bağlantıları (göreli adresler) olduğu gibi çalışır.
#
# Derleme bağlamı **depo kökü** (compose'da `context: .`): Caddyfile
# infra/ altında duruyor ve iki dizinden de okunabilmeli.

FROM node:22-slim AS derleme

WORKDIR /uygulama

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/tsconfig*.json web/vite.config.ts web/index.html ./
COPY web/src ./src
# Sözleşme tipleri depodan geliyor: derleme sırasında üretilmiyor ki
# imaj OpenAPI dosyasına bağlı kalmasın (tipler commit'li, ADR-0014 md.10).
RUN npm run build


FROM caddy:2-alpine

COPY --from=derleme /uygulama/dist /srv
COPY infra/Caddyfile /etc/caddy/Caddyfile

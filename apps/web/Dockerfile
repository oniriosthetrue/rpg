# =============================================================================
# Frontend Next.js « MJ D&D » — build multi-stage, sortie standalone.
# Contexte de build : ./apps/web (défini dans docker-compose.yml).
# =============================================================================

# ─── Dépendances ────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
# npm ci si un lockfile existe, sinon npm install (première génération).
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# ─── Build ──────────────────────────────────────────────────────────────────
FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Variables intégrées au build client (publiques).
ARG NEXT_PUBLIC_APP_HOST=rpg.minervia.fr
ENV NEXT_PUBLIC_APP_HOST=$NEXT_PUBLIC_APP_HOST
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ─── Exécution ──────────────────────────────────────────────────────────────
FROM node:20-alpine AS run
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
# Sortie standalone : regroupe le serveur + les chunks nécessaires.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]

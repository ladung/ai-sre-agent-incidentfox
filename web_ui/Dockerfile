FROM node:20-bookworm-slim AS base
WORKDIR /app

FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci

# Install platform-specific native binaries based on target architecture.
# TARGETARCH is set by BuildKit during multi-platform builds. With the legacy
# builder (DOCKER_BUILDKIT=0), TARGETARCH is empty, so we fall back to
# detecting the runtime arch via `uname -m`.
ARG TARGETARCH
RUN ARCH="${TARGETARCH:-$(uname -m | sed -e 's/x86_64/amd64/' -e 's/aarch64/arm64/')}"; \
    echo "Installing native binaries for arch: $ARCH"; \
    if [ "$ARCH" = "amd64" ]; then \
      npm install @next/swc-linux-x64-gnu lightningcss-linux-x64-gnu @tailwindcss/oxide-linux-x64-gnu --no-save || true; \
    elif [ "$ARCH" = "arm64" ]; then \
      npm install @next/swc-linux-arm64-gnu lightningcss-linux-arm64-gnu @tailwindcss/oxide-linux-arm64-gnu --no-save || true; \
    fi

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-bookworm-slim AS runner
WORKDIR /app

# Install security patches and remove npm/corepack (not needed at runtime, fixes CVE-2026-24842)
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* && \
    rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

ENV NODE_ENV=production
ENV PORT=3000
ENV NEXT_TELEMETRY_DISABLED=1

# Next.js standalone output
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]

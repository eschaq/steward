# Steward's frontend: a Vite build served as static files.
#
# Multi-stage because the toolchain is only needed to produce `dist/` — nothing
# in node_modules belongs in the running image. The result is nginx plus a few
# hundred KB of assets, which is why this service is so much cheaper to run than
# the backend.
#
# Every VITE_* value is baked in at build time: Vite substitutes
# `import.meta.env.*` during the build, so these are build args, not runtime
# env. They are all public by design — the Firebase web config ships in any
# Firebase app's bundle, and firestore.rules plus backend token verification are
# what actually protect data, not the secrecy of these strings.
FROM node:20-slim AS build

ARG VITE_API_BASE_URL
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_APP_ID
ARG VITE_ESTATE_ID=seed-estate-001

WORKDIR /app
# Lockfile first, so a source-only change reuses the install layer.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
# nginx:alpine substitutes ${PORT} from this template at container start, which
# is how it binds whatever port Cloud Run hands it rather than assuming 8080.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
ENV PORT=8080

<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Web implementation notes

The React/Vite client lives in `apps/web`. It serves a truthful public landing page at `/` and the authenticated workspace at `/app`. In local development the Vite server serves both routes; the production nginx fallback keeps deep links working. GitHub Pages uses `VITE_BASE_PATH=/BidWeave/` while the API and Keycloak URLs remain explicit build arguments.

## Runtime contract

`VITE_API_BASE` defaults to `/api`; `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM`, and `VITE_KEYCLOAK_CLIENT` match the integration contract. The client uses Keycloak PKCE (`S256`) and forwards the resulting bearer token to every API operation. There is no local role or demo identity fallback.

The H/P/D/I tabs map directly to the API contract: team tasks/comments, process submission/review/amendments, evidence/lineage/export, and permission-scoped intelligence. Application data is loaded from the API only. A synthetic case, if supplied by the deployment's seed procedure, should be labeled by the API/UI content rather than being fabricated by this client.

## Source and deploy

From `apps/web`, use `npm ci --ignore-scripts` and `npm run build` with Node 22. The two-stage Dockerfile builds from source and nginx serves `dist` with an SPA fallback. Commit dependency changes with the generated `package-lock.json`; do not hand-edit resolved package entries. The build also writes third-party runtime notices and verbatim licenses into `dist`.

GitHub Pages sets `VITE_STATIC_SITE=true` and `VITE_BASE_PATH=/BidWeave/`. That build shows only the project introduction and run instructions; it does not attempt to authenticate against a visitor's localhost. The local application uses the normal SSO-enabled build. The vocabulary file is static, while private lineage remains behind the API.

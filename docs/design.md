<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Web implementation notes

The React/Vite client lives in `apps/web`. It serves a truthful public landing page at `/` and the authenticated workspace at `/app`. In local development the Vite server serves both routes; the production nginx fallback keeps deep links working. GitHub Pages uses `VITE_BASE_PATH=/BidWeave/` while the API and Keycloak URLs remain explicit build arguments.

## Runtime contract

`VITE_API_BASE` defaults to `/api`; `VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM`, and `VITE_KEYCLOAK_CLIENT` match the integration contract. The client uses Keycloak PKCE (`S256`) and forwards the resulting bearer token to every API operation. There is no local role or demo identity fallback.

The H/P/D/I tabs map directly to the API contract: team tasks/comments, process submission/review/amendments, evidence/lineage/export, and permission-scoped intelligence. Application data is loaded from the API only. A synthetic case, if supplied by the deployment's seed procedure, should be labeled by the API/UI content rather than being fabricated by this client.

## Workspace 1.1 and theme boundary

The user selected Shadcn Admin as the visual reference for the workspace and login. The implementation uses the existing React/CSS client, without importing that template's application code or changing the public landing. The source of reusable tokens is [DESIGN.md](../DESIGN.md); `.app-shell` owns the operational palette and `data-bw-theme` selects the resolved light/dark theme.

`useThemePreference` accepts only `light`, `dark` or `system`. The preference is stored as `bidweave.theme` in localStorage and in the host-scoped `bidweave-theme` cookie (`Path=/`, `SameSite=Lax`, `Secure` on HTTPS). System mode follows `prefers-color-scheme`. These values contain no identity, role or token. Login can share the cookie across ports on one hostname; unrelated hostnames do not share it.

Loading, signed-out and authentication-error screens also use the themed application shell, with a single-column centered layout. They must not fall back to the landing palette. Editing errors remain inside the native dialog and receive focus when displayed. The sidebar becomes top navigation on narrow screens; dense work areas stack without removing actions.

## Keycloak presentation

`infra/keycloak/themes/bidweave/login` inherits the shipped Keycloak theme. CSS, a preference script and English/Vietnamese messages customize presentation; there is no replacement credential form, copied authentication protocol or client-side role fallback.

Fresh realm configuration selects the theme and Vietnamese default locale. `scripts/keycloak-theme.py`, called by `make up` and `make up-all`, applies only `loginTheme` to an existing realm using the authenticated Admin API. Existing users, clients, credentials and locale remain untouched. Admin credentials come from the ignored local environment; tokens are not printed or stored.

Desktop/mobile captures and a real create → verify → review → export journey are recorded in [verification.md](verification.md#7-giao-diện-110-workspace-và-keycloak). Successful LLM output from the earlier release is distinguished from the resource-limited Agent attempt during this UI review.


## Source and deploy

From `apps/web`, use `npm ci --ignore-scripts` and `npm run build` with Node 22. The two-stage Dockerfile builds from source and nginx serves `dist` with an SPA fallback. Commit dependency changes with the generated `package-lock.json`; do not hand-edit resolved package entries. The build also writes third-party runtime notices and verbatim licenses into `dist`.

GitHub Pages sets `VITE_STATIC_SITE=true` and `VITE_BASE_PATH=/BidWeave/`. That build shows only the project introduction and run instructions; it does not attempt to authenticate against a visitor's localhost. The local application uses the normal SSO-enabled build. The vocabulary file is static, while private lineage remains behind the API.

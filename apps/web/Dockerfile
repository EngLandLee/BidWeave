# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Multi-stage source build; runtime variables are supplied as Vite build arguments.
FROM node:22-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
ARG VITE_API_BASE=/api
ARG VITE_KEYCLOAK_URL=http://localhost:8091
ARG VITE_KEYCLOAK_REALM=bidweave
ARG VITE_KEYCLOAK_CLIENT=bidweave-web
ARG VITE_BASE_PATH=/
ENV VITE_API_BASE=$VITE_API_BASE VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM VITE_KEYCLOAK_CLIENT=$VITE_KEYCLOAK_CLIENT VITE_BASE_PATH=$VITE_BASE_PATH
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Integration contract

## Ownership and collaboration
Parent owns integration, Git/GitHub operations, runtime verification, demo seeding/smoke, final documentation truth. Workers edit ONLY their assigned files and never checkout/commit/push. Do not run builds, linters, tests or formatters mid-flight. One final integrated verification follows their delivery. Every authored file has SPDX Apache-2.0 header/sidecar; no cookies or credentials are committed.

## Layout and ownership
- Core worker: services/api/ except bidweave/intelligence.py; domain regression tests under services/api/tests/.
- Platform worker: infra/, compose.yaml, .env.example, Makefile, scripts/platform.py, scripts/backup.sh, scripts/restore.sh; services/workflow/ (small source-built Flowable Spring Boot REST engine if needed).
- Intelligence worker: services/api/bidweave/intelligence.py, services/mcp/, integrations/, data/, scripts/llm-smoke.py. Coordinate new API dependencies with core worker, do not edit its pyproject.
- Workspace worker: apps/web/ only plus DESIGN.md and docs/design.md. Source at apps/web; build output apps/web/dist. React + TypeScript + Vite. API-first no static mocked application data. Parent supplies PRODUCT.md.
- Repository worker: .github/, docs/ except contest.md, implementation-contract.md and design.md; README.md, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md, SUPPORT.md, CODE_OF_CONDUCT.md, NOTICE, scripts/check-headers.py, scripts/release.py, REUSE.toml. Do not claim tests have passed until evidence is provided.

## Runtime
Docker project bidweave. API service listens :8000, Vite production web :80. APISIX host http://localhost:8090 routes /api/* and /mcp to api:8000, all other paths web:80. Keycloak host http://localhost:8091 realm bidweave, public PKCE client bidweave-web, redirect http://localhost:8090/* and dev http://localhost:5173/*. Token audience bidweave-api, tenant claim tenant_id, roles coordinator/contributor/reviewer in realm_access.roles. Demo users coordinator, contributor, reviewer (tenant demo), outsider (tenant other); generated password from .env, no fixed production secret. Direct access grants enabled only for local smoke client/documented local demo. No unauthenticated X-Role/dev-auth bypass. API validates signature, issuer, audience and token expiry. Internal key fetching URL http://keycloak:8080/realms/bidweave/protocol/openid-connect/certs; public issuer configurable.
Postgres DATABASE_URL=postgresql+psycopg://bidweave:<generated>@postgres:5432/bidweave.
S3_ENDPOINT=http://seaweedfs:8333, S3_BUCKET=bidweave, S3_ACCESS_KEY/S3_SECRET_KEY. FLOWABLE_URL=http://workflow:8080/process-api, FLOWABLE_USER/FLOWABLE_PASSWORD. CLAMAV_HOST=clamav and port3310. NATS_URL=nats://nats:4222. FUSEKI_URL=http://fuseki:3030/bidweave. OLLAMA_URL=http://ollama:11434, LLM_MODEL=qwen2.5:0.5b (local resource-constrained default, configurable); actual inference required, no fake responses. n8n independent optional automation profile with real exported workflow. Allow explicit development security settings only in .env generated local config; bind service management ports to loopback.
Flowable process key bidweave-review: start→userTask review→end, deployment from infra/workflow/review.bpmn; variable tenant_id, case_id, revision and submitter. Core starts a real instance for a submission, completes only for independent reviewer; rejection terminates instance. Source-built engine can expose a small adapter instead if both workers agree before implementing. No silent local workflow substitute.

## API shape (required contract)
JSON errors {detail: string}; 401 missing/invalid auth, 403 rights, 404 cross-tenant/not found, 409 stale revision or unmet transition, 422 invalid input, 503 unavailable dependency.
GET /api/health public infrastructure readiness (no secrets).
GET /api/me → {id,username,tenant_id,roles: string[]}.
GET /api/cases → Case[]. POST /api/cases body {title,deadline,description?} → Case.
Case = {id,title,description,deadline,current_revision:number,status: draft|in_review|approved,owner_id,created_at}.
GET /api/cases/{id} → case fields plus {requirements:Requirement[],evidence:Evidence[],tasks:Task[],comments:Comment[],revisions:Revision[],approvals:Approval[],impact:Impact[],workflow_id?}.
POST /api/cases/{id}/revisions body {expected_revision,deadline,reason,requirements:RequirementInput[]} → updated detail.
RequirementInput = {key,title,description,kind: document|count|validity|text,minimum?:number,mandatory:boolean,source_ref:string,owner:string}; key stable within a case. A new case starts at revision0, first revision expected0 →1. Changes in title/whitespace alone do not alter deterministic constraints; description/source semantics conservatively require review. Key remapping is NOT automatic.
Requirement = input plus {revision,status:missing|needs_review|verified,evidence_ids:string[]}.
POST /api/cases/{id}/evidence multipart fields file, requirement_key, expected_revision, valid_until? ISOdate, quantity? integer, notes?; quarantine scan, sha256, store, then persist. → Evidence {id,requirement_key,filename,sha256,valid_until,quantity,notes,verified:boolean,uploaded_by,revision,created_at}.
POST /api/cases/{id}/evidence/{eid}/verify body {expected_revision} → updated detail; reviewer only, cannot self-verify own upload.
GET /api/cases/{id}/evidence/{eid}/download → authenticated original bytes; authorization checked before storage.
POST /api/cases/{id}/submit body {expected_revision} → detail; coordinator, all mandatory evidence verified and constraints satisfied. POST /api/cases/{id}/review body {expected_revision,decision:approve|reject,comment} → detail; independent reviewer only, requires active matching Flowable instance. Every transition invalidates stale state atomically.
GET /api/cases/{id}/export?revision=N → application/gzip .tar.gz only currently-approved exact revision, files plus manifest and provenance. Reject stale/cross-tenant/incomplete. Archive paths safe. Re-read version under lock; integrity verify evidence hashes. Historical exports are explicitly historical, never relabeled current.
POST /api/cases/{id}/comments body {body} → Comment {id,author,body,created_at}.
PATCH /api/cases/{id}/tasks/{task_id} body {status:open|done,assignee?} → detail. Tasks auto-created for impact, deduplicated per revision/key. Completion does not bypass evidence review.
GET /api/analytics → {case_count,approved_count,pending_review_count,open_tasks,requirements_count,verified_requirements,events:[...]} computed from tenant data.
GET /api/cases/{id}/lineage → JSON-LD linked graph of public notice/requirements/evidence/revisions/approvals. POST /api/cases/{id}/notice body {publication_number} links fetched TED notice and source graph to case.

## Intelligence endpoints (module exposes APIRouter named router; core includes it)
GET /api/linked-data/notices?date=YYYY-MM-DD&cpv_prefix=72 → {source,retrieved_at,notices:[{publication_number,cpv_code,cpv_label,source_graph}]} from bounded fixed SPARQL, never arbitrary caller query. Explicit source outage errors, snapshot endpoint separate.
POST /api/agent/chat {case_id,message} → {answer,sources:[],suggested_actions:[],model,limitations:[]} actual LLM; forward bearer token to internal core API (CORE_API_URL default http://127.0.0.1:8000); all retrieval is permission-checked. Case docs untrusted; no autonomous writes.
POST /api/agent/extract multipart file → {requirements:[RequirementInput],source,needs_review:true,model}; pypdf text parsing first, Docling optional external endpoint profile. LLM outputs validated schema, never treated as authoritative. Limit upload size/types and do not parse arbitrary URL.
GET /api/agent/status → actual provider availability/model, no secrets.
MCP server must implement real JSON-RPC initialize, tools/list, tools/call (streamable HTTP or stdio with official SDK); tools proxy same authorized domain APIs. Read tools + propose revision tasks and submit for review require explicit structured parameters/expected revision. Never provide approve or arbitrary SQL/shell tools.

## Frontend
Read token from OIDC PKCE flow (keycloak-js), not local fabricated identity; in-memory session storage acceptable local session, no credentials rendered. / is real project landing. /app is workspace behind login. Tabs H Team (tasks/comments), P Workflow (cases/review), D Evidence (matrix/upload/history/lineage/export), I Agent (chat/source refs/status). Provide case creation, revision editor including amendment, evidence upload+verify, submit/review and file download. Error/empty/loading states, labeled controls, keyboard/mobile. No fake activity or customer counts. Seeded content always tagged synthetic. VITE_API_BASE=/api, VITE_KEYCLOAK_URL=http://localhost:8091, VITE_KEYCLOAK_REALM=bidweave, VITE_KEYCLOAK_CLIENT=bidweave-web. Landing builds for GitHub Pages under /BidWeave/ via VITE_BASE_PATH; don't claim Pages hosts backend.

## Verification
Parent exercises real Docker services and browser; backend worker writes deterministic regression tests only for domain boundaries/stale versions/permissions (tests may isolate external adapters but cannot be only mock echoes). Source headers and all declared file-level licenses must pass REUSE. Parent publishes exact observed run evidence, not inferred success.

<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Product
<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
delegated: Python/FastAPI and PostgreSQL for domain operations; TypeScript/React/Vite for the workspace and landing page. The user explicitly delegated implementation decisions. External core engines are integrated through documented APIs, not copied into the repository.

## Users
The accepted concept targets an IT-services bidder: coordinator, contributor and independent reviewer. Vietnamese-first interface with English technical identifiers. This is a product hypothesis, not evidence of interviewed customers.

## Product Purpose
Keep a bid response consistent with the applicable tender revision. Convert changed requirements into assigned, reviewable work; preserve provenance and prevent stale approval/export.

## Operating Context
A coordinator creates a case and revision, imports public metadata, captures requirements, attaches evidence and requests review. Another authorized person approves the exact revision. An amendment recomputes impact and invalidates current readiness without erasing historical approvals. The final package includes the approved manifest, original evidence and provenance.

## Acceptance
- Three tiers: reusable headless services; a shared HPDI workspace; a tender-domain module.
- Four working core services: Keycloak OIDC SSO, APISIX, PostgreSQL/object storage, Flowable BPMN.
- H: assignments and comments. P: submission, independent review, amendment and export. D: evidence matrix, metrics, source lineage and revision history. I: real LLM-assisted suggestions and scoped MCP tools; never fabricated model output.
- Immutable requirements/evidence revisions, explicit self-declared versus verified evidence, optimistic version checks, tenant boundaries, separated submitter/reviewer, valid-at-deadline rules and deterministic thresholds.
- Real TED RDF queries scoped to named graphs; local snapshots identified as snapshots, not live data. ePO/CCCEV links retain attribution.
- Document parsing, quarantined uploads, integrity hashes, event delivery, analytics snapshots, monitoring and recoverable deployment.
- n8n connectors remain an independently licensed third-party service; Flowable owns approval workflow state.
- Code, documentation, issues, branches, pull requests, CI, source release and landing page have truthful provenance and verified setup instructions.

## Boundaries
No IoT. No autonomous tender submission, fake certificate generation, legal certification, guaranteed eligibility or guaranteed winning. Synthetic examples must be clearly identified. Missing integrations fail explicitly rather than returning mock success. External LLM requests must respect confidential document boundaries.

## Evidence on Hand
Official OLP problem and rubric are linked in docs/contest.md. Live TED SPARQL was queried during research; this establishes access to public metadata, not access rights to every attached tender document. No real customer, revenue or performance claim exists.

## Accessibility
Keyboard navigation, associated input labels, visible focus, readable contrast, responsive desktop/mobile and reduced-motion support.

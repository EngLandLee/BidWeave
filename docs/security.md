<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Threat boundaries

BidWeave protects workflow integrity and tenant separation; it is not a legal compliance or malware-proofing guarantee. Operators remain responsible for identity provider policy, host hardening, retention, incident response and lawful use.

## Trust zones

- **Public:** browser, GitHub Pages landing, public TED metadata. Landing must not contain credentials, case data or private evidence.
- **Authenticated tenant:** OIDC bearer tokens and API requests. The API validates signature, issuer, audience, expiry, tenant claim and role; UI visibility is not authorization.
- **Private evidence:** uploaded files, parsed text, hashes, comments, requirements and approval history. Storage authorization occurs before download; object keys never act as credentials.
- **External processors:** Flowable, ClamAV, TED/Fuseki, Ollama/remote LLM and optional n8n. Send only the minimum permitted data; provider outage/failure remains explicit.

Public TED notice metadata may be linked to a case, but access to a public notice does not grant access to tender attachments. Private documents must not be sent to an external LLM unless the deployment policy, tenant authorization and data-processing terms allow it. LLM output is untrusted and never directly changes requirements, approvals or permissions.

## Abuse cases and controls

- **Cross-tenant access:** every domain query is tenant-scoped; unknown/cross-tenant objects return 404; roles are checked server-side.
- **Stale approval/amendment:** optimistic revision checks and atomic transitions reject stale requests; amendment invalidates readiness and creates impact tasks.
- **Self-approval:** submitter and reviewer separation is enforced; uploader cannot verify own evidence; Flowable instance must match case/revision.
- **Malicious upload/path traversal:** upload size limits, ClamAV before object storage, SHA-256, safe archive paths and authorization before bytes; preview/extraction additionally restrict supported document types. No persistent quarantine archive is implemented.
- **Prompt injection/data exfiltration:** documents are untrusted context; bounded retrieval/MCP tools; no arbitrary SQL/shell/approve tool; source references and limitations are returned.
- **Credential leakage:** random generated local secrets, `.env` ignored, no secrets in release/logs/screenshots; production secrets belong to deployment secret manager.
- **Supply chain:** dependencies are declared, source is not vendored, CI pins actions and checks REUSE/headers; release carries SBOM and dependency inventory.

Report security issues privately as described in [SECURITY.md](../SECURITY.md). Do not include confidential tender files or credentials in public tickets.

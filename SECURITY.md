<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Security policy

## Supported versions

Only the latest published source release and the default branch receive coordinated fixes. Integrated third-party services and model/data providers follow their own support policies.

## Reporting

Do not open a public issue for a vulnerability. Contact the repository maintainers privately through the security contact configured on the GitHub repository (GitHub Security Advisories if enabled). If that channel is unavailable, contact the repository owner `@EngLandLee` through GitHub and request a private channel. Include a concise impact description, affected commit/version, reproducible steps without private tender files, and a safe contact for follow-up. Never include credentials, personal data, or confidential documents.

We will acknowledge receipt when practicable, assess severity and affected boundaries, coordinate a fix/advisory, and credit reporters only with permission. There is no guarantee of a response time or of a legal/compliance outcome.

## Deployment boundary

Operators must generate and rotate secrets, harden hosts, restrict management ports, configure OIDC claims/audience, encrypt backups, set retention, and review external LLM/data-processing terms. See [docs/security.md](docs/security.md). The project does not guarantee malware detection, confidentiality against a compromised deployment, legal compliance, eligibility or award.

<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# BidWeave design system

BidWeave is a revision-aware procurement workspace. Its visual language is an editorial dossier: a dark ink/navy shell frames warm reading surfaces; rust marks a change; status colors communicate workflow state without relying on color alone. The interface is deliberately compact and operational rather than decorative.

## Surfaces

- **Landing / Persuade:** a quiet public explanation of the mechanism, with a single dossier preview and direct links to the workspace and source.
- **Workspace / Operate:** the H/P/D/I tabs share the same sidebar, case selector, revision context, compact rows, labeled forms, and persistent change marker.
- **States:** loading, network/offline, empty, API error, stale 409, disabled controls, and reduced-motion behavior are first-class.

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| `--ink` | `#142434` | body text and high-contrast foreground |
| `--navy` | `#0d2638` | shell, primary actions, code surfaces |
| `--paper` | `#fbfaf6` | reading surfaces |
| `--sand` | `#e8e2d7` | quiet controls and explanatory fills |
| `--line` | `#d7d1c7` | rules and table separation |
| `--rust` | `#bb4d2e` | focus, primary action, revision/change marker |
| `--green` | `#2b7058` | verified/approved/done |
| `--amber` | `#ae7128` | in-review/needs-review |
| `--red` | `#a23c39` | explicit error treatment |

Typography uses self-hosted Newsreader (SIL OFL-1.1) for editorial headings, a system sans for Vietnamese body text, and monospace only for stable requirement keys, hashes and revision measurements. Font files and license notices are bundled during the source build; there are no external font requests.

## Interaction rules

- Backend authorization is authoritative. Role-aware controls reduce noise but every operation handles 401/403/409/422/503 responses visibly.
- Every revision mutation includes `expected_revision`; a stale response is labeled as stale rather than silently retried.
- A requirement has a stable key, kind, owner, mandatory flag, and source reference. Evidence displays filename, hash prefix, uploader, and verification state.
- Export is a real API link for the exact current revision; unavailable or incomplete exports remain errors.
- Agent responses show model, sources, and limitations. Extraction candidates are always labeled as needing review.
- Focus is visible, controls have labels, keyboard users can reach every action, and narrow screens collapse columns without hiding content.

## Ownership

The web surface is source-built at `apps/web`, with `VITE_API_BASE`, Keycloak settings, and `VITE_BASE_PATH` supplied by the deployment. No external fonts, image CDNs, invented metrics, synthetic app success, or unauthoritative identity state are used.

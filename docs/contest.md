<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# OLP 2026: requirements and licensing decision

Sources consulted on 2026-10-16:
- https://vfossa.vn/tin-tuc/de-thi-phan-mem-nguon-mo-olp-2026-798.html
- https://vfossa.vn/tin-tuc/the-le-olp-phan-mem-nguon-mo-nam-2026-760.html
- https://reuse.software/spec-3.3/

The problem requires a headless Tier 1 with Identity/SSO, API Gateway, structured/unstructured data and Workflow, plus at least one HPDI interface in Tier 2. BidWeave deliberately covers H, P, D and I and a tender-domain Tier 3. The seven-layer technology table is a reference architecture, not a requirement to install every named vendor product. Section 4 also mentions IT/OT convergence; BidWeave has no IoT and must not claim an organizer waiver or guaranteed full technical compliance for that wording.

The PoF rubric explicitly deducts five points when the license is not recorded in each source file ("Giấy phép không được ghi trong từng tệp mã"). It also requires compatible OSI licensing, license-purpose notice, full license text, public versioned release, build-from-source instructions, declared dependencies, real bug tracking and changelog. Use .tar.gz source release assets to avoid the rubric's expressly listed archive-format penalties. No score is guaranteed.

## File policy
Every owned commentable source/config/document file carries SPDX-FileCopyrightText and SPDX-License-Identifier: Apache-2.0 near the top, preserving shebang/XML declarations. Code includes an Apache notice of permitted reuse and lack of warranty. Un-commentable files (JSON, images, PDF) have adjacent .license sidecars. REUSE covers generated files explicitly, not with a blanket license that overwrites upstream attribution. LICENSE and LICENSES/Apache-2.0.txt contain the full canonical license. Third-party source is not vendored or relicensed. External service and dataset licenses are documented separately.

This is an implementation policy based on the published rubric and REUSE, not a claim that BTC explicitly endorsed SPDX sidecars. Final acceptance and scoring belong to the judges.

<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Contributing to BidWeave

## Before changing code

Read [PRODUCT.md](PRODUCT.md), [docs/implementation-contract.md](docs/implementation-contract.md), and the relevant architecture/security/license docs. Keep API behavior within the shared contract; communicate interface changes before editing callers. Do not commit credentials, private tender documents, runtime state, generated `node_modules`, or upstream source.

## Issues and pull requests

Use the bug, feature or research issue form. A pull request must state scope, affected contract, acceptance criteria, security/privacy impact, verification evidence or an explicit unavailable dependency, and license/header impact. Do not claim a test or score that was not observed. Keep synthetic data clearly labelled.

### Branch and status workflow

1. **Research — `status:research`:** record the problem, primary sources, license constraints, alternatives and observable acceptance criteria in an issue. Use the release milestone for a bounded delivery, not a promised contest score.
2. **Implementation — `status:in-progress`:** branch from `develop` as `feature/<issue>-<description>` or `fix/<issue>-<description>`. Make coherent commits that reference the issue; do not invent commits or backdate work to simulate activity.
3. **Review — `status:review`:** open a pull request to `develop`, link evidence and explain risks. Run the CI checks and inspect the changed behavior. Automated/self-review must be labelled as such; it is not an independent human approval.
4. **Completion — `status:done`:** merge only after the acceptance criteria and required checks pass, then close the issue with evidence. If it was found incomplete, move it back to in-progress and describe the remaining failure instead of marking it done.
5. **Release:** open a `develop` → `main` pull request. `main` is the public release line; Pages publishes its landing page. Align application versions and changelog before pushing a semantic `vX.Y.Z` tag. The release workflow builds from source and validates SPDX/checksums before publishing assets.

Keep one status label per issue. Preserve the discussion history as work moves through states. Do not fabricate reviewers, users, deployments, test output or community participation. A solo maintainer can transparently self-review, but must not claim to have received an independent review.

## Development policy

- Source and documentation use SPDX Apache-2.0 headers; non-commentable files use adjacent `.license` sidecars.
- Preserve tenant isolation, OIDC validation, revision checks, independent review and explicit external dependency failures.
- Add deterministic tests for meaningful domain boundaries and edge cases; do not replace real integrations with fake success.
- Run the documented build/check commands before requesting review and report exact results.
- Follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and report security issues privately via [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contribution is provided under Apache-2.0, with attribution preserved where another license applies. See [NOTICE](NOTICE) and [docs/licensing.md](docs/licensing.md).

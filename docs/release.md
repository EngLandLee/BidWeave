<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Source release procedure

A source release is a reproducible `.tar.gz` of this repository, not a production deployment or container image. Before tagging, maintainers must record runtime evidence and complete a dependency/REUSE review; no score or compatibility guarantee is implied.

The release job builds the workflow service from tracked source with Java 21 and Maven, then passes that exact executable JAR to the offline dependency inventory generator. From the repository root, the equivalent maintainer commands are:

```sh
python3 scripts/check-headers.py
reuse lint
mvn -B --no-transfer-progress -f services/workflow/pom.xml clean package
python3 scripts/release.py \
  --version 1.1.0 \
  --workflow-jar services/workflow/target/bidweave-workflow-1.1.0.jar \
  --output dist/release
(cd dist/release && sha256sum --check SHA256SUMS)
uvx --from spdx-tools==0.8.3 pyspdxtools --infile dist/release/sbom.spdx.json
uvx --from spdx-tools==0.8.3 pyspdxtools --infile dist/release/dependency-sbom.spdx.json
```

`release.py` rejects malformed versions and missing JAR inputs. It writes:

- `bidweave-<version>.tar.gz`, sorted source inputs with normalized tar ownership/modes/timestamps and a fixed gzip timestamp;
- `sbom.spdx.json`, an SPDX 2.3 inventory of the source archive inputs;
- `dependency-sbom.spdx.json`, an SPDX 2.3 inventory assembled only from `uv.lock`, hash-locked MCP requirements, npm lockfile v3, the built Spring Boot JAR, and declared compose image references;
- `dependency-inventory.json`, declared manifest hashes and integration boundaries;
- `SHA256SUMS`, covering the four assets above.

The dependency inventory does not fetch registries or build external images. Unknown upstream license metadata is recorded as `NOASSERTION`, and compose tags are declarations rather than content digests unless an explicit `@sha256:` reference is present.

The generator can also be run directly for inspection (it writes `dependency-sbom.spdx.json` into the directory):

```sh
python3 scripts/dependency-sbom.py \
  --workflow-jar services/workflow/target/bidweave-workflow-1.1.0.jar \
  --output-dir dist/release
```

GitHub release workflow runs on `v*`, validates the semantic version, checks headers, builds the Java 21 artifact, validates both SPDX documents with `spdx-tools`, verifies all generated checksums, uploads the assets, and publishes only after those steps succeed. The pull-request CI also exercises archive generation and SPDX validation. Do not upload private evidence, `.env`, credentials, runtime database dumps or generated model weights.

The Maven inventory reads every embedded POM coordinate, including shaded components (for example inside Angus Mail and MyBatis). Only the enclosing artifact receives the JAR checksum. Multiple POM license entries remain `NOASSERTION` unless their semantics are established separately; the original names/URLs remain in provenance rather than being guessed as `AND` or `OR`.

SHA-1 file checksums and package verification codes are present because SPDX 2.3 requires them; SHA-256 remains the integrity check for release assets. Source archive reproducibility means identical tracked content (including executable bits) and version produce identical archive bytes. It does not claim that external image tags, model downloads or independently rebuilt Java binaries are bit-for-bit reproducible.

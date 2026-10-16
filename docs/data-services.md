<!-- SPDX-FileCopyrightText: 2026 BidWeave contributors
SPDX-License-Identifier: Apache-2.0 -->

# Data services

`bidweave.projections` contains bounded, headless projections for lineage and
analytics. PostgreSQL remains authoritative for cases, revisions, approvals,
requirements and evidence metadata. Projection code never reads or copies the
object-store bytes represented by an evidence row.

## Lineage

`build_lineage(case, db, public_base="http://localhost:8090")` returns JSON-LD
with an explicit context for the BidWeave vocabulary, ePO, CCCEV, PROV,
Dublin Core Terms and Schema.org. Revision links use the revision UUID in the
URI and carry the exact revision number as a separate property. Requirements,
evidence, approvals, actors and public TED notice/source-graph entities are
linked to those revision URIs. TED links retain the public source graph and
retrieval attribution; they do not imply access to tender attachments.

The API route must authorize the case before calling the function. The graph
contains metadata and SHA-256 values only. It is deterministic for unchanged
source rows, which makes it suitable for a retryable event or background job.

`publish_lineage(graph, tenant_id, case_id)` validates the JSON-LD with
`rdflib`, then performs an authenticated HTTP PUT to the configured Fuseki
Graph Store endpoint. The endpoint is process configuration (`FUSEKI_URL`),
not a caller-supplied URL. The named graph URI is deterministic and encodes
both tenant and case identifiers. Configure either `FUSEKI_TOKEN` or the
`FUSEKI_USER`/`FUSEKI_PASSWORD` pair. Anonymous publishing is rejected unless
`FUSEKI_ALLOW_ANONYMOUS=true` is explicitly set for a local deployment.

## Cold history snapshots

`snapshot_case(case, db)` reads at most 10,000 rows per bounded collection for
the case's current revision and writes an analytical snapshot to
`HISTORY_DIR` (default `/data/history`). It creates:

- `history.duckdb`, containing `snapshot_records` with revision metadata,
  metrics, schema version and content hash;
- `snapshots.parquet`, atomically replaced from the same DuckDB table; and
- `history.lock`, used for cross-process serialization of writers.

The snapshot key is tenant + case + revision number. Repeating a snapshot with
identical source content is idempotent. If source data for an existing key has
changed, `SnapshotIntegrityError` is raised rather than silently overwriting
history. Temporary Parquet files are created in the configured directory and
renamed atomically. Case and tenant values are database fields, not path
components, so user input cannot select arbitrary files.

The snapshot records revision requirements, evidence metadata/hashes, approval
metadata and deterministic metrics. It does not change case status, freeze a
revision, create an approval, or claim legal immutability. It is not a
transactional Lakehouse or ledger; rebuildable PostgreSQL-derived analytics
only.

`history_for_case(case, db)` scopes reads by both `case.tenant_id` and
`case.id`. `history_for_tenant(tenant_id)` scopes every query by the supplied
tenant. These functions do not replace API authentication: the route or event
consumer must authenticate and authorize the caller first.

## Event and CLI use

`synchronize_case(case, db)` is the event/background adapter and delegates to
the same snapshot implementation. To synchronize real database cases without
a frontend, run from the API environment:

```text
python -m bidweave.projections [--tenant TENANT_ID] [--case CASE_ID]
```

The command uses the configured SQLAlchemy database session and fails when no
matching case or current revision exists; it does not seed synthetic rows.

The API dependency manifest must pin these additional libraries:

- `rdflib==7.1.3` (JSON-LD parsing/serialization);
- `duckdb==1.1.3` (DuckDB storage and Parquet analytical export).

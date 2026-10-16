# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
"""Bounded lineage publication and cold-history projections.

PostgreSQL remains the source of truth for cases and evidence.  This module
only projects metadata, hashes, and metrics: evidence object bytes are never
copied to JSON-LD or history.  History is a local analytical snapshot and is
not a legal immutable ledger or a transactional Lakehouse.
"""

from __future__ import annotations

import argparse
import hashlib
import base64
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .domain import requirement_satisfied
from .models import Approval, Case, Evidence, Notice, Requirement, Revision

MAX_LINEAGE_ROWS = 10_000
MAX_HISTORY_ROWS = 10_000
HISTORY_SCHEMA_VERSION = 1
DEFAULT_HISTORY_DIR = "/data/history"
DEFAULT_FUSEKI_URL = "http://localhost:3030/bidweave"

EPO = "http://data.europa.eu/a4g/ontology#"
CCCEV = "http://data.europa.eu/m8g/"
PROV = "http://www.w3.org/ns/prov#"
DCTERMS = "http://purl.org/dc/terms/"
SCHEMA = "https://schema.org/"
BIDWEAVE_VOCAB = "https://englandlee.github.io/BidWeave/vocab.jsonld#"


class ProjectionError(RuntimeError):
    """Base error for an unavailable or invalid projection operation."""


class ProjectionConfigurationError(ProjectionError):
    """A required projection setting is absent or unsafe."""


class SnapshotIntegrityError(ProjectionError):
    """A supposedly idempotent snapshot key has changed content."""


def _text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _path_part(value: Any) -> str:
    value = _text(value)
    if not value or value in {".", ".."}:
        raise ProjectionError("projection identifier is empty")
    return quote(value, safe="")


def _base_uri(public_base: str) -> str:
    value = str(public_base).strip().rstrip("/")
    if not value or not value.startswith(("http://", "https://")):
        raise ProjectionConfigurationError("public_base must be an HTTP(S) origin")
    return value


def _uri(base: str, *parts: Any) -> str:
    return "/".join([base, *(_path_part(part) for part in parts)])


def _iso(value: Any) -> str | None:
    return (
        value.isoformat()
        if value is not None and hasattr(value, "isoformat")
        else (str(value) if value is not None else None)
    )


def _bounded(
    db: Session, statement: Any, label: str, limit: int = MAX_LINEAGE_ROWS
) -> list[Any]:
    rows = list(db.scalars(statement.limit(limit + 1)).all())
    if len(rows) > limit:
        raise ProjectionError(f"{label} exceeds projection bound ({limit})")
    return rows


def _actor_node(actor: str, base: str, nodes: dict[str, dict[str, Any]]) -> str:
    actor_id = _uri(base, "actors", actor)
    nodes.setdefault(
        actor_id, {"@id": actor_id, "@type": "prov:Agent", "schema:identifier": actor}
    )
    return actor_id


def build_lineage(
    case: Case, db: Session, public_base: str = "http://localhost:8090"
) -> dict[str, Any]:
    """Build deterministic JSON-LD for one tenant-owned case.

    The caller must perform tenant authorization before calling this function.
    Every revision URI includes its database UUID while also exposing its exact
    revision number.  This avoids the old ambiguous ``revision:<number>``
    links when a case has amendments.
    """
    if not getattr(case, "id", None) or not getattr(case, "tenant_id", None):
        raise ProjectionError("case must have an id and tenant")
    base = _base_uri(public_base)
    case_id = _uri(base, "api", "cases", case.id)
    revisions = _bounded(
        db,
        select(Revision)
        .where(Revision.case_id == case.id, Revision.tenant_id == case.tenant_id)
        .order_by(Revision.number),
        "revisions",
    )
    requirements = _bounded(
        db,
        select(Requirement)
        .where(Requirement.case_id == case.id, Requirement.tenant_id == case.tenant_id)
        .order_by(Requirement.revision, Requirement.key),
        "requirements",
    )
    evidence = _bounded(
        db,
        select(Evidence)
        .where(Evidence.case_id == case.id, Evidence.tenant_id == case.tenant_id)
        .order_by(Evidence.revision, Evidence.id),
        "evidence",
    )
    approvals = _bounded(
        db,
        select(Approval)
        .where(Approval.case_id == case.id, Approval.tenant_id == case.tenant_id)
        .order_by(Approval.created_at, Approval.id),
        "approvals",
    )
    notices = _bounded(
        db,
        select(Notice)
        .where(Notice.case_id == case.id, Notice.tenant_id == case.tenant_id)
        .order_by(Notice.retrieved_at, Notice.id),
        "notices",
    )

    revision_uris: dict[int, str] = {}
    for revision in revisions:
        if not revision.id:
            raise ProjectionError("revision has no stable UUID")
        revision_uris[revision.number] = _uri(
            base, "api", "cases", case.id, "revisions", revision.id
        )

    nodes: dict[str, dict[str, Any]] = {
        case_id: {
            "@id": case_id,
            "@type": "bw:BidCase",
            "schema:name": case.title,
            "schema:description": case.description or "",
            "bw:tenant": case.tenant_id,
            "bw:currentRevision": {"@id": revision_uris[case.current_revision]}
            if case.current_revision in revision_uris
            else None,
            "bw:hasRevision": [
                {"@id": revision_uris[revision.number]}
                for revision in revisions
                if revision.number in revision_uris
            ],
        }
    }
    if nodes[case_id]["bw:currentRevision"] is None:
        nodes[case_id].pop("bw:currentRevision")

    for revision in revisions:
        revision_uri = revision_uris[revision.number]
        nodes[revision_uri] = {
            "@id": revision_uri,
            "@type": "bw:Revision",
            "bw:uuid": revision.id,
            "bw:revisionNumber": revision.number,
            "bw:submissionDeadline": _iso(revision.deadline),
            "schema:description": revision.reason,
            "bw:createdBy": {"@id": _actor_node(revision.created_by, base, nodes)},
            "prov:specializationOf": {"@id": case_id},
        }

    evidence_by_key: dict[tuple[int, str], list[str]] = {}
    for item in evidence:
        evidence_uri = _uri(base, "api", "cases", case.id, "evidence", item.id)
        revision_uri = revision_uris.get(item.revision)
        if revision_uri is None:
            raise ProjectionError(
                f"evidence {item.id} references unknown revision {item.revision}"
            )
        evidence_by_key.setdefault((item.revision, item.requirement_key), []).append(
            evidence_uri
        )
        node: dict[str, Any] = {
            "@id": evidence_uri,
            "@type": "cccev:Evidence",
            "bw:uuid": item.id,
            "bw:filename": item.filename,
            "bw:sha256": item.sha256,
            "bw:revision": {"@id": revision_uri},
            "bw:requirementKey": item.requirement_key,
            "bw:verified": bool(item.verified),
            "prov:wasAttributedTo": {"@id": _actor_node(item.uploaded_by, base, nodes)},
            "schema:dateCreated": _iso(item.created_at),
        }
        if item.quantity is not None:
            node["bw:quantity"] = item.quantity
        if item.valid_until is not None:
            node["bw:validUntil"] = _iso(item.valid_until)
        if item.verified_by:
            node["bw:verifiedBy"] = {"@id": _actor_node(item.verified_by, base, nodes)}
        nodes[evidence_uri] = node

    for requirement in requirements:
        requirement_uri = _uri(
            base, "api", "cases", case.id, "requirements", requirement.id
        )
        revision_uri = revision_uris.get(requirement.revision)
        if revision_uri is None:
            raise ProjectionError(
                f"requirement {requirement.id} references unknown revision {requirement.revision}"
            )
        links = [
            {"@id": uri}
            for uri in evidence_by_key.get((requirement.revision, requirement.key), [])
        ]
        node = {
            "@id": requirement_uri,
            "@type": "bw:Requirement",
            "bw:uuid": requirement.id,
            "bw:key": requirement.key,
            "schema:name": requirement.title,
            "schema:description": requirement.description,
            "bw:kind": requirement.kind,
            "bw:mandatory": bool(requirement.mandatory),
            "bw:revision": {"@id": revision_uri},
            "bw:sourceRef": requirement.source_ref,
            "bw:owner": requirement.owner,
            "bw:hasEvidence": links,
            "prov:wasDerivedFrom": {"@id": revision_uri},
        }
        if requirement.minimum is not None:
            node["bw:minimum"] = requirement.minimum
        nodes[requirement_uri] = node

    for approval in approvals:
        approval_uri = _uri(base, "api", "cases", case.id, "approvals", approval.id)
        revision_uri = revision_uris.get(approval.revision)
        if revision_uri is None:
            raise ProjectionError(
                f"approval {approval.id} references unknown revision {approval.revision}"
            )
        reviewer_uri = _actor_node(approval.reviewer_id, base, nodes)
        nodes[approval_uri] = {
            "@id": approval_uri,
            "@type": "bw:Approval",
            "bw:uuid": approval.id,
            "bw:decision": approval.decision,
            "bw:comment": approval.comment,
            "bw:revision": {"@id": revision_uri},
            "prov:wasAssociatedWith": {"@id": reviewer_uri},
            "prov:wasDerivedFrom": {"@id": revision_uri},
            "schema:dateCreated": _iso(approval.created_at),
        }

    for notice in notices:
        notice_uri = _uri(base, "api", "cases", case.id, "notices", notice.id)
        source = notice.source_graph.strip()
        if not source:
            raise ProjectionError(f"notice {notice.id} has no public source graph")
        source_uri = (
            source
            if source.startswith(("http://", "https://", "urn:"))
            else _uri(base, "sources", source)
        )
        source_node = {
            "@id": source_uri,
            "@type": "prov:Entity",
            "dcterms:identifier": source,
            "bw:public": True,
        }
        nodes.setdefault(source_uri, source_node)
        nodes[notice_uri] = {
            "@id": notice_uri,
            "@type": "bw:NoticeReference",
            "bw:uuid": notice.id,
            "bw:publicationNumber": notice.publication_number,
            "bw:sourceGraph": {"@id": source_uri},
            "dcterms:source": {"@id": source_uri},
            "prov:wasDerivedFrom": {"@id": source_uri},
            "bw:retrievedAt": _iso(notice.retrieved_at),
        }

    # Sorting makes repeated event/background projections byte-for-byte stable.
    ordered = [nodes[key] for key in sorted(nodes)]
    return {
        "@context": {
            "@vocab": BIDWEAVE_VOCAB,
            "bw": BIDWEAVE_VOCAB,
            "epo": EPO,
            "cccev": CCCEV,
            "prov": PROV,
            "dcterms": DCTERMS,
            "schema": SCHEMA,
        },
        "@graph": ordered,
    }


def _fuseki_config() -> tuple[str, dict[str, str]]:
    endpoint = os.getenv("FUSEKI_URL", DEFAULT_FUSEKI_URL).strip().rstrip("/")
    if not endpoint.startswith(("http://", "https://")):
        raise ProjectionConfigurationError("FUSEKI_URL must be an HTTP(S) URL")
    headers = {"Accept": "application/ld+json", "Content-Type": "application/ld+json"}
    token = os.getenv("FUSEKI_TOKEN", "").strip()
    user = os.getenv("FUSEKI_USER", os.getenv("FUSEKI_USERNAME", "")).strip()
    password = os.getenv("FUSEKI_PASSWORD", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif user and password:
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
    elif (
        not (user and password)
        and os.getenv("FUSEKI_ALLOW_ANONYMOUS", "").lower() != "true"
    ):
        raise ProjectionConfigurationError("Fuseki authentication is not configured")
    if endpoint.endswith("/data"):
        return endpoint, headers
    return endpoint + "/data", headers


def _named_graph_uri(tenant_id: str, case_id: str) -> str:
    if not tenant_id or not case_id:
        raise ProjectionError("tenant_id and case_id are required")
    return f"{BIDWEAVE_VOCAB}graph/tenant/{_path_part(tenant_id)}/case/{_path_part(case_id)}"


def publish_lineage(
    graph: dict[str, Any], tenant_id: str, case_id: str
) -> dict[str, Any]:
    """PUT JSON-LD to the configured Fuseki named graph.

    Fuseki configuration is process-level only; callers cannot provide an
    arbitrary endpoint.  The graph URI is deterministic and URL-encoded for
    each tenant/case pair, so a tenant can never overwrite another tenant's
    named graph accidentally.
    """
    if not isinstance(graph, dict) or not isinstance(graph.get("@graph"), list):
        raise ProjectionError("graph must be a JSON-LD object with @graph")
    try:
        from rdflib import Graph as RDFGraph
    except ImportError as exc:  # pragma: no cover - packaging failure
        raise ProjectionConfigurationError(
            "rdflib is required for lineage publication"
        ) from exc
    payload = json.dumps(
        graph, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    parsed = RDFGraph()
    try:
        parsed.parse(data=payload, format="json-ld")
        serialized = parsed.serialize(format="json-ld", auto_compact=False)
    except Exception as exc:  # rdflib exposes parser-specific exception classes
        raise ProjectionError(f"invalid JSON-LD lineage: {exc}") from exc
    if isinstance(serialized, str):
        serialized_bytes = serialized.encode("utf-8")
    else:
        serialized_bytes = bytes(serialized)
    endpoint, headers = _fuseki_config()
    graph_uri = _named_graph_uri(tenant_id, case_id)
    try:
        response = httpx.put(
            endpoint,
            params={"graph": graph_uri},
            content=serialized_bytes,
            headers=headers,
            timeout=float(os.getenv("FUSEKI_TIMEOUT_SECONDS", "15")),
        )
    except httpx.HTTPError as exc:
        raise ProjectionError(f"Fuseki unavailable: {exc}") from exc
    if response.status_code < 200 or response.status_code >= 300:
        detail = response.text[:500]
        raise ProjectionError(
            f"Fuseki rejected lineage ({response.status_code}): {detail}"
        )
    return {
        "graph_uri": graph_uri,
        "status_code": response.status_code,
        "triple_count": len(parsed),
        "content_sha256": hashlib.sha256(serialized_bytes).hexdigest(),
    }


def _history_root() -> Path:
    raw = os.getenv("HISTORY_DIR", DEFAULT_HISTORY_DIR).strip()
    if not raw:
        raise ProjectionConfigurationError("HISTORY_DIR cannot be empty")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ProjectionConfigurationError("HISTORY_DIR must be an absolute path")
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _duckdb():
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - packaging failure
        raise ProjectionConfigurationError(
            "duckdb is required for history projections"
        ) from exc
    return duckdb


def _lock(root: Path):
    import fcntl

    handle = (root / "history.lock").open("a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _init_history(connection: Any) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshot_records (
            snapshot_key VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            case_id VARCHAR NOT NULL,
            revision_id VARCHAR NOT NULL,
            revision_number INTEGER NOT NULL,
            case_status VARCHAR NOT NULL,
            captured_at VARCHAR NOT NULL,
            content_sha256 VARCHAR NOT NULL,
            schema_version INTEGER NOT NULL,
            payload_json VARCHAR NOT NULL,
            requirements_count INTEGER NOT NULL,
            evidence_count INTEGER NOT NULL,
            verified_evidence_count INTEGER NOT NULL,
            mandatory_requirements INTEGER NOT NULL,
            verified_requirements INTEGER NOT NULL
        )
        """
    )


def _row_payload(
    case: Case,
    revision: Revision,
    requirements: list[Requirement],
    evidence: list[Evidence],
    approvals: list[Approval],
) -> dict[str, Any]:
    evidence_rows = [
        {
            "id": item.id,
            "requirement_key": item.requirement_key,
            "filename": item.filename,
            "sha256": item.sha256,
            "valid_until": _iso(item.valid_until),
            "quantity": item.quantity,
            "verified": bool(item.verified),
            "uploaded_by": item.uploaded_by,
            "verified_by": item.verified_by,
            "revision": item.revision,
            "created_at": _iso(item.created_at),
        }
        for item in evidence
    ]
    requirement_rows = [
        {
            "id": item.id,
            "key": item.key,
            "title": item.title,
            "description": item.description,
            "kind": item.kind,
            "minimum": item.minimum,
            "mandatory": bool(item.mandatory),
            "source_ref": item.source_ref,
            "owner": item.owner,
            "satisfied": requirement_satisfied(item, evidence, revision.deadline),
            "revision": item.revision,
        }
        for item in requirements
    ]
    approval_rows = [
        {
            "id": item.id,
            "reviewer_id": item.reviewer_id,
            "decision": item.decision,
            "created_at": _iso(item.created_at),
        }
        for item in approvals
    ]
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "tenant_id": case.tenant_id,
        "case_id": case.id,
        "case_title": case.title,
        "case_status": "approved",
        "captured_revision": {
            "id": revision.id,
            "number": revision.number,
            "deadline": _iso(revision.deadline),
            "reason": revision.reason,
            "created_by": revision.created_by,
            "created_at": _iso(revision.created_at),
        },
        "requirements": requirement_rows,
        "evidence": evidence_rows,
        "approvals": approval_rows,
        "metrics": {
            "requirements_count": len(requirements),
            "evidence_count": len(evidence),
            "verified_evidence_count": sum(bool(item.verified) for item in evidence),
            "mandatory_requirements": sum(
                bool(item.mandatory) for item in requirements
            ),
            "verified_requirements": sum(
                requirement_satisfied(item, evidence, revision.deadline)
                for item in requirements
            ),
        },
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_row(
    case: Case, revision: Revision, payload: dict[str, Any], captured_at: str
) -> tuple[Any, ...]:
    content_hash = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    metrics = payload["metrics"]
    return (
        f"{case.tenant_id}:{case.id}:{revision.number}",
        case.tenant_id,
        case.id,
        revision.id,
        revision.number,
        "approved",
        captured_at,
        content_hash,
        HISTORY_SCHEMA_VERSION,
        _canonical(payload),
        metrics["requirements_count"],
        metrics["evidence_count"],
        metrics["verified_evidence_count"],
        metrics["mandatory_requirements"],
        metrics["verified_requirements"],
    )


def snapshot_case(
    case: Case, db: Session, revision_number: int | None = None
) -> dict[str, Any]:
    """Archive an approved immutable revision, including after a later amendment.

    A repeated snapshot must have the same hash. PostgreSQL approval and the
    frozen revision deadline, not the current mutable case status, are authoritative.
    """
    if not getattr(case, "id", None) or not getattr(case, "tenant_id", None):
        raise ProjectionError("case must have an id and tenant")
    revision = db.scalar(
        select(Revision).where(
            Revision.case_id == case.id,
            Revision.tenant_id == case.tenant_id,
            Revision.number
            == (case.current_revision if revision_number is None else revision_number),
        )
    )
    if revision is None:
        raise ProjectionError(
            f"current revision {case.current_revision} does not exist"
        )
    requirements = _bounded(
        db,
        select(Requirement)
        .where(
            Requirement.case_id == case.id,
            Requirement.tenant_id == case.tenant_id,
            Requirement.revision == revision.number,
        )
        .order_by(Requirement.key),
        "history requirements",
        MAX_HISTORY_ROWS,
    )
    evidence = _bounded(
        db,
        select(Evidence)
        .where(
            Evidence.case_id == case.id,
            Evidence.tenant_id == case.tenant_id,
            Evidence.revision == revision.number,
        )
        .order_by(Evidence.id),
        "history evidence",
        MAX_HISTORY_ROWS,
    )
    approvals = _bounded(
        db,
        select(Approval)
        .where(
            Approval.case_id == case.id,
            Approval.tenant_id == case.tenant_id,
            Approval.revision == revision.number,
        )
        .order_by(Approval.created_at, Approval.id),
        "history approvals",
        MAX_HISTORY_ROWS,
    )
    if not any(approval.decision == "approve" for approval in approvals):
        raise ProjectionError("only approved revisions may be archived")
    payload = _row_payload(case, revision, requirements, evidence, approvals)
    # Captured time is metadata, deliberately excluded from content hashing.
    captured_at = datetime.now().astimezone().isoformat()
    row = _snapshot_row(case, revision, payload, captured_at)
    root = _history_root()
    lock = _lock(root)
    temp_parquet: str | None = None
    try:
        duckdb = _duckdb()
        connection = duckdb.connect(str(root / "history.duckdb"))
        try:
            _init_history(connection)
            connection.execute("BEGIN TRANSACTION")
            existing = connection.execute(
                "SELECT content_sha256, payload_json, captured_at FROM snapshot_records WHERE snapshot_key = ?",
                [row[0]],
            ).fetchone()
            if existing is not None:
                if existing[0] != row[7]:
                    connection.execute("ROLLBACK")
                    raise SnapshotIntegrityError(
                        f"snapshot content changed for tenant={case.tenant_id!r}, case={case.id!r}, revision={revision.number}"
                    )
                connection.execute("COMMIT")
                return {
                    "snapshot_key": row[0],
                    "tenant_id": row[1],
                    "case_id": row[2],
                    "revision_id": row[3],
                    "revision_number": row[4],
                    "content_sha256": row[7],
                    "schema_version": row[8],
                    "captured_at": existing[2],
                    "idempotent": True,
                    "history_dir": str(root),
                }
            connection.execute(
                "INSERT INTO snapshot_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                list(row),
            )
            with tempfile.NamedTemporaryFile(
                prefix=".snapshots-", suffix=".parquet", dir=root, delete=False
            ) as temp:
                temp_parquet = temp.name
            connection.sql(
                "SELECT * FROM snapshot_records ORDER BY tenant_id, case_id, revision_number"
            ).write_parquet(temp_parquet, compression="zstd")
            connection.execute("COMMIT")
        except Exception:
            try:
                connection.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            connection.close()
        os.replace(temp_parquet, root / "snapshots.parquet")
        temp_parquet = None
        return {
            "snapshot_key": row[0],
            "tenant_id": row[1],
            "case_id": row[2],
            "revision_id": row[3],
            "revision_number": row[4],
            "content_sha256": row[7],
            "schema_version": row[8],
            "captured_at": row[6],
            "idempotent": False,
            "history_dir": str(root),
        }
    finally:
        if temp_parquet:
            try:
                Path(temp_parquet).unlink(missing_ok=True)
            except OSError:
                pass
        import fcntl

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def _history_query(tenant_id: str, case_id: str | None = None) -> dict[str, Any]:
    if not tenant_id:
        raise ProjectionError("tenant_id is required")
    root = _history_root()
    db_path = root / "history.duckdb"
    if not db_path.exists():
        return {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "snapshots": [],
            "aggregate": {"snapshot_count": 0, "case_count": 0},
        }
    lock = _lock(root)
    duckdb = _duckdb()
    connection = duckdb.connect(str(db_path), read_only=True)
    try:
        if not connection.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'snapshot_records'"
        ).fetchone():
            return {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "snapshots": [],
                "aggregate": {"snapshot_count": 0, "case_count": 0},
            }
        if case_id is None:
            rows = connection.execute(
                "SELECT snapshot_key, case_id, revision_id, revision_number, case_status, captured_at, content_sha256, schema_version, payload_json, requirements_count, evidence_count, verified_evidence_count, mandatory_requirements, verified_requirements FROM snapshot_records WHERE tenant_id = ? ORDER BY case_id, revision_number",
                [tenant_id],
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT snapshot_key, case_id, revision_id, revision_number, case_status, captured_at, content_sha256, schema_version, payload_json, requirements_count, evidence_count, verified_evidence_count, mandatory_requirements, verified_requirements FROM snapshot_records WHERE tenant_id = ? AND case_id = ? ORDER BY revision_number",
                [tenant_id, case_id],
            ).fetchall()
    finally:
        connection.close()
        import fcntl

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
    snapshots = [
        {
            "snapshot_key": row[0],
            "case_id": row[1],
            "revision_id": row[2],
            "revision_number": row[3],
            "case_status": row[4],
            "captured_at": row[5],
            "content_sha256": row[6],
            "schema_version": row[7],
            "payload": json.loads(row[8]),
            "metrics": {
                "requirements_count": row[9],
                "evidence_count": row[10],
                "verified_evidence_count": row[11],
                "mandatory_requirements": row[12],
                "verified_requirements": row[13],
            },
        }
        for row in rows
    ]
    return {
        "tenant_id": tenant_id,
        "case_id": case_id,
        "snapshots": snapshots,
        "aggregate": {
            "snapshot_count": len(snapshots),
            "case_count": len({item["case_id"] for item in snapshots}),
            "latest_revision": max(
                (item["revision_number"] for item in snapshots), default=None
            ),
            "verified_requirements": sum(
                item["metrics"]["verified_requirements"] for item in snapshots
            ),
        },
    }


def history_for_case(case: Case, db: Session | None = None) -> dict[str, Any]:
    """Read snapshots scoped by the case's tenant and id.

    ``db`` is accepted so API dependencies can pass the authenticated session;
    history itself is intentionally served from the same DuckDB projection.
    """
    if not getattr(case, "id", None) or not getattr(case, "tenant_id", None):
        raise ProjectionError("case must have an id and tenant")
    return _history_query(case.tenant_id, case.id)


def history_for_tenant(tenant_id: str) -> dict[str, Any]:
    """Read aggregate history for exactly one tenant."""
    return _history_query(tenant_id)


def synchronize_case(case: Case, db: Session) -> dict[str, Any]:
    """Event/background hook: project a real database case once."""
    return snapshot_case(case, db)


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize BidWeave cases into local history"
    )
    parser.add_argument("--tenant", help="only this tenant")
    parser.add_argument("--case", dest="case_id", help="only this case id")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        statement = select(Case).order_by(Case.tenant_id, Case.id)
        if args.tenant:
            statement = statement.where(Case.tenant_id == args.tenant)
        if args.case_id:
            statement = statement.where(Case.id == args.case_id)
        cases = list(db.scalars(statement).all())
        if not cases:
            raise ProjectionError("no matching cases in the configured database")
        result = [synchronize_case(case, db) for case in cases]
        print(json.dumps({"synchronized": result}, sort_keys=True))
        return 0
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover - exercised as an operational CLI
    raise SystemExit(_cli())

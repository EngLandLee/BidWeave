# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
"""Boundary tests for metadata lineage and bounded cold history."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from bidweave.db import Base, configure_engine, engine
from bidweave.models import Approval, Case, Evidence, Notice, Requirement, Revision
from bidweave.projections import (
    SnapshotIntegrityError,
    build_lineage,
    history_for_tenant,
    publish_lineage,
    snapshot_case,
)


@pytest.fixture
def db(tmp_path):
    configure_engine(f"sqlite:///{tmp_path}/projections.db")
    Base.metadata.create_all(engine())
    session = Session(engine())
    yield session
    session.close()


def _case(db, tenant: str, case_id: str):
    deadline = datetime.now(timezone.utc) + timedelta(days=14)
    case = Case(
        id=case_id,
        tenant_id=tenant,
        title="Public services tender",
        description="Bounded projection fixture",
        deadline=deadline,
        current_revision=1,
        status="approved",
        owner_id="owner",
    )
    db.add(case)
    db.flush()
    revision = Revision(
        id=f"revision-{case_id}",
        case_id=case.id,
        tenant_id=tenant,
        number=1,
        deadline=deadline,
        reason="Initial revision",
        created_by="owner",
    )
    db.add(revision)
    db.flush()
    requirement = Requirement(
        id=f"requirement-{case_id}",
        case_id=case.id,
        revision_id=revision.id,
        tenant_id=tenant,
        revision=1,
        key="insurance",
        title="Insurance certificate",
        description="Valid certificate",
        kind="document",
        mandatory=True,
        source_ref="TED:notice-1",
        owner="contributor",
    )
    evidence = Evidence(
        id=f"evidence-{case_id}",
        case_id=case.id,
        tenant_id=tenant,
        requirement_key=requirement.key,
        filename="certificate.pdf",
        sha256="a" * 64,
        object_key="private/object/one",
        verified=True,
        uploaded_by="contributor",
        verified_by="reviewer",
        revision=1,
    )
    db.add_all([requirement, evidence])
    db.add(
        Approval(
            id=f"approval-{case_id}",
            case_id=case.id,
            tenant_id=tenant,
            revision=1,
            reviewer_id="reviewer",
            decision="approve",
            comment="Reviewed",
        )
    )
    db.add(
        Notice(
            id=f"notice-{case_id}",
            case_id=case.id,
            tenant_id=tenant,
            publication_number="2026/S 001-000001",
            source_graph="https://publications.europa.eu/graph/notice-1",
        )
    )
    db.commit()
    return case


def test_lineage_uses_exact_revision_uuid_and_links_public_source(db):
    case = _case(db, "tenant-a", "case-a")
    graph = build_lineage(case, db, "https://portal.example")

    context = graph["@context"]
    assert context["@vocab"]
    assert context["epo"]
    assert context["cccev"]
    assert context["prov"]
    nodes = {node["@id"]: node for node in graph["@graph"] if "@id" in node}
    revision_id = "https://portal.example/api/cases/case-a/revisions/revision-case-a"
    requirement_id = (
        "https://portal.example/api/cases/case-a/requirements/requirement-case-a"
    )
    evidence_id = "https://portal.example/api/cases/case-a/evidence/evidence-case-a"
    assert revision_id in nodes
    assert nodes[revision_id]["bw:revisionNumber"] == 1
    assert nodes[requirement_id]["bw:revision"] == {"@id": revision_id}
    assert nodes[requirement_id]["bw:hasEvidence"] == [{"@id": evidence_id}]
    assert nodes[evidence_id]["bw:revision"] == {"@id": revision_id}
    assert not any("revision:1" in str(node) for node in graph["@graph"])
    assert any(
        node.get("@id") == "https://publications.europa.eu/graph/notice-1"
        for node in graph["@graph"]
    )


def test_snapshot_is_idempotent_and_detects_in_place_changes(db, tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DIR", str(tmp_path / "history"))
    case = _case(db, "tenant-a", "case-a")

    first = snapshot_case(case, db)
    second = snapshot_case(case, db)
    assert first["content_sha256"] == second["content_sha256"]
    assert second["idempotent"] is True

    evidence = db.query(Evidence).filter_by(case_id=case.id).one()
    evidence.verified = False
    db.commit()
    with pytest.raises(SnapshotIntegrityError):
        snapshot_case(case, db)


def test_history_queries_preserve_tenant_isolation(db, tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DIR", str(tmp_path / "history"))
    first = _case(db, "tenant-a", "case-a")
    _case(db, "tenant-b", "case-b")
    snapshot_case(first, db)
    second = db.query(Case).filter_by(id="case-b").one()
    snapshot_case(second, db)

    history = history_for_tenant("tenant-a")
    assert history["aggregate"]["case_count"] == 1
    assert [item["case_id"] for item in history["snapshots"]] == ["case-a"]

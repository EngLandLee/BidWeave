# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed regression tests; no warranty.
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session
from bidweave.db import Base, configure_engine, engine
from bidweave.models import Case, Evidence, Requirement, Revision
from bidweave.domain import evaluate, create_revision


@pytest.fixture
def db(tmp_path):
    configure_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine())
    session = Session(engine())
    yield session
    session.close()


def test_count_and_validity_require_independent_verification(db):
    deadline = datetime.now(timezone.utc) + timedelta(days=10)
    case = Case(tenant_id="t", title="x", deadline=deadline, owner_id="owner")
    db.add(case)
    db.flush()
    revision = Revision(
        case_id=case.id,
        tenant_id="t",
        number=1,
        deadline=deadline,
        reason="Initial requirements",
        created_by="owner",
    )
    db.add(revision)
    db.flush()
    req_count = Requirement(
        case_id=case.id,
        tenant_id="t",
        revision=1,
        key="count",
        title="Count",
        description="",
        kind="count",
        minimum=2,
        mandatory=True,
        source_ref="s",
        owner="o",
    )
    req_valid = Requirement(
        case_id=case.id,
        tenant_id="t",
        revision=1,
        key="valid",
        title="Valid",
        description="",
        kind="validity",
        minimum=None,
        mandatory=True,
        source_ref="s",
        owner="o",
    )
    req_count.revision_id = revision.id
    req_valid.revision_id = revision.id
    db.add_all([req_count, req_valid])
    db.flush()
    evidence = [
        Evidence(
            case_id=case.id,
            tenant_id="t",
            requirement_key="count",
            filename="a",
            sha256="a" * 64,
            object_key="a",
            quantity=2,
            uploaded_by="u",
            revision=1,
            verified=False,
        ),
        Evidence(
            case_id=case.id,
            tenant_id="t",
            requirement_key="valid",
            filename="b",
            sha256="b" * 64,
            object_key="b",
            valid_until=deadline + timedelta(days=1),
            uploaded_by="u",
            revision=1,
            verified=True,
        ),
    ]
    db.add_all(evidence)
    db.flush()
    assert evaluate(case, 1, [req_count, req_valid], evidence) == {
        "count": False,
        "valid": True,
    }
    evidence[0].verified = True
    assert evaluate(case, 1, [req_count, req_valid], evidence)["count"] is True


def test_stale_revision_rejected(db):
    case = Case(
        tenant_id="t",
        title="x",
        deadline=datetime.now(timezone.utc) + timedelta(days=10),
        owner_id="owner",
        current_revision=1,
    )
    db.add(case)
    db.commit()
    with pytest.raises(Exception) as error:
        create_revision(db, case, 0, case.deadline, "stale", [], "owner")
    assert getattr(error.value, "status_code", None) == 409


def test_historical_reference_cannot_verify_reviewers_own_current_upload(db):
    from fastapi import HTTPException
    from bidweave.auth import Principal
    from bidweave.main import verify_evidence
    from bidweave.schemas import EvidenceVerify, RequirementInput

    deadline = datetime(2030, 1, 1, tzinfo=timezone.utc)
    case = Case(
        tenant_id="t",
        title="Independent verification",
        deadline=deadline,
        owner_id="owner",
    )
    db.add(case)
    db.flush()
    inputs = [
        RequirementInput(
            key="EXP",
            title="Experience",
            kind="count",
            minimum=2,
            mandatory=True,
            source_ref="document:terms#page:1",
            owner="owner",
        )
    ]
    create_revision(db, case, 0, deadline, "initial", inputs, "owner")
    previous = Evidence(
        case_id=case.id,
        tenant_id="t",
        requirement_key="EXP",
        filename="proof.txt",
        sha256="a" * 64,
        object_key="proof",
        quantity=1,
        uploaded_by="contributor",
        revision=1,
    )
    db.add(previous)
    db.flush()
    create_revision(db, case, 1, deadline, "amendment", inputs, "owner")
    current = Evidence(
        case_id=case.id,
        tenant_id="t",
        requirement_key="EXP",
        filename="proof.txt",
        sha256="a" * 64,
        object_key="proof",
        quantity=99,
        uploaded_by="reviewer",
        revision=2,
    )
    db.add(current)
    db.commit()
    reviewer = Principal(
        id="reviewer",
        username="reviewer",
        tenant_id="t",
        roles=frozenset({"reviewer"}),
        token="test-only",
    )
    with pytest.raises(HTTPException) as error:
        verify_evidence(
            case.id, previous.id, EvidenceVerify(expected_revision=2), db, reviewer
        )
    assert error.value.status_code == 403
    assert current.verified is False


def test_approved_notice_provenance_requires_new_revision(db, monkeypatch):
    from fastapi import HTTPException
    from bidweave.auth import Principal
    from bidweave.main import notice
    from bidweave.schemas import NoticeCreate

    case = Case(
        tenant_id="t",
        title="Approved",
        deadline=datetime(2030, 1, 1, tzinfo=timezone.utc),
        owner_id="owner",
        status="approved",
        current_revision=1,
    )
    db.add(case)
    db.commit()
    monkeypatch.setattr(
        "bidweave.main.fetch_ted_notice", lambda number: "https://example.org/notice"
    )
    owner = Principal(
        id="owner",
        username="owner",
        tenant_id="t",
        roles=frozenset({"coordinator"}),
        token="test-only",
    )
    with pytest.raises(HTTPException) as error:
        notice(case.id, NoticeCreate(publication_number="00668268-2024"), db, owner)
    assert error.value.status_code == 409


def test_receipt_rechecks_revision_at_final_write(db):
    from fastapi import HTTPException
    from sqlalchemy import select
    from bidweave.auth import Principal
    from bidweave.automation import record_receipt
    from bidweave.models import Approval, Comment
    from bidweave.schemas import SubmitRequest

    case = Case(
        tenant_id="t",
        title="Automation race",
        deadline=datetime(2030, 1, 1, tzinfo=timezone.utc),
        owner_id="owner",
        status="approved",
        current_revision=1,
    )
    db.add(case)
    db.flush()
    approval = Approval(
        case_id=case.id,
        tenant_id="t",
        revision=1,
        reviewer_id="reviewer",
        decision="approve",
    )
    db.add(approval)
    db.commit()
    actor = Principal(
        id="owner",
        username="owner",
        tenant_id="t",
        roles=("coordinator",),
        token="test-only",
    )
    receipt = record_receipt(case.id, SubmitRequest(expected_revision=1), db, actor)
    assert approval.id in receipt.body
    # n8n observed R1, but an amendment wins before its final POST.
    case.current_revision = 2
    case.status = "draft"
    db.commit()
    with pytest.raises(HTTPException) as changed:
        record_receipt(case.id, SubmitRequest(expected_revision=1), db, actor)
    assert changed.value.status_code == 409
    # Even a later approval of R2 must not validate the stale R1 request.
    case.status = "approved"
    db.add(
        Approval(
            case_id=case.id,
            tenant_id="t",
            revision=2,
            reviewer_id="reviewer",
            decision="approve",
        )
    )
    db.commit()
    with pytest.raises(HTTPException) as stale:
        record_receipt(case.id, SubmitRequest(expected_revision=1), db, actor)
    assert stale.value.status_code == 409
    assert list(db.scalars(select(Comment.id).where(Comment.case_id == case.id))) == [
        receipt.id
    ]

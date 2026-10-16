# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed domain behavior; no warranty.
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, re
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from .models import (
    Case,
    Revision,
    Requirement,
    Evidence,
    Task,
    Comment,
    Approval,
    Impact,
    Notice,
    AuditEvent,
    OutboxEvent,
)
from .schemas import RequirementInput
from .auth import Principal


def tenant_case(db: Session, case_id: str, user: Principal, lock: bool = False) -> Case:
    query = select(Case).where(Case.id == case_id, Case.tenant_id == user.tenant_id)
    if lock:
        query = query.with_for_update()
    case = db.scalar(query)
    if case is None:
        raise HTTPException(404, "case not found")
    return case


def utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def requirement_satisfied(
    req: Requirement, evidence: list[Evidence], deadline: datetime
) -> bool:
    matching = {}
    for item in evidence:
        if item.requirement_key == req.key and item.verified:
            matching.setdefault(item.sha256, item)
    verified = list(matching.values())
    if req.kind == "count":
        return sum((e.quantity or 0) for e in verified) >= (req.minimum or 0)
    if req.kind == "validity":
        return any(
            e.valid_until is not None and utc(e.valid_until) >= utc(deadline)
            for e in verified
        )
    return bool(verified)


def evaluate(
    case: Case, revision: int, requirements: list[Requirement], evidence: list[Evidence]
) -> dict[str, bool]:
    return {
        r.key: requirement_satisfied(
            r, [e for e in evidence if e.revision == revision], case.deadline
        )
        for r in requirements
        if r.revision == revision
    }


def append_audit(
    db: Session,
    tenant: str,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
) -> AuditEvent:
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:tenant))"), {"tenant": tenant}
        )
    db.flush()
    previous = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == tenant)
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    previous_hash = previous.hash if previous else ""
    serial = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        (
            previous_hash + tenant + actor + action + entity_type + entity_id + serial
        ).encode()
    ).hexdigest()
    event = AuditEvent(
        tenant_id=tenant,
        actor_id=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=serial,
        previous_hash=previous_hash,
        hash=digest,
    )
    db.add(event)
    return event


def enqueue(db: Session, tenant: str, subject: str, payload: dict) -> None:
    db.add(
        OutboxEvent(
            tenant_id=tenant,
            subject=subject,
            payload=json.dumps(payload, sort_keys=True),
        )
    )


def create_revision(
    db: Session,
    case: Case,
    expected: int,
    deadline: datetime,
    reason: str,
    inputs: list[RequirementInput],
    actor: str,
) -> None:
    if case.current_revision != expected:
        raise HTTPException(409, "stale revision")
    if utc(deadline) <= datetime.now(timezone.utc):
        raise HTTPException(422, "deadline must be in the future")
    keys = [x.key for x in inputs]
    if len(keys) != len(set(keys)):
        raise HTTPException(422, "requirement keys must be unique")
    if any(x.kind == "count" and x.minimum is None for x in inputs):
        raise HTTPException(422, "count requirements need minimum")
    old = {
        r.key: r
        for r in db.scalars(
            select(Requirement).where(
                Requirement.case_id == case.id, Requirement.revision == expected
            )
        )
    }
    old_revision = db.scalar(
        select(Revision).where(Revision.case_id == case.id, Revision.number == expected)
    )
    deadline_changed = old_revision is not None and utc(old_revision.deadline) != utc(
        deadline
    )
    number = expected + 1
    revision = Revision(
        case_id=case.id,
        tenant_id=case.tenant_id,
        number=number,
        deadline=deadline,
        reason=reason,
        created_by=actor,
    )
    db.add(revision)
    db.flush()
    for item in inputs:
        req = Requirement(
            case_id=case.id,
            revision_id=revision.id,
            tenant_id=case.tenant_id,
            revision=number,
            key=item.key,
            title=item.title,
            description=item.description,
            kind=item.kind,
            minimum=item.minimum,
            mandatory=item.mandatory,
            source_ref=item.source_ref,
            owner=item.owner,
        )
        db.add(req)
        before = old.get(item.key)
        semantic_change = before is None or (
            before.description.strip() != item.description.strip()
            or before.source_ref != item.source_ref
            or before.kind != item.kind
            or before.minimum != item.minimum
            or before.mandatory != item.mandatory
        )
        if semantic_change or deadline_changed:
            impact_kind = (
                "added"
                if before is None
                else ("changed" if semantic_change else "deadline_changed")
            )
            changes = []
            if before is None:
                changes.append("Yêu cầu mới, chưa được xác nhận")
            else:
                for field, label in (
                    ("kind", "Loại"),
                    ("minimum", "Ngưỡng số lượng"),
                    ("mandatory", "Bắt buộc"),
                    ("source_ref", "Vị trí nguồn"),
                    ("description", "Nội dung"),
                ):
                    previous_value, next_value = (
                        getattr(before, field),
                        getattr(item, field),
                    )
                    if field == "description":
                        previous_value, next_value = (
                            previous_value.strip(),
                            next_value.strip(),
                        )
                    if previous_value != next_value:
                        changes.append(
                            f"{label}: {json.dumps(previous_value, ensure_ascii=False)} → {json.dumps(next_value, ensure_ascii=False)}"
                        )
            if deadline_changed:
                changes.append(
                    f"Hạn nộp (UTC): {utc(old_revision.deadline).isoformat()} → {utc(deadline).isoformat()}"
                )
            detail = (
                "; ".join(changes) + ". Cần đối chiếu minh chứng cho phiên bản này."
            )
            impact = Impact(
                case_id=case.id,
                tenant_id=case.tenant_id,
                revision=number,
                requirement_key=item.key,
                kind=impact_kind,
                detail=detail,
            )
            db.add(impact)
            db.add(
                Task(
                    case_id=case.id,
                    tenant_id=case.tenant_id,
                    revision=number,
                    requirement_key=item.key,
                    title=f"Rà soát yêu cầu: {item.title}",
                )
            )
    removed = set(old) - set(keys)
    for key in removed:
        db.add(
            Impact(
                case_id=case.id,
                tenant_id=case.tenant_id,
                revision=number,
                requirement_key=key,
                kind="removed",
                detail="Yêu cầu đã bị bỏ khỏi phiên bản hiện tại; lịch sử trước đó vẫn được giữ.",
            )
        )
    case.current_revision = number
    case.deadline = deadline
    case.status = "draft"
    append_audit(
        db,
        case.tenant_id,
        actor,
        "revision.created",
        "case",
        case.id,
        {"revision": number, "reason": reason},
    )
    enqueue(
        db,
        case.tenant_id,
        "bidweave.revision.created",
        {"case_id": case.id, "revision": number},
    )


def requirement_payload(req: Requirement, evidence: list[Evidence]) -> dict:
    return {
        "id": req.id,
        "key": req.key,
        "title": req.title,
        "description": req.description,
        "kind": req.kind,
        "minimum": req.minimum,
        "mandatory": req.mandatory,
        "source_ref": req.source_ref,
        "owner": req.owner,
        "revision": req.revision,
        "status": req.status,
        "evidence_ids": [
            e.id
            for e in evidence
            if e.requirement_key == req.key and e.revision == req.revision
        ],
    }


def detail_payload(case: Case, db: Session, workflow_id: str | None = None) -> dict:
    if workflow_id is None:
        pending = db.scalar(
            select(Approval)
            .where(
                Approval.case_id == case.id,
                Approval.revision == case.current_revision,
                Approval.decision == "pending",
            )
            .order_by(Approval.created_at.desc())
        )
        workflow_id = pending.workflow_id if pending else None
    reqs = list(
        db.scalars(
            select(Requirement)
            .where(
                Requirement.case_id == case.id,
                Requirement.revision == case.current_revision,
            )
            .order_by(Requirement.key)
        )
    )
    evidence = list(
        db.scalars(
            select(Evidence)
            .where(Evidence.case_id == case.id)
            .order_by(Evidence.created_at)
        )
    )
    statuses = evaluate(case, case.current_revision, reqs, evidence)
    for req in reqs:
        req.status = (
            "verified"
            if statuses.get(req.key)
            else (
                "needs_review"
                if any(
                    e.requirement_key == req.key and e.revision == case.current_revision
                    for e in evidence
                )
                else "missing"
            )
        )
    return {
        "id": case.id,
        "title": case.title,
        "description": case.description,
        "deadline": case.deadline,
        "current_revision": case.current_revision,
        "status": case.status,
        "owner_id": case.owner_id,
        "created_at": case.created_at,
        "requirements": [requirement_payload(r, evidence) for r in reqs],
        "evidence": evidence,
        "tasks": list(
            db.scalars(
                select(Task).where(Task.case_id == case.id).order_by(Task.created_at)
            )
        ),
        "comments": list(
            db.scalars(
                select(Comment)
                .where(Comment.case_id == case.id)
                .order_by(Comment.created_at)
            )
        ),
        "revisions": list(
            db.scalars(
                select(Revision)
                .where(Revision.case_id == case.id)
                .order_by(Revision.number)
            )
        ),
        "approvals": list(
            db.scalars(
                select(Approval)
                .where(Approval.case_id == case.id)
                .order_by(Approval.created_at)
            )
        ),
        "impact": list(
            db.scalars(
                select(Impact)
                .where(Impact.case_id == case.id)
                .order_by(Impact.created_at)
            )
        ),
        "workflow_id": workflow_id,
    }


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("unsafe filename")
    return cleaned[:180]

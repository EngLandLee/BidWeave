# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed governance endpoints; no warranty.
"""Tenant-scoped governance search and audit-chain verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from .auth import Principal, current_user, require_role
from .db import get_db
from .models import AuditEvent, Case, Requirement

router = APIRouter()


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    head_hash: str
    broken_event_id: str | None = None


def _event_hash(event: AuditEvent) -> str:
    """Recompute the digest format used by :func:`domain.append_audit`."""
    material = (
        event.previous_hash
        + event.tenant_id
        + event.actor_id
        + event.action
        + event.entity_type
        + event.entity_id
        + event.payload
    )
    return sha256(material.encode()).hexdigest()


def _sort_key(event: AuditEvent) -> tuple[str, str]:
    """Order events deterministically, including SQLite-style naive datetimes."""
    timestamp = event.created_at
    if timestamp is None:
        normalized = ""
    elif timestamp.tzinfo is None:
        normalized = timestamp.replace(tzinfo=timezone.utc).isoformat()
    else:
        normalized = timestamp.astimezone(timezone.utc).isoformat()
    return normalized, event.id


def verify_audit_chain(events: Iterable[AuditEvent]) -> ChainVerification:
    """Verify one already tenant-filtered audit chain.

    ``append_audit`` links each event to the latest event for that tenant.
    Following those links (rather than relying on timestamp uniqueness) detects
    a missing parent, a fork, or a payload/field mutation without treating a
    hash as a non-repudiation signature.
    """
    ordered = sorted(events, key=_sort_key)
    if not ordered:
        return ChainVerification(valid=True, head_hash="")

    reported_head = ordered[-1].hash
    by_hash: dict[str, AuditEvent] = {}
    for event in ordered:
        if event.hash in by_hash or _event_hash(event) != event.hash:
            return ChainVerification(False, reported_head, event.id)
        by_hash[event.hash] = event

    roots = [event for event in ordered if event.previous_hash == ""]
    if not roots:
        return ChainVerification(False, reported_head, ordered[0].id)
    if len(roots) > 1:
        return ChainVerification(False, reported_head, roots[1].id)

    children: dict[str, list[AuditEvent]] = {}
    for event in ordered:
        if event.previous_hash and event.previous_hash not in by_hash:
            return ChainVerification(False, reported_head, event.id)
        if event.previous_hash:
            children.setdefault(event.previous_hash, []).append(event)
    for siblings in children.values():
        if len(siblings) > 1:
            siblings.sort(key=_sort_key)
            return ChainVerification(False, reported_head, siblings[1].id)

    visited: set[str] = set()
    current = roots[0]
    while True:
        if current.hash in visited:
            return ChainVerification(False, reported_head, current.id)
        visited.add(current.hash)
        next_events = children.get(current.hash)
        if not next_events:
            return (
                ChainVerification(True, current.hash)
                if len(visited) == len(ordered)
                else ChainVerification(
                    False,
                    reported_head,
                    next(event.id for event in ordered if event.hash not in visited),
                )
            )
        current = next_events[0]


@router.get("/search/requirements")
def search_requirements(
    q: str = Query(..., min_length=1, max_length=120),
    db: Session = Depends(get_db),
    user: Principal = Depends(current_user),
):
    """Search current- revision requirements in the caller's tenant."""
    if db.get_bind().dialect.name != "postgresql":
        raise HTTPException(
            status_code=503, detail="PostgreSQL requirement search unavailable"
        )

    regconfig = literal_column("'simple'::regconfig")
    vector = func.to_tsvector(
        regconfig,
        func.concat_ws(
            " ",
            Requirement.key,
            Requirement.title,
            Requirement.description,
            Requirement.source_ref,
        ),
    )
    query = (
        select(
            Case.id.label("case_id"),
            Case.title.label("case_title"),
            Requirement.key.label("requirement_key"),
            Requirement.title.label("title"),
            Requirement.source_ref.label("source_ref"),
        )
        .join(Requirement, Requirement.case_id == Case.id)
        .where(
            Case.tenant_id == user.tenant_id,
            Requirement.tenant_id == user.tenant_id,
            Requirement.revision == Case.current_revision,
            vector.op("@@")(func.plainto_tsquery(regconfig, q)),
        )
        .order_by(Case.title.asc(), Requirement.key.asc())
        .limit(50)
    )
    rows = db.execute(query).mappings().all()
    return {
        "query": q,
        "results": [
            {
                "case_id": row["case_id"],
                "case_title": row["case_title"],
                "requirement_key": row["requirement_key"],
                "title": row["title"],
                "source_ref": row["source_ref"],
            }
            for row in rows
        ],
    }


@router.get("/audit/verify")
def verify_audit(
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("coordinator")),
):
    """Verify the caller tenant's audit chain and expose only its summary."""
    events = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == user.tenant_id)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        )
    )
    result = verify_audit_chain(events)
    payload = {
        "valid": result.valid,
        "event_count": len(events),
        "head_hash": result.head_hash,
    }
    if result.broken_event_id is not None:
        payload["broken_event_id"] = result.broken_event_id
    return payload

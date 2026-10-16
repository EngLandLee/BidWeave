# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Licensed under Apache-2.0; see LICENSE. No warranties.
"""Explicit, authenticated optional automation; Flowable remains authoritative."""

import os
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import Principal, require_role
from .db import get_db
from .domain import append_audit, tenant_case
from .models import Approval, Comment
from .schemas import CommentOut, SubmitRequest

router = APIRouter()


@router.post("/cases/{case_id}/automation/receipt")
def send_receipt(
    case_id: str,
    body: SubmitRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("coordinator")),
):
    case = tenant_case(db, case_id, user)
    if case.status != "approved" or case.current_revision != body.expected_revision:
        raise HTTPException(409, "receipt requires the currently approved revision")
    endpoint = os.getenv("N8N_WEBHOOK_URL", "").strip()
    if not endpoint:
        raise HTTPException(
            503, "n8n connector is not configured; enable the automation profile"
        )
    # The short-lived caller credential is forwarded only to the operator-configured
    # internal connector, never persisted in an outbox, workflow definition or LLM input.
    try:
        response = httpx.post(
            endpoint,
            headers={"Authorization": "Bearer " + user.token},
            json={"case_id": case.id, "revision": body.expected_revision},
            timeout=45,
        )
        response.raise_for_status()
        result = response.json()
        comment_id = str(UUID(result["comment_id"]))
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            503, "n8n did not confirm a workspace receipt; the approval is unchanged"
        ) from error
    if (
        result.get("performed") != "posted_workspace_receipt"
        or result.get("case_id") != case.id
        or result.get("revision") != body.expected_revision
    ):
        raise HTTPException(502, "n8n returned a mismatched receipt")
    comment = db.scalar(
        select(Comment).where(
            Comment.id == comment_id,
            Comment.case_id == case.id,
            Comment.tenant_id == user.tenant_id,
        )
    )
    if comment is None:
        raise HTTPException(
            502, "receipt does not exist in the authoritative workspace"
        )
    return {
        "performed": "posted_workspace_receipt",
        "comment_id": comment.id,
        "case_id": case.id,
        "revision": body.expected_revision,
    }


@router.post(
    "/cases/{case_id}/automation/receipt-record",
    response_model=CommentOut,
    status_code=201,
)
def record_receipt(
    case_id: str,
    body: SubmitRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("coordinator")),
):
    # The final write must share the revision lock, not rely on n8n's earlier GET.
    case = tenant_case(db, case_id, user, lock=True)
    if case.status != "approved" or case.current_revision != body.expected_revision:
        raise HTTPException(409, "receipt requires the currently approved revision")
    approval = db.scalar(
        select(Approval).where(
            Approval.case_id == case.id,
            Approval.tenant_id == user.tenant_id,
            Approval.revision == body.expected_revision,
            Approval.decision == "approve",
        )
    )
    if approval is None:
        raise HTTPException(409, "approval evidence is missing")
    comment = Comment(
        case_id=case.id,
        tenant_id=user.tenant_id,
        author=user.id,
        body=f"Biên nhận đồng bộ: R{body.expected_revision} đã được duyệt tại thời điểm đối soát. "
        f"Tham chiếu quyết định: {approval.id}. Đây không phải email hay biên nhận nộp thầu.",
    )
    db.add(comment)
    db.flush()
    append_audit(
        db,
        user.tenant_id,
        user.id,
        "automation.receipt.recorded",
        "case",
        case.id,
        {
            "revision": body.expected_revision,
            "approval_id": approval.id,
            "comment_id": comment.id,
        },
    )
    db.commit()
    return comment

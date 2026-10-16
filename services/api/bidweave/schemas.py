# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed API schemas; no warranty.
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class User(BaseModel):
    id: str
    username: str
    tenant_id: str
    roles: list[str]


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    deadline: datetime
    description: str | None = None


class RequirementInput(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    kind: Literal["document", "count", "validity", "text"]
    minimum: int | None = Field(default=None, ge=0)
    mandatory: bool = True
    source_ref: str = Field(min_length=1, max_length=1000)
    owner: str = Field(min_length=1, max_length=255)


class RevisionCreate(BaseModel):
    expected_revision: int = Field(ge=0)
    deadline: datetime
    reason: str = Field(min_length=1)
    requirements: list[RequirementInput]


class EvidenceVerify(BaseModel):
    expected_revision: int = Field(ge=0)


class SubmitRequest(BaseModel):
    expected_revision: int = Field(ge=0)


class ReviewRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    decision: Literal["approve", "reject"]
    comment: str = ""


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class TaskPatch(BaseModel):
    status: Literal["open", "done"]
    assignee: str | None = None


class NoticeCreate(BaseModel):
    publication_number: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9./_-]{2,254}$")


class RequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    title: str
    description: str
    kind: str
    minimum: int | None
    mandatory: bool
    source_ref: str
    owner: str
    revision: int
    status: str
    evidence_ids: list[str] = []


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    requirement_key: str
    filename: str
    sha256: str
    valid_until: datetime | None
    quantity: int | None
    notes: str | None
    verified: bool
    uploaded_by: str
    revision: int
    created_at: datetime


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision: int
    requirement_key: str
    title: str
    status: str
    assignee: str | None
    created_at: datetime


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    author: str
    body: str
    created_at: datetime


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    number: int
    deadline: datetime
    reason: str
    created_by: str
    created_at: datetime


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision: int
    reviewer_id: str
    decision: str
    comment: str
    workflow_id: str | None
    created_at: datetime


class ImpactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    revision: int
    requirement_key: str
    kind: str
    detail: str
    created_at: datetime


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: str | None
    deadline: datetime
    current_revision: int
    status: str
    owner_id: str
    created_at: datetime


class CaseDetail(CaseOut):
    requirements: list[RequirementOut]
    evidence: list[EvidenceOut]
    tasks: list[TaskOut]
    comments: list[CommentOut]
    revisions: list[RevisionOut]
    approvals: list[ApprovalOut]
    impact: list[ImpactOut]
    workflow_id: str | None = None


class Analytics(BaseModel):
    case_count: int
    approved_count: int
    pending_review_count: int
    open_tasks: int
    requirements_count: int
    verified_requirements: int
    events: list[dict]

# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed API; no warranty.
from __future__ import annotations
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json, tarfile
from fastapi import (
    FastAPI,
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db, init_db
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
)
from .schemas import (
    CaseCreate,
    CaseOut,
    CaseDetail,
    RevisionCreate,
    EvidenceOut,
    EvidenceVerify,
    SubmitRequest,
    ReviewRequest,
    CommentCreate,
    CommentOut,
    TaskPatch,
    Analytics,
    NoticeCreate,
    User,
)
from .auth import Principal, current_user, require_role
from .adapters import (
    ClamAVScanner,
    DependencyUnavailable,
    FlowableClient,
    fetch_ted_notice,
    object_store,
)
from .domain import (
    append_audit,
    create_revision,
    detail_payload,
    enqueue,
    evaluate,
    safe_filename,
    utc,
    tenant_case,
)
from .projections import (
    build_lineage,
    publish_lineage,
    history_for_case,
    ProjectionError,
)
from .observability import configure_observability


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        yield
    finally:
        if telemetry is not None:
            for provider in telemetry:
                provider.shutdown()


app = FastAPI(title="BidWeave API", version="1.1.0", lifespan=lifespan)
telemetry = configure_observability(app)
api = APIRouter(prefix="/api")


@api.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
    except Exception as exc:
        raise HTTPException(503, "database unavailable") from exc
    return {"status": "ok", "database": "ok"}


@api.get("/me", response_model=User)
def me(user: Principal = Depends(current_user)):
    return User(
        id=user.id,
        username=user.username,
        tenant_id=user.tenant_id,
        roles=list(user.roles),
    )


def commit_or_rollback(db: Session):
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@api.get("/cases", response_model=list[CaseOut])
def list_cases(db: Session = Depends(get_db), user: Principal = Depends(current_user)):
    return list(
        db.scalars(
            select(Case)
            .where(Case.tenant_id == user.tenant_id)
            .order_by(Case.created_at.desc())
        )
    )


@api.post("/cases", response_model=CaseOut, status_code=201)
def create_case(
    body: CaseCreate,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("coordinator")),
):
    if utc(body.deadline) <= datetime.now(timezone.utc):
        raise HTTPException(422, "deadline must be in the future")
    case = Case(
        tenant_id=user.tenant_id,
        title=body.title,
        description=body.description,
        deadline=body.deadline,
        owner_id=user.id,
    )
    db.add(case)
    db.flush()
    append_audit(
        db,
        user.tenant_id,
        user.id,
        "case.created",
        "case",
        case.id,
        {"title": case.title},
    )
    enqueue(db, user.tenant_id, "bidweave.case.created", {"case_id": case.id})
    commit_or_rollback(db)
    return case


@api.get("/cases/{case_id}", response_model=CaseDetail)
def get_case(
    case_id: str, db: Session = Depends(get_db), user: Principal = Depends(current_user)
):
    return detail_payload(tenant_case(db, case_id, user), db)


@api.post("/cases/{case_id}/revisions", response_model=CaseDetail)
def revision(
    case_id: str,
    body: RevisionCreate,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("coordinator")),
):
    case = tenant_case(db, case_id, user, lock=True)
    if body.expected_revision != case.current_revision:
        raise HTTPException(409, "stale revision")
    if utc(body.deadline) <= datetime.now(timezone.utc):
        raise HTTPException(422, "deadline must be in the future")
    keys = [item.key for item in body.requirements]
    if len(keys) != len(set(keys)):
        raise HTTPException(422, "requirement keys must be unique")
    if any(item.kind == "count" and item.minimum is None for item in body.requirements):
        raise HTTPException(422, "count requirements need minimum")
    if case.status == "in_review":
        pending = db.scalar(
            select(Approval)
            .where(
                Approval.case_id == case.id,
                Approval.revision == case.current_revision,
                Approval.decision == "pending",
            )
            .order_by(Approval.created_at.desc())
        )
        if pending is None or not pending.workflow_id:
            raise HTTPException(409, "active workflow not found")
        try:
            FlowableClient().delete(pending.workflow_id)
        except DependencyUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        pending.decision = "superseded"
        pending.comment = "Superseded by a new revision"
        append_audit(
            db,
            user.tenant_id,
            user.id,
            "review.superseded",
            "approval",
            pending.id,
            {"revision": pending.revision, "workflow_id": pending.workflow_id},
        )
    create_revision(
        db,
        case,
        body.expected_revision,
        body.deadline,
        body.reason,
        body.requirements,
        user.id,
    )
    commit_or_rollback(db)
    return detail_payload(case, db)


@api.post("/cases/{case_id}/evidence", response_model=EvidenceOut, status_code=201)
async def upload_evidence(
    case_id: str,
    file: UploadFile = File(...),
    requirement_key: str = Form(...),
    expected_revision: int = Form(...),
    valid_until: datetime | None = Form(None),
    quantity: int | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    user: Principal = Depends(current_user),
):
    case = tenant_case(db, case_id, user, lock=True)
    if expected_revision != case.current_revision:
        raise HTTPException(409, "stale revision")
    if case.status == "approved":
        raise HTTPException(409, "approved revision is immutable")
    req = db.scalar(
        select(Requirement).where(
            Requirement.case_id == case.id,
            Requirement.revision == case.current_revision,
            Requirement.key == requirement_key,
        )
    )
    if req is None:
        raise HTTPException(422, "requirement does not exist in current revision")
    if quantity is not None and quantity < 0:
        raise HTTPException(422, "quantity must not be negative")
    content = await file.read(get_settings().max_upload_bytes + 1)
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(422, "file exceeds upload limit")
    try:
        ClamAVScanner().scan(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except DependencyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    digest = sha256(content).hexdigest()
    if (
        db.scalar(
            select(Evidence).where(
                Evidence.case_id == case.id,
                Evidence.revision == case.current_revision,
                Evidence.sha256 == digest,
            )
        )
        is not None
    ):
        raise HTTPException(409, "duplicate evidence content for this revision")
    try:
        filename = safe_filename(file.filename or "upload")
    except ValueError as exc:
        raise HTTPException(422, "unsafe filename") from exc
    key = f"{user.tenant_id}/{case.id}/{case.current_revision}/{digest}-{filename}"
    try:
        object_store().put(
            key, content, file.content_type or "application/octet-stream"
        )
    except DependencyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    evidence = Evidence(
        case_id=case.id,
        tenant_id=user.tenant_id,
        requirement_key=requirement_key,
        filename=filename,
        sha256=digest,
        object_key=key,
        valid_until=valid_until,
        quantity=quantity,
        notes=notes,
        uploaded_by=user.id,
        revision=case.current_revision,
    )
    db.add(evidence)
    db.flush()
    append_audit(
        db,
        user.tenant_id,
        user.id,
        "evidence.uploaded",
        "evidence",
        evidence.id,
        {"sha256": digest, "revision": case.current_revision},
    )
    enqueue(
        db,
        user.tenant_id,
        "bidweave.evidence.uploaded",
        {"case_id": case.id, "evidence_id": evidence.id},
    )
    commit_or_rollback(db)
    return evidence


@api.post("/cases/{case_id}/evidence/{evidence_id}/verify", response_model=CaseDetail)
def verify_evidence(
    case_id: str,
    evidence_id: str,
    body: EvidenceVerify,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("reviewer")),
):
    case = tenant_case(db, case_id, user, lock=True)
    if body.expected_revision != case.current_revision:
        raise HTTPException(409, "stale revision")
    if case.status == "approved":
        raise HTTPException(409, "approved revision is immutable")
    evidence = db.scalar(
        select(Evidence).where(Evidence.id == evidence_id, Evidence.case_id == case.id)
    )
    if evidence is None:
        raise HTTPException(404, "evidence not found")
    if evidence.uploaded_by == user.id:
        raise HTTPException(403, "uploader cannot verify own evidence")
    # Historical evidence is never silently carried forward.  A reviewer explicitly
    # verifying it creates a current-revision attachment while preserving the original.
    target = evidence
    if evidence.revision != case.current_revision:
        existing_same = db.scalar(
            select(Evidence).where(
                Evidence.case_id == case.id,
                Evidence.revision == case.current_revision,
                Evidence.sha256 == evidence.sha256,
            )
        )
        if (
            existing_same is not None
            and existing_same.requirement_key != evidence.requirement_key
        ):
            raise HTTPException(
                409, "evidence content already attached to another current requirement"
            )
        target = existing_same
        if target is None:
            target = Evidence(
                case_id=case.id,
                tenant_id=user.tenant_id,
                requirement_key=evidence.requirement_key,
                filename=evidence.filename,
                sha256=evidence.sha256,
                object_key=evidence.object_key,
                valid_until=evidence.valid_until,
                quantity=evidence.quantity,
                notes=evidence.notes,
                uploaded_by=evidence.uploaded_by,
                revision=case.current_revision,
            )
            db.add(target)
            db.flush()
    if target.uploaded_by == user.id:
        raise HTTPException(403, "uploader cannot verify own evidence")
    if (
        db.scalar(
            select(Requirement.id).where(
                Requirement.case_id == case.id,
                Requirement.revision == case.current_revision,
                Requirement.key == target.requirement_key,
            )
        )
        is None
    ):
        raise HTTPException(409, "evidence requirement is not present in this revision")
    target.verified = True
    target.verified_by = user.id
    append_audit(
        db,
        user.tenant_id,
        user.id,
        "evidence.verified",
        "evidence",
        target.id,
        {"revision": target.revision, "source_evidence_id": evidence.id},
    )
    enqueue(
        db,
        user.tenant_id,
        "bidweave.evidence.verified",
        {"case_id": case.id, "evidence_id": target.id},
    )
    commit_or_rollback(db)
    return detail_payload(case, db)


@api.get("/cases/{case_id}/evidence/{evidence_id}/download")
def download_evidence(
    case_id: str,
    evidence_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_user),
):
    case = tenant_case(db, case_id, user)
    evidence = db.scalar(
        select(Evidence).where(Evidence.id == evidence_id, Evidence.case_id == case.id)
    )
    if evidence is None:
        raise HTTPException(404, "evidence not found")
    try:
        content = object_store().get(evidence.object_key)
    except DependencyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename(evidence.filename)}"'
        },
    )


@api.get("/cases/{case_id}/evidence/{evidence_id}/preview")
def preview_evidence(
    case_id: str,
    evidence_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_user),
):
    case = tenant_case(db, case_id, user)
    evidence = db.scalar(
        select(Evidence).where(Evidence.id == evidence_id, Evidence.case_id == case.id)
    )
    if evidence is None:
        raise HTTPException(404, "evidence not found")
    try:
        content = object_store().get(evidence.object_key)
    except DependencyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if evidence.filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(422, "unable to extract PDF text") from exc
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                422, "preview is available only for text and PDF evidence"
            ) from exc
    return {
        "evidence_id": evidence.id,
        "filename": evidence.filename,
        "text": text[:200000],
        "truncated": len(text) > 200000,
    }


@api.post("/cases/{case_id}/submit", response_model=CaseDetail)
def submit(
    case_id: str,
    body: SubmitRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("coordinator")),
):
    case = tenant_case(db, case_id, user, lock=True)
    if body.expected_revision != case.current_revision:
        raise HTTPException(409, "stale revision")
    if case.status != "draft":
        raise HTTPException(409, "case is not in draft state")
    reqs = list(
        db.scalars(
            select(Requirement).where(
                Requirement.case_id == case.id,
                Requirement.revision == case.current_revision,
            )
        )
    )
    if not reqs:
        raise HTTPException(
            409, "at least one requirement is required before submission"
        )
    evidence = list(db.scalars(select(Evidence).where(Evidence.case_id == case.id)))
    results = evaluate(case, case.current_revision, reqs, evidence)
    if any(r.mandatory and not results.get(r.key, False) for r in reqs):
        raise HTTPException(409, "mandatory requirements are not satisfied")
    flowable = FlowableClient()
    try:
        workflow_id = flowable.start(
            user.tenant_id, case.id, case.current_revision, user.id
        )
    except DependencyUnavailable as first_error:
        try:
            workflow_id = flowable.active_for_case(case.id, case.current_revision)
        except DependencyUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        if workflow_id is None:
            raise HTTPException(
                503, "workflow submission could not be reconciled"
            ) from first_error
    case.status = "in_review"
    pending = Approval(
        case_id=case.id,
        tenant_id=user.tenant_id,
        revision=case.current_revision,
        reviewer_id=user.id,
        decision="pending",
        comment="",
        workflow_id=workflow_id,
    )
    db.add(pending)
    append_audit(
        db,
        user.tenant_id,
        user.id,
        "case.submitted",
        "case",
        case.id,
        {"revision": case.current_revision, "workflow_id": workflow_id},
    )
    enqueue(
        db,
        user.tenant_id,
        "bidweave.case.submitted",
        {"case_id": case.id, "revision": case.current_revision},
    )
    commit_or_rollback(db)
    return detail_payload(case, db, workflow_id)


@api.post("/cases/{case_id}/review", response_model=CaseDetail)
def review(
    case_id: str,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("reviewer")),
):
    case = tenant_case(db, case_id, user, lock=True)
    if body.expected_revision != case.current_revision:
        raise HTTPException(409, "stale revision")
    if case.status != "in_review":
        raise HTTPException(409, "case has no active review")
    pending = db.scalar(
        select(Approval)
        .where(
            Approval.case_id == case.id,
            Approval.revision == case.current_revision,
            Approval.decision == "pending",
        )
        .order_by(Approval.created_at.desc())
    )
    if pending is None or not pending.workflow_id:
        raise HTTPException(409, "active workflow not found")
    if pending.reviewer_id == user.id or case.owner_id == user.id:
        raise HTTPException(403, "submitter or owner cannot approve")
    flowable = FlowableClient()
    try:
        tasks = flowable.tasks(pending.workflow_id)
        if tasks:
            try:
                flowable.complete(
                    str(tasks[0]["id"]), body.decision, body.comment, user.id
                )
            except DependencyUnavailable:
                # A lost response must not invent success or leave a finished process stranded.
                # The engine's persisted history below must prove this exact decision and actor.
                pass
        completed = flowable.completed_review(pending.workflow_id)
    except DependencyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    expected = {
        "case_id": case.id,
        "tenant_id": user.tenant_id,
        "revision": case.current_revision,
        "decision": body.decision,
        "comment": body.comment,
        "reviewer": user.id,
    }
    if completed is None:
        raise HTTPException(
            503, "workflow completion is not confirmed; retry the same decision"
        )
    if any(completed.get(key) != value for key, value in expected.items()):
        raise HTTPException(
            409, "workflow history records a different decision or reviewer"
        )
    pending.decision = body.decision
    pending.reviewer_id = user.id
    pending.comment = body.comment
    case.status = "approved" if body.decision == "approve" else "draft"
    action = "approved" if body.decision == "approve" else "rejected"
    append_audit(
        db,
        user.tenant_id,
        user.id,
        f"case.{action}",
        "case",
        case.id,
        {"revision": case.current_revision, "workflow_id": pending.workflow_id},
    )
    enqueue(
        db,
        user.tenant_id,
        f"bidweave.case.{action}",
        {"case_id": case.id, "revision": case.current_revision},
    )
    commit_or_rollback(db)
    return detail_payload(case, db, pending.workflow_id)


@api.get("/cases/{case_id}/export")
def export_case(
    case_id: str,
    revision: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: Principal = Depends(current_user),
):
    case = tenant_case(db, case_id, user, lock=True)
    if revision != case.current_revision:
        raise HTTPException(409, "stale revision cannot be exported")
    approval = db.scalar(
        select(Approval).where(
            Approval.case_id == case.id,
            Approval.revision == revision,
            Approval.decision == "approve",
        )
    )
    if approval is None:
        raise HTTPException(409, "only an approved revision can be exported")
    rev = db.scalar(
        select(Revision).where(Revision.case_id == case.id, Revision.number == revision)
    )
    if rev is None:
        raise HTTPException(404, "revision not found")
    evidence = list(
        db.scalars(
            select(Evidence).where(
                Evidence.case_id == case.id,
                Evidence.revision == revision,
                Evidence.verified.is_(True),
            )
        ).all()
    )
    requirements = list(
        db.scalars(
            select(Requirement)
            .where(Requirement.case_id == case.id, Requirement.revision == revision)
            .order_by(Requirement.key)
        ).all()
    )
    notices = list(
        db.scalars(
            select(Notice)
            .where(Notice.case_id == case.id)
            .order_by(Notice.retrieved_at)
        ).all()
    )
    manifest = {
        "case_id": case.id,
        "revision": revision,
        "historical": False,
        "deadline": rev.deadline.isoformat(),
        "approval": {
            "id": approval.id,
            "reviewer_id": approval.reviewer_id,
            "comment": approval.comment,
            "created_at": approval.created_at.isoformat(),
        },
        "requirements": [
            {
                "key": item.key,
                "title": item.title,
                "description": item.description,
                "kind": item.kind,
                "minimum": item.minimum,
                "mandatory": item.mandatory,
                "source_ref": item.source_ref,
                "owner": item.owner,
            }
            for item in requirements
        ],
        "source_graphs": [item.source_graph for item in notices],
        "provenance": {
            "case_owner": case.owner_id,
            "revision_created_by": rev.created_by,
        },
        "files": [],
    }
    archive = BytesIO()
    try:
        with tarfile.open(fileobj=archive, mode="w:gz") as tar:
            for item in evidence:
                try:
                    content = object_store().get(item.object_key)
                except DependencyUnavailable as exc:
                    raise HTTPException(503, str(exc)) from exc
                if sha256(content).hexdigest() != item.sha256:
                    raise HTTPException(409, "evidence integrity check failed")
                name = f"evidence/{item.id}-{safe_filename(item.filename)}"
                info = tarfile.TarInfo(name)
                info.size = len(content)
                tar.addfile(info, BytesIO(content))
                manifest["files"].append(
                    {"path": name, "sha256": item.sha256, "evidence_id": item.id}
                )
            manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(manifest_bytes)
            tar.addfile(info, BytesIO(manifest_bytes))
    except HTTPException:
        raise
    return StreamingResponse(
        iter([archive.getvalue()]),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="bidweave-{case.id}-r{revision}.tar.gz"'
        },
    )


@api.post("/cases/{case_id}/comments", response_model=CommentOut, status_code=201)
def comment(
    case_id: str,
    body: CommentCreate,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_user),
):
    case = tenant_case(db, case_id, user)
    value = Comment(
        case_id=case.id, tenant_id=user.tenant_id, author=user.id, body=body.body
    )
    db.add(value)
    append_audit(db, user.tenant_id, user.id, "comment.created", "case", case.id, {})
    commit_or_rollback(db)
    return value


@api.patch("/cases/{case_id}/tasks/{task_id}", response_model=CaseDetail)
def task_patch(
    case_id: str,
    task_id: str,
    body: TaskPatch,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_user),
):
    case = tenant_case(db, case_id, user)
    task = db.scalar(select(Task).where(Task.id == task_id, Task.case_id == case.id))
    if task is None:
        raise HTTPException(404, "task not found")
    if (
        body.assignee is not None
        and body.assignee != user.id
        and "coordinator" not in user.roles
    ):
        raise HTTPException(403, "cannot assign task to another user")
    task.status = body.status
    task.assignee = body.assignee or task.assignee or user.id
    commit_or_rollback(db)
    return detail_payload(case, db)


@api.get("/analytics", response_model=Analytics)
def analytics(db: Session = Depends(get_db), user: Principal = Depends(current_user)):
    cases = list(db.scalars(select(Case).where(Case.tenant_id == user.tenant_id)))
    tasks = list(
        db.scalars(
            select(Task).where(Task.tenant_id == user.tenant_id, Task.status == "open")
        )
    )
    reqs = []
    verified_requirements = 0
    for case in cases:
        current = list(
            db.scalars(
                select(Requirement).where(
                    Requirement.case_id == case.id,
                    Requirement.revision == case.current_revision,
                )
            ).all()
        )
        reqs.extend(current)
        evidence = list(
            db.scalars(select(Evidence).where(Evidence.case_id == case.id)).all()
        )
        results = evaluate(case, case.current_revision, current, evidence)
        verified_requirements += sum(bool(results.get(item.key)) for item in current)
    audit = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.tenant_id == user.tenant_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        )
    )
    events = [
        {
            "id": item.id,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "created_at": item.created_at.isoformat(),
        }
        for item in audit
    ]
    return Analytics(
        case_count=len(cases),
        approved_count=sum(c.status == "approved" for c in cases),
        pending_review_count=sum(c.status == "in_review" for c in cases),
        open_tasks=len(tasks),
        requirements_count=len(reqs),
        verified_requirements=verified_requirements,
        events=events,
    )


@api.get("/cases/{case_id}/lineage")
def lineage(
    case_id: str, db: Session = Depends(get_db), user: Principal = Depends(current_user)
):
    case = tenant_case(db, case_id, user)
    return build_lineage(case, db)


@api.post("/cases/{case_id}/lineage/publish")
def publish_case_lineage(
    case_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("coordinator")),
):
    case = tenant_case(db, case_id, user)
    try:
        return publish_lineage(build_lineage(case, db), user.tenant_id, case.id)
    except ProjectionError as exc:
        raise HTTPException(503, str(exc)) from exc


@api.get("/cases/{case_id}/history")
def case_history(
    case_id: str, db: Session = Depends(get_db), user: Principal = Depends(current_user)
):
    return history_for_case(tenant_case(db, case_id, user), db)


@api.post("/cases/{case_id}/notice")
def notice(
    case_id: str,
    body: NoticeCreate,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_role("coordinator")),
):
    case = tenant_case(db, case_id, user, lock=True)
    if case.status != "draft":
        raise HTTPException(
            409, "notice provenance can only change in a draft revision"
        )
    try:
        graph = fetch_ted_notice(body.publication_number)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except DependencyUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    item = Notice(
        case_id=case.id,
        tenant_id=user.tenant_id,
        publication_number=body.publication_number,
        source_graph=graph,
    )
    db.add(item)
    append_audit(
        db,
        user.tenant_id,
        user.id,
        "notice.linked",
        "case",
        case.id,
        {"publication_number": body.publication_number},
    )
    commit_or_rollback(db)
    return {
        "publication_number": item.publication_number,
        "source_graph": item.source_graph,
        "retrieved_at": item.retrieved_at,
    }


@app.get("/internal/metrics", include_in_schema=False)
def metrics(db: Session = Depends(get_db)):
    cases = db.scalar(select(func.count(Case.id))) or 0
    approved = (
        db.scalar(select(func.count(Case.id)).where(Case.status == "approved")) or 0
    )
    return Response(
        f"# HELP bidweave_cases_total Cases\n# TYPE bidweave_cases_total gauge\nbidweave_cases_total {cases}\n# HELP bidweave_cases_approved Approved cases\n# TYPE bidweave_cases_approved gauge\nbidweave_cases_approved {approved}\n",
        media_type="text/plain; version=0.0.4",
    )


from .intelligence import router as intelligence_router

api.include_router(intelligence_router)
from .governance import router as governance_router
from .automation import router as automation_router

api.include_router(governance_router)
api.include_router(automation_router)

app.include_router(api)


def run() -> None:
    import uvicorn

    uvicorn.run("bidweave.main:app", host="0.0.0.0", port=8000)

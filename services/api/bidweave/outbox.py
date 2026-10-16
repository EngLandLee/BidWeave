# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed outbox delivery; no warranty.
from datetime import datetime, timezone
import asyncio, json
from sqlalchemy import select
from .adapters import NatsPublisher
from .db import SessionLocal
from .models import Case, OutboxEvent
from .projections import snapshot_case


def deliver_once(limit: int = 100) -> int:
    db = SessionLocal()
    sent = 0
    try:
        events = list(
            db.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.delivered_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(limit)
            )
        )
        for event in events:
            payload = json.loads(event.payload)
            if event.subject == "bidweave.case.approved":
                case = db.scalar(
                    select(Case).where(
                        Case.id == payload["case_id"], Case.tenant_id == event.tenant_id
                    )
                )
                if case is None:
                    raise RuntimeError("approved event references an unavailable case")
                snapshot_case(case, db, revision_number=payload["revision"])
            asyncio.run(
                NatsPublisher().publish(
                    event.subject,
                    {"event_id": event.id, "tenant_id": event.tenant_id, **payload},
                )
            )
            event.delivered_at = datetime.now(timezone.utc)
            sent += 1
        db.commit()
        return sent
    finally:
        db.close()


def run_once() -> None:
    deliver_once()

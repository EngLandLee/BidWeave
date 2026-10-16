# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed governance regression tests; no warranty.
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace

from bidweave.governance import verify_audit_chain


def _event(
    event_id: str,
    *,
    previous_hash: str = "",
    payload: str = '{"value":1}',
    tenant_id: str = "tenant-a",
    created_at: datetime,
):
    actor_id = "actor"
    action = "case.created"
    entity_type = "case"
    entity_id = event_id
    digest = sha256(
        (
            previous_hash
            + tenant_id
            + actor_id
            + action
            + entity_type
            + entity_id
            + payload
        ).encode()
    ).hexdigest()
    return SimpleNamespace(
        id=event_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        previous_hash=previous_hash,
        hash=digest,
        created_at=created_at,
    )


def test_valid_chain_preserves_head_hash():
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    root = _event("z-root", created_at=timestamp)
    child = _event("a-child", previous_hash=root.hash, created_at=timestamp)
    result = verify_audit_chain([child, root])
    assert result.valid is True
    assert result.head_hash == child.hash
    assert result.broken_event_id is None


def test_empty_chain_is_a_valid_tenant_boundary():
    result = verify_audit_chain([])
    assert result.valid is True
    assert result.head_hash == ""
    assert result.broken_event_id is None


def test_chain_requires_an_empty_root_boundary():
    event = _event(
        "root",
        previous_hash="foreign-head",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    result = verify_audit_chain([event])
    assert result.valid is False
    assert result.broken_event_id == "root"


def test_payload_tampering_is_reported_at_the_tampered_event():
    root = _event("root", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    tampered = _event(
        "tampered",
        previous_hash=root.hash,
        payload='{"value":2}',
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    tampered.hash = _event(
        "tampered",
        previous_hash=root.hash,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    ).hash

    result = verify_audit_chain([root, tampered])
    assert result.valid is False
    assert result.broken_event_id == "tampered"


def test_missing_parent_and_fork_are_reported_deterministically():
    missing = _event(
        "missing-parent",
        previous_hash="deadbeef",
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    missing_result = verify_audit_chain([missing])
    assert missing_result.valid is False
    assert missing_result.broken_event_id == "missing-parent"

    root = _event("root", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    first_branch = _event(
        "branch-a",
        previous_hash=root.hash,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    second_branch = _event(
        "branch-b",
        previous_hash=root.hash,
        created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    fork_result = verify_audit_chain([root, first_branch, second_branch])
    assert fork_result.valid is False
    assert fork_result.broken_event_id == "branch-b"

#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Licensed under Apache-2.0; see LICENSE. Provided without warranties.
"""Exercise real SSO, gateway, storage, workflow and revision invariants.

Run from the repository root after `make up`:
    uv run --project services/api python scripts/smoke.py
No service is mocked. Credentials come from ignored local .env and are never logged.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tarfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx


def configuration(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"').strip("'")
    return {**values, **os.environ}


class Scenario:
    def __init__(self, base: str, identity: str, password: str):
        self.base = base.rstrip("/")
        self.client = httpx.Client(timeout=90, follow_redirects=True)
        self.tokens = {}
        self.checks = []
        for username in ("coordinator", "contributor", "reviewer", "outsider"):
            response = self.client.post(
                identity.rstrip("/") + "/realms/bidweave/protocol/openid-connect/token",
                data={
                    "grant_type": "password",
                    "client_id": "bidweave-smoke",
                    "username": username,
                    "password": password,
                },
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"SSO failed for {username}: HTTP {response.status_code}"
                )
            self.tokens[username] = response.json()["access_token"]
        self.checks.append("Four real Keycloak identities authenticated")

    def request(
        self,
        method: str,
        path: str,
        *,
        actor: str | None = "coordinator",
        expected: tuple[int, ...] = (200,),
        **kwargs,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if actor:
            headers["Authorization"] = "Bearer " + self.tokens[actor]
        response = self.client.request(
            method, self.base + path, headers=headers, **kwargs
        )
        if response.status_code not in expected:
            raise AssertionError(
                f"{method} {path}: expected {expected}, got "
                f"{response.status_code}: {response.text[:1200]}"
            )
        return response

    def upload(
        self,
        case: str,
        revision: int,
        key: str,
        name: str,
        text: str,
        *,
        quantity: int = 1,
        valid_until: str | None = None,
    ) -> dict:
        fields = {
            "requirement_key": key,
            "expected_revision": str(revision),
            "quantity": str(quantity),
            "notes": "Synthetic E2E fixture; no real company claim.",
        }
        if valid_until:
            fields["valid_until"] = valid_until
        return self.request(
            "POST",
            f"/api/cases/{case}/evidence",
            actor="contributor",
            expected=(200, 201),
            data=fields,
            files={"file": (name, text.encode(), "text/plain")},
        ).json()

    def verify_current(self, case: str, revision: int) -> dict:
        detail = self.request("GET", f"/api/cases/{case}").json()
        for item in detail["evidence"]:
            self.request(
                "POST",
                f"/api/cases/{case}/evidence/{item['id']}/verify",
                actor="reviewer",
                json={"expected_revision": revision},
            )
        return self.request("GET", f"/api/cases/{case}").json()

    def export(self, case: str, revision: int) -> tuple[bytes, list[str]]:
        response = self.request("GET", f"/api/cases/{case}/export?revision={revision}")
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
            members = archive.getmembers()
            assert all(
                not m.name.startswith("/")
                and ".." not in Path(m.name).parts
                and not m.issym()
                and not m.islnk()
                for m in members
            )
            names = [m.name for m in members]
            manifest_names = [n for n in names if n.endswith("manifest.json")]
            assert len(manifest_names) == 1, "Export must contain one manifest"
            manifest = json.load(archive.extractfile(manifest_names[0]))
            assert manifest["revision"] == revision, (
                "Manifest must record the exact approved revision"
            )
            detail = self.request("GET", f"/api/cases/{case}").json()
            expected_hashes = {
                e["sha256"]
                for e in detail["evidence"]
                if e["revision"] == revision and e["verified"]
            }
            file_hashes = {
                hashlib.sha256(archive.extractfile(m).read()).hexdigest()
                for m in members
                if m.isfile()
            }
            assert expected_hashes <= file_hashes, (
                "Original evidence missing or changed in export"
            )
        return response.content, names

    def run(self) -> dict:
        today = date.today()
        first_deadline = (today + timedelta(days=30)).isoformat()
        later_deadline = (today + timedelta(days=60)).isoformat()
        original_expiry = (today + timedelta(days=45)).isoformat()
        replacement_expiry = (today + timedelta(days=120)).isoformat()
        self.request("GET", "/api/cases", actor=None, expected=(401,))
        self.request("GET", "/api/me", actor="outsider")
        case = self.request(
            "POST",
            "/api/cases",
            expected=(200, 201),
            json={
                "title": "SYNTHETIC · Amendment assurance scenario",
                "deadline": first_deadline,
                "description": "Generated verification case. Fictional IT support procurement; no legal eligibility claim.",
            },
        ).json()
        cid = case["id"]
        assert case["current_revision"] == 0
        self.request("GET", f"/api/cases/{cid}", actor="outsider", expected=(404,))
        requirements = [
            {
                "key": "EXP",
                "title": "Similar completed projects",
                "description": "Independently verified project count.",
                "kind": "count",
                "minimum": 2,
                "mandatory": True,
                "source_ref": "Synthetic specification section 2",
                "owner": "contributor",
            },
            {
                "key": "CERT",
                "title": "Valid certificate at submission deadline",
                "description": "This synthetic tender explicitly requires validity through its submission deadline.",
                "kind": "validity",
                "mandatory": True,
                "source_ref": "Synthetic specification section 3",
                "owner": "contributor",
            },
        ]
        revision_body = {
            "expected_revision": 0,
            "deadline": first_deadline,
            "reason": "Initial synthetic specification",
            "requirements": requirements,
        }
        first = self.request(
            "POST",
            f"/api/cases/{cid}/revisions",
            expected=(200, 201),
            json=revision_body,
        ).json()
        assert first["current_revision"] == 1
        self.request(
            "POST", f"/api/cases/{cid}/revisions", expected=(409,), json=revision_body
        )
        self.request(
            "POST",
            f"/api/cases/{cid}/submit",
            expected=(409,),
            json={"expected_revision": 1},
        )
        self.checks.append(
            "Missing auth, tenant isolation, stale mutation and incomplete submission rejected"
        )
        evidence = self.upload(
            cid,
            1,
            "EXP",
            "synthetic-projects.txt",
            "SYNTHETIC: two completed projects, ALPHA and BETA. Reviewer confirms the count 2.",
            quantity=2,
        )
        cert = self.upload(
            cid,
            1,
            "CERT",
            "synthetic-certificate.txt",
            "SYNTHETIC: fictional certificate expires " + original_expiry,
            valid_until=original_expiry,
        )
        self.request(
            "POST",
            f"/api/cases/{cid}/evidence/{evidence['id']}/verify",
            actor="contributor",
            expected=(403,),
            json={"expected_revision": 1},
        )
        self.request(
            "GET",
            f"/api/cases/{cid}/evidence/{cert['id']}/download",
            actor="outsider",
            expected=(404,),
        )
        self.verify_current(cid, 1)
        submitted = self.request(
            "POST", f"/api/cases/{cid}/submit", json={"expected_revision": 1}
        ).json()
        assert submitted["status"] == "in_review"
        assert submitted.get("workflow_id"), "No real workflow process identity"
        self.request(
            "POST",
            f"/api/cases/{cid}/review",
            expected=(403,),
            json={
                "expected_revision": 1,
                "decision": "approve",
                "comment": "Cannot self-approve",
            },
        )
        approved = self.request(
            "POST",
            f"/api/cases/{cid}/review",
            actor="reviewer",
            json={
                "expected_revision": 1,
                "decision": "approve",
                "comment": "Synthetic revision 1 checked",
            },
        ).json()
        assert approved["status"] == "approved"
        _, original_names = self.export(cid, 1)
        self.checks.append(
            "Quarantined stored evidence independently verified; Flowable review completed; archive hashes verified"
        )
        requirements[0]["minimum"] = 3
        amended = self.request(
            "POST",
            f"/api/cases/{cid}/revisions",
            expected=(200, 201),
            json={
                "expected_revision": 1,
                "deadline": later_deadline,
                "reason": "Synthetic amendment: three projects and a later submission deadline",
                "requirements": requirements,
            },
        ).json()
        assert amended["current_revision"] == 2 and amended["status"] == "draft"
        assert amended["impact"], "Amendment impact not recorded"
        assert amended["approvals"], "Historical approval erased"
        self.request("GET", f"/api/cases/{cid}/export?revision=1", expected=(409,))
        self.request("GET", f"/api/cases/{cid}/export?revision=2", expected=(409,))
        self.request(
            "POST",
            f"/api/cases/{cid}/review",
            actor="reviewer",
            expected=(409,),
            json={
                "expected_revision": 1,
                "decision": "approve",
                "comment": "Stale browser tab",
            },
        )
        self.request(
            "POST",
            f"/api/cases/{cid}/submit",
            expected=(409,),
            json={"expected_revision": 2},
        )
        self.checks.append(
            "Amendment invalidates readiness, preserves historical approval and blocks stale/current-unapproved export"
        )
        self.upload(
            cid,
            2,
            "EXP",
            "synthetic-extra-project.txt",
            "SYNTHETIC: third completed project GAMMA. Count 1.",
            quantity=1,
        )
        self.upload(
            cid,
            2,
            "CERT",
            "synthetic-renewed-certificate.txt",
            "SYNTHETIC: replacement fictional certificate expires "
            + replacement_expiry,
            valid_until=replacement_expiry,
        )
        self.verify_current(cid, 2)
        self.request(
            "POST",
            f"/api/cases/{cid}/comments",
            expected=(200, 201),
            actor="contributor",
            json={
                "body": "Synthetic amendment addressed; please independently check the new evidence."
            },
        )
        current = self.request("GET", f"/api/cases/{cid}").json()
        for task in current["tasks"]:
            self.request(
                "PATCH", f"/api/cases/{cid}/tasks/{task['id']}", json={"status": "done"}
            )
        self.request("POST", f"/api/cases/{cid}/submit", json={"expected_revision": 2})
        self.request(
            "POST",
            f"/api/cases/{cid}/review",
            actor="reviewer",
            json={
                "expected_revision": 2,
                "decision": "reject",
                "comment": "Synthetic correction requested",
            },
        )
        rejected = self.request("GET", f"/api/cases/{cid}").json()
        assert rejected["status"] == "draft"
        self.request("GET", f"/api/cases/{cid}/export?revision=2", expected=(409,))
        self.request("POST", f"/api/cases/{cid}/submit", json={"expected_revision": 2})
        self.request(
            "POST",
            f"/api/cases/{cid}/review",
            actor="reviewer",
            json={
                "expected_revision": 2,
                "decision": "approve",
                "comment": "Synthetic amended evidence checked",
            },
        )
        archive_bytes, final_names = self.export(cid, 2)
        lineage = self.request("GET", f"/api/cases/{cid}/lineage").json()
        assert "@context" in lineage and "@graph" in lineage, "Missing linked lineage"
        metrics = self.request("GET", "/api/analytics").json()
        assert metrics["approved_count"] >= 1
        self.checks.append(
            "Updated evidence re-reviewed; version 2 approved/exported; HPDI collaboration, analytics and lineage exercised"
        )
        return {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "case_id": cid,
            "data_classification": "synthetic",
            "checks": self.checks,
            "first_archive_members": original_names,
            "final_archive_members": final_names,
            "final_archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
            "status": "passed",
            "boundary": "LLM, MCP, linked-data and browser have separate verification steps.",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8090")
    parser.add_argument("--identity", default="http://localhost:8091")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output", type=Path, default=Path(".runtime/smoke-result.json")
    )
    args = parser.parse_args()
    config = configuration(args.env)
    password = config.get("DEMO_PASSWORD")
    if not password:
        raise SystemExit("DEMO_PASSWORD is missing; run make configure first.")
    scenario = Scenario(args.base, args.identity, password)
    try:
        result = scenario.run()
    finally:
        scenario.client.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

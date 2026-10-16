# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
"""Official MCP transport with per-request authentication and no approval tool.

Bearer credentials belong to HTTP headers, never LLM-visible tool arguments.
UUID parameters cannot escape the fixed core routes. Proposals are explicitly
read-only; submitting a case is a real, permission-checked workflow mutation.
"""
# Keep concrete Context annotations: MCP 1.13 uses them for transport injection.

import os
from typing import Any
from uuid import UUID

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

CORE_API_URL = os.getenv("CORE_API_URL", "http://127.0.0.1:8000").rstrip("/")
mcp = FastMCP(
    "BidWeave",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*", "127.0.0.1:*", "mcp:*"],
        allowed_origins=["http://localhost:8090", "http://localhost:5173"],
    ),
)


class AuthenticateRequest:
    """Authenticate initialize/list/call requests as well as individual tools."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        authorization = (
            dict(scope.get("headers", [])).get(b"authorization", b"").decode("latin-1")
        )
        if not authorization.startswith("Bearer ") or len(authorization) > 8192:
            await JSONResponse(
                {"detail": "Bearer authentication required"}, status_code=401
            )(scope, receive, send)
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                result = await client.get(
                    f"{CORE_API_URL}/api/me", headers={"Authorization": authorization}
                )
        except httpx.HTTPError:
            await JSONResponse(
                {"detail": "Identity service unavailable"}, status_code=503
            )(scope, receive, send)
            return
        if result.status_code != 200:
            code = result.status_code if result.status_code in (401, 403) else 503
            await JSONResponse(
                {"detail": "Core authentication rejected"}, status_code=code
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def _request(
    path: str, ctx: Context, method: str = "GET", body: dict[str, Any] | None = None
) -> Any:
    request = ctx.request_context.request
    if request is None:
        raise ValueError("Authenticated HTTP context is required")
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise ValueError("Bearer authentication is required")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{CORE_API_URL}{path}",
                headers={"Authorization": authorization},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise RuntimeError("Core API unavailable") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "Core request rejected")
        except ValueError:
            detail = "Core request rejected"
        raise ValueError(f"{response.status_code}: {detail}")
    return response.json()


@mcp.tool()
async def read_case(case_id: UUID, ctx: Context) -> dict[str, Any]:
    """Read the caller's tenant-scoped requirements, evidence metadata and history."""
    return await _request(f"/api/cases/{case_id}", ctx)


@mcp.tool()
async def read_evidence(case_id: UUID, ctx: Context) -> dict[str, Any]:
    """Read metadata only; never disclose original document bytes to an agent."""
    case = await read_case(case_id, ctx)
    return {
        "case_id": str(case_id),
        "revision": case["current_revision"],
        "evidence": case["evidence"],
    }


@mcp.tool()
async def read_impact(case_id: UUID, ctx: Context) -> dict[str, Any]:
    """Read current amendment impacts and existing human tasks."""
    case = await read_case(case_id, ctx)
    revision = case["current_revision"]
    return {
        "case_id": str(case_id),
        "revision": revision,
        "impact": [item for item in case["impact"] if item["revision"] == revision],
        "tasks": [item for item in case["tasks"] if item["revision"] == revision],
    }


@mcp.tool()
async def propose_tasks(
    case_id: UUID, expected_revision: int, ctx: Context
) -> dict[str, Any]:
    """Derive missing-evidence tasks without duplicating open tasks; does not write."""
    case = await read_case(case_id, ctx)
    if expected_revision != case["current_revision"]:
        raise ValueError("Stale revision; reload the case")
    existing = {
        task["requirement_key"]
        for task in case["tasks"]
        if task["revision"] == expected_revision and task["status"] == "open"
    }
    proposals = [
        {
            "requirement_key": req["key"],
            "title": f"Bổ sung và xác nhận: {req['title']}",
            "owner": req["owner"],
            "source_ref": req["source_ref"],
            "reason": req["status"],
        }
        for req in case["requirements"]
        if req["status"] != "verified" and req["key"] not in existing
    ]
    return {
        "case_id": str(case_id),
        "revision": expected_revision,
        "proposals": proposals,
        "existing_open_tasks": sorted(existing),
        "written": False,
    }


@mcp.tool()
async def propose_revision(
    case_id: UUID,
    expected_revision: int,
    reason: str,
    requirement_keys: list[str],
    ctx: Context,
) -> dict[str, Any]:
    """Prepare a grounded revision review scope; human editor applies any changes."""
    case = await read_case(case_id, ctx)
    if expected_revision != case["current_revision"]:
        raise ValueError("Stale revision; reload the case")
    if (
        not reason.strip()
        or len(reason) > 2000
        or not 1 <= len(requirement_keys) <= 100
    ):
        raise ValueError("Provide a reason and 1-100 requirement keys")
    requirements = {item["key"]: item for item in case["requirements"]}
    if set(requirement_keys) - requirements.keys():
        raise ValueError(
            "Unknown requirement key; proposals must reference existing requirements"
        )
    evidence = [
        item
        for item in case["evidence"]
        if item["requirement_key"] in requirement_keys
        and item["revision"] == expected_revision
    ]
    return {
        "case_id": str(case_id),
        "base_revision": expected_revision,
        "reason": reason.strip(),
        "review_scope": [requirements[key] for key in dict.fromkeys(requirement_keys)],
        "evidence_to_reverify": [item["id"] for item in evidence],
        "approval_will_be_invalidated": case["status"] == "approved",
        "written": False,
    }


@mcp.tool()
async def submit_for_review(
    case_id: UUID, expected_revision: int, ctx: Context
) -> dict[str, Any]:
    """Submit an exact revision to Flowable; core enforces coordinator permission."""
    if expected_revision < 1:
        raise ValueError("An initial requirements revision is required")
    return await _request(
        f"/api/cases/{case_id}/submit",
        ctx,
        method="POST",
        body={"expected_revision": expected_revision},
    )


def create_mcp_app():
    app = mcp.streamable_http_app()
    app.add_middleware(AuthenticateRequest)
    return app

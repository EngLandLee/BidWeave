#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Licensed under Apache-2.0; see LICENSE. No warranties.
"""Exercise live MCP authorization and Ollama; no fake response or stored token."""

from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from smoke import Scenario, configuration


async def exercise_tools(url: str, token: str, outsider: str, case_id: str) -> dict:
    async with streamablehttp_client(
        url, headers={"Authorization": f"Bearer {token}"}
    ) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert "approve_case" not in names, (
                "Agent must not have an approval capability"
            )
            result = await session.call_tool("read_case", {"case_id": case_id})
            assert not result.isError and result.structuredContent["id"] == case_id
            assert all(
                "token" not in json.dumps(tool.inputSchema).lower()
                for tool in tools.tools
            )
    async with streamablehttp_client(
        url, headers={"Authorization": f"Bearer {outsider}"}
    ) as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            denied = await session.call_tool("read_case", {"case_id": case_id})
            assert denied.isError, "MCP leaked another tenant case"
            assert not denied.structuredContent, "Denied MCP result includes case data"
    return {"read_case": case_id, "cross_tenant_read": "denied", "tools": sorted(names)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://localhost:8090")
    parser.add_argument("--identity", default="http://localhost:8091")
    parser.add_argument("--case-id")
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument(
        "--output", type=Path, default=Path(".runtime/intelligence-result.json")
    )
    args = parser.parse_args()
    case_id = args.case_id
    if not case_id:
        previous = Path(".runtime/smoke-result.json")
        if not previous.is_file():
            parser.error("Run scripts/smoke.py first, or supply --case-id.")
        case_id = json.loads(previous.read_text())["case_id"]
    scenario = Scenario(
        args.base, args.identity, configuration(args.env)["DEMO_PASSWORD"]
    )
    scenario.client.timeout = httpx.Timeout(180)
    try:
        detail = scenario.request("GET", f"/api/cases/{case_id}").json()
        mcp_result = asyncio.run(
            exercise_tools(
                args.base + "/mcp",
                scenario.tokens["coordinator"],
                scenario.tokens["outsider"],
                case_id,
            )
        )
        scenario.request("POST", "/mcp", actor=None, expected=(401,), json={})
        status = scenario.request("GET", "/api/agent/status").json()
        assert status["available"] and status["model_present"], (
            "Start Ollama and pull LLM_MODEL first"
        )
        chat = scenario.request(
            "POST",
            "/api/agent/chat",
            json={
                "case_id": case_id,
                "message": "Tóm tắt phiên bản hiện tại và tình trạng minh chứng; dẫn nguồn từ hồ sơ. Không thực hiện thay đổi.",
            },
        ).json()
        allowed_sources = (
            {f"case:{case_id}"}
            | {f"requirement:{r['key']}" for r in detail["requirements"]}
            | {
                f"evidence:{e['id']}"
                for e in detail["evidence"]
                if e["revision"] == detail["current_revision"]
            }
        )
        assert chat["sources"] and all(
            source["source_id"] in allowed_sources and not source["quote"]
            for source in chat["sources"]
        )
        after = scenario.request("GET", f"/api/cases/{case_id}").json()
        assert (after["current_revision"], after["status"], after["approvals"]) == (
            detail["current_revision"],
            detail["status"],
            detail["approvals"],
        ), "Chat changed authoritative workflow state"
        extracted = scenario.request(
            "POST",
            "/api/agent/extract",
            files={
                "file": (
                    "synthetic-terms.txt",
                    b"SYNTHETIC EXERCISE. Requirement EXP: at least 2 completed contracts. Supporting documents are mandatory.",
                    "text/plain",
                ),
            },
        ).json()
        assert any(
            item["kind"] == "count" and item["minimum"] == 2
            for item in extracted["requirements"]
        ), "The explicit minimum count was not correctly extracted"
        assert all(
            item["source_ref"] == "document:synthetic-terms.txt#page:1"
            for item in extracted["requirements"]
        )
        result = {
            "status": "passed",
            "case_id": case_id,
            "mcp": mcp_result,
            "model": chat["model"],
            "chat": chat,
            "extraction": extracted,
            "boundary": "Real local inference; structured output and references are checked, not a guarantee of factual or legal correctness.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        scenario.client.close()


if __name__ == "__main__":
    main()

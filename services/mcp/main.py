# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
"""Runnable streamable HTTP MCP service for the BidWeave gateway."""

from __future__ import annotations

from .server import create_mcp_app

# FastMCP's official streamable HTTP application owns the /mcp route and
# per-session transport. Do not put a shared bearer token in this process.
app = create_mcp_app()

"""ZKC · transport seam（第四 seam，ADR-0004）。

对外暴露协议层与契约快照；MCP server 的业务 handler 由上层在构造时注入，
本包自身不 import repository / 驱动，也不直连 DDL。

启动：`python -m zkc.transport`（stdio；stdout 仅输出 JSON-RPC 帧）。
"""
from __future__ import annotations

from .contract import (
    CONTRACT_VERSION,
    MCP_PROTOCOL_VERSION,
    TOOL_NAMES,
    contract_snapshot,
)
from .mcp_server import McpServer, ResourceSpec, ToolSpec, build_server
from .stdio import serve_stdio

__all__ = [
    "CONTRACT_VERSION", "MCP_PROTOCOL_VERSION", "TOOL_NAMES", "contract_snapshot",
    "McpServer", "ToolSpec", "ResourceSpec", "build_server", "serve_stdio",
]

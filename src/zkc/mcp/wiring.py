"""ZKC · MCP composition root：把业务 handler 注入纯协议层。

`transport` 包不知道 ZKC 领域层的存在；本模块是唯一接线点。
store / routers 都是**惰性 provider**——MCP client 启动时只做协议握手，
首个 tool 调用才连库 / 构造路由引擎，因此无 PG / 无 Ollama 的环境也能
完成 initialize 与 tools/list（CI 与协议层单测依赖这一点）。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from zkc.transport.contract import RESOURCE_SCHEMAS, TOOL_SCHEMAS
from zkc.transport.mcp_server import McpServer, ResourceSpec, ToolSpec, build_server

from .handlers import build_handlers


class _LazyStore:
    def __init__(self) -> None:
        self._store = None

    def __call__(self):
        if self._store is None:
            from zkc.repository import get_storage

            self._store = get_storage()
        return self._store


class _LazyRouters:
    def __init__(self) -> None:
        self._value = None

    def __call__(self):
        if self._value is None:
            from zkc.web.app import build_routers

            decision_router, lexical_router = build_routers()
            self._value = (decision_router, lexical_router, True)
        return self._value


def build_zkc_server(
    *,
    store_provider: Optional[Callable[[], Any]] = None,
    routing_provider: Optional[Callable[[], tuple]] = None,
    audit_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    allow_private_claims: bool = False,
    capture_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    capture_profile: Optional[Any] = None,
) -> McpServer:
    """构造带五白名单 tool + 「该关注清单」resource 的 ZKC MCP server。"""
    handlers = build_handlers(
        store_provider=store_provider or _LazyStore(),
        routing_provider=routing_provider or _LazyRouters(),
        audit_sink=audit_sink,
        allow_private_claims=allow_private_claims,
        capture_fn=capture_fn,
        capture_profile=capture_profile,
    )
    tools = [
        ToolSpec(
            name=spec["name"],
            description=spec["description"],
            input_schema=spec["inputSchema"],
            handler=handlers[spec["name"]],
        )
        for spec in TOOL_SCHEMAS
    ]
    resources = [
        ResourceSpec(
            uri=spec["uri"],
            name=spec["name"],
            description=spec["description"],
            mime_type=spec["mimeType"],
            handler=handlers["zkc_scheduler_due"],
        )
        for spec in RESOURCE_SCHEMAS
    ]
    return build_server(tools=tools, resources=resources, audit_sink=audit_sink)


__all__ = ["build_zkc_server"]

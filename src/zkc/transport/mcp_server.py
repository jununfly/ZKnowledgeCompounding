"""ZKC · MCP server 薄适配层（transport seam，ADR-0004）。

第四 seam：与 storage / provider / encoder 并列。本模块**只做协议分发**：
- 不 import 任何 repository / 驱动，不写 DDL，不自行获取 storage；
- 所有 tool / resource 的 handler 由调用方在构造时注入（1-3 接线）；
- 对外契约以 `zkc-mcp-contract v1` 快照为唯一事实源；
- 零网络面：真正的 I/O 只在 `stdio.py` 的 stdin/stdout 循环里。

因此这里是「零领域语义」层：单测只覆盖帧、initialize、tools/list、
tools/call 分发、错误码与注册表安全约束。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from .contract import (
    CAPABILITIES,
    CONTRACT_VERSION,
    MCP_PROTOCOL_VERSION,
    SERVER_INFO,
    TRUST_BOUNDARY,
    is_blacklisted,
)
from .protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    JsonRpcError,
    error_response,
    is_notification,
    result_response,
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Any]


@dataclass(frozen=True)
class ResourceSpec:
    uri: str
    name: str
    description: str
    mime_type: str
    handler: Callable[[Dict[str, Any]], Any]


def _public_tool_view(spec: ToolSpec) -> Dict[str, Any]:
    return {"name": spec.name, "description": spec.description, "inputSchema": spec.input_schema}


def _tool_result(payload: Any, *, is_error: bool = False) -> Dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, default=str
    )
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _type_ok(value: Any, expected: Optional[str]) -> bool:
    if not expected:
        return True
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def validate_arguments(schema: Dict[str, Any], arguments: Dict[str, Any]) -> Optional[str]:
    """最小 JSON Schema 校验（required + 顶层 type），无第三方依赖。

    返回 None 表示通过；否则返回给 agent 的可读错误文本。
    """
    if not isinstance(arguments, dict):
        return "arguments 必须是 object"
    for key in schema.get("required", []):
        if key not in arguments:
            return f"缺少必需参数 {key}"
    for key, spec in (schema.get("properties") or {}).items():
        if key in arguments and not _type_ok(arguments[key], spec.get("type")):
            return f"参数 {key} 类型应为 {spec.get('type')}"
    return None


class McpServer:
    """可注入 handler 的 MCP 协议分发器（不持有任何 store）。"""

    def __init__(
        self,
        *,
        tools: Iterable[ToolSpec] = (),
        resources: Iterable[ResourceSpec] = (),
        audit_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self._tools: Dict[str, ToolSpec] = {}
        self._resources: Dict[str, ResourceSpec] = {}
        self._audit_sink = audit_sink
        for spec in tools:
            self.register_tool(spec)
        for spec in resources:
            self.register_resource(spec)

    # ------------------------------------------------------------ registry
    def register_tool(self, spec: ToolSpec) -> None:
        if not isinstance(spec.name, str) or not spec.name.strip():
            raise ValueError("tool name 不能为空")
        if is_blacklisted(spec.name):
            raise ValueError(f"tool {spec.name!r} 命中 ADR-0004 黑名单，禁止注册")
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} 重复注册")
        if not callable(spec.handler):
            raise ValueError(f"tool {spec.name!r} 的 handler 必须可调用")
        self._tools[spec.name] = spec

    def register_resource(self, spec: ResourceSpec) -> None:
        if spec.uri in self._resources:
            raise ValueError(f"resource {spec.uri!r} 重复注册")
        self._resources[spec.uri] = spec

    @property
    def tool_names(self) -> Tuple[str, ...]:
        return tuple(self._tools)

    def _audit(self, event: str, **fields: Any) -> None:
        if self._audit_sink is None:
            return
        try:
            self._audit_sink({"event": event, **fields})
        except Exception:
            # 审计失败不得把协议连接带崩（留痕只是旁路能力）。
            pass

    # ------------------------------------------------------------ protocol
    def handle_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理一帧；通知返回 None（不回帧）。"""
        if is_notification(message):
            return None
        request_id = message.get("id")
        try:
            result = self._dispatch(message)
        except JsonRpcError as exc:
            return error_response(request_id, exc.code, exc.message, exc.data)
        except Exception as exc:  # 防御：任何未预期异常不外泄为进程崩溃
            return error_response(request_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        return result_response(request_id, result)

    def _dispatch(self, message: Dict[str, Any]) -> Any:
        method = message["method"]
        params = message.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise JsonRpcError(INVALID_PARAMS, "params 必须是 object")

        if method == "initialize":
            requested = params.get("protocolVersion")
            return {
                "protocolVersion": (
                    requested if requested == MCP_PROTOCOL_VERSION else MCP_PROTOCOL_VERSION
                ),
                "capabilities": CAPABILITIES,
                "serverInfo": dict(SERVER_INFO),
                # ZKC 扩展字段：对外契约版本独立于 §5 DDL，由 seam 吸收演进。
                "contractVersion": CONTRACT_VERSION,
                "instructions": TRUST_BOUNDARY,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [_public_tool_view(s) for s in self._tools.values()]}
        if method == "tools/call":
            return self._call_tool(params)
        if method == "resources/list":
            return {"resources": [
                {"uri": s.uri, "name": s.name, "description": s.description,
                 "mimeType": s.mime_type}
                for s in self._resources.values()
            ]}
        if method == "resources/read":
            return self._read_resource(params)
        raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise JsonRpcError(INVALID_PARAMS, "tools/call 需要 name")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise JsonRpcError(INVALID_PARAMS, "arguments 必须是 object")

        spec = self._tools.get(name)
        if spec is None:
            reason = (
                "命中 ADR-0004 黑名单：该写操作绝不暴露"
                if is_blacklisted(name)
                else "未注册的 tool；暴露面仅含 contract v1 白名单五 tool"
            )
            self._audit("tool_denied", tool=name, reason=reason, arguments=arguments)
            return _tool_result(f"拒绝调用 {name!r}：{reason}", is_error=True)

        problem = validate_arguments(spec.input_schema, arguments)
        if problem:
            self._audit("tool_invalid_arguments", tool=name, reason=problem)
            return _tool_result(f"参数校验失败：{problem}", is_error=True)
        try:
            payload = spec.handler(arguments)
        except Exception as exc:
            self._audit("tool_handler_error", tool=name, reason=f"{type(exc).__name__}: {exc}")
            return _tool_result(f"handler 执行失败：{type(exc).__name__}: {exc}", is_error=True)
        return _tool_result(payload)

    def _read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise JsonRpcError(INVALID_PARAMS, "resources/read 需要 uri")
        spec = self._resources.get(uri)
        if spec is None:
            self._audit("resource_denied", uri=uri, reason="未注册的 resource")
            raise JsonRpcError(INVALID_PARAMS, f"未知 resource: {uri}")
        try:
            payload = spec.handler({"uri": uri})
        except Exception as exc:
            self._audit("resource_handler_error", uri=uri, reason=f"{type(exc).__name__}: {exc}")
            return {"contents": [{"uri": uri, "mimeType": spec.mime_type,
                                  "text": f"handler 执行失败：{type(exc).__name__}: {exc}"}]}
        text = payload if isinstance(payload, str) else json.dumps(
            payload, ensure_ascii=False, default=str
        )
        return {"contents": [{"uri": uri, "mimeType": spec.mime_type, "text": text}]}


def build_server(
    *,
    tools: Iterable[ToolSpec] = (),
    resources: Iterable[ResourceSpec] = (),
    audit_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> McpServer:
    """构造可由 MCP client 通过 stdio 连接的 server。

    1-2 阶段是骨架：注册表为空，只提供协议能力；1-3 注入五个白名单 tool
    与「该关注清单」resource，1-4 补 capture 分流闸，1-5 接注入验收用例。
    """
    return McpServer(tools=tools, resources=resources, audit_sink=audit_sink)


__all__ = ["ToolSpec", "ResourceSpec", "McpServer", "build_server", "validate_arguments"]

"""ZKC · MCP stdio 传输的 JSON-RPC 2.0 帧层（纯标准库、零网络面）。

MCP stdio transport 约定：消息是 UTF-8 的 JSON-RPC 2.0 对象，**以换行分帧**，
单条消息内不得出现嵌入换行（由 `encode_message` 的 JSON 转义保证）。
本层只管编解码与错误码常量，不含任何 MCP 方法语义，更不碰存储。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

JSONRPC_VERSION = "2.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcError(Exception):
    """可映射为 JSON-RPC error 对象的协议层异常。"""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def as_dict(self) -> Dict[str, Any]:
        err: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


def decode_message(raw: str) -> Dict[str, Any]:
    """把一行文本解码为 JSON-RPC 请求/通知对象；非法输入抛 JsonRpcError。"""
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise JsonRpcError(PARSE_ERROR, "Parse error: invalid JSON") from exc
    if not isinstance(obj, dict):
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request: expected a JSON object")
    if obj.get("jsonrpc") != JSONRPC_VERSION:
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request: jsonrpc must be '2.0'")
    if not isinstance(obj.get("method"), str) or not obj["method"].strip():
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request: method is required")
    return obj


def encode_message(obj: Dict[str, Any]) -> str:
    """编码为单行 JSON 帧（ensure_ascii=False 保中文；换行由 JSON 转义）。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def is_notification(message: Dict[str, Any]) -> bool:
    """无 id 即通知，按协议不回任何帧。"""
    return "id" not in message


def result_response(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": err}


__all__ = [
    "JSONRPC_VERSION", "PARSE_ERROR", "INVALID_REQUEST", "METHOD_NOT_FOUND",
    "INVALID_PARAMS", "INTERNAL_ERROR", "JsonRpcError",
    "decode_message", "encode_message", "is_notification",
    "result_response", "error_response",
]

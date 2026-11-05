"""ZKC · `zkc-mcp-contract v1` 对外契约快照（独立于 §5 DDL 版本化）。

ADR-0004：对外契约独立版本化，DDL 演进由 transport seam 适配层吸收，
不直接暴露给 MCP client。本模块只加载同目录的 `contract_v1.json`，
不 import 任何 repository / 驱动 / 领域代码 —— seam 纯净性由单测静态校验。

契约快照是**事实源**：白名单五 tool、黑名单、capabilities、信任边界
都从这里读，调用方与测试不得另起一份清单。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Tuple

SNAPSHOT_PATH = Path(__file__).with_name("contract_v1.json")


def _load() -> Dict[str, Any]:
    with SNAPSHOT_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


_SNAPSHOT: Dict[str, Any] = _load()

CONTRACT_VERSION: str = _SNAPSHOT["version"]
MCP_PROTOCOL_VERSION: str = _SNAPSHOT["protocolVersion"]
TRANSPORT: str = _SNAPSHOT["transport"]
TRUST_BOUNDARY: str = _SNAPSHOT["trustBoundary"]
CAPABILITIES: Dict[str, Any] = _SNAPSHOT["capabilities"]
SERVER_INFO: Dict[str, Any] = _SNAPSHOT["serverInfo"]
SERVER_NAME: str = SERVER_INFO["name"]
SERVER_VERSION: str = SERVER_INFO["version"]

TOOL_SCHEMAS: Tuple[Dict[str, Any], ...] = tuple(_SNAPSHOT["tools"])
TOOL_NAMES: Tuple[str, ...] = tuple(t["name"] for t in TOOL_SCHEMAS)
RESOURCE_SCHEMAS: Tuple[Dict[str, Any], ...] = tuple(_SNAPSHOT["resources"])
BLACKLIST: FrozenSet[str] = frozenset(_SNAPSHOT["blacklist"])

# 注入企图的词形锚点：ADR-0004 黑名单的实际语义是「这四类写绝不暴露」，
# 外部 agent 可能换名调用，故按词形拒绝而非只比字符串。
_DANGEROUS_TOKENS = (
    "distill", "interval_adjustment", "interval.adjustment",
    "meta_claim", "meta.claim", "delete_history", "update_history",
)


def contract_snapshot() -> Dict[str, Any]:
    """返回快照的深拷贝（防调用方就地篡改全局事实源）。"""
    return json.loads(json.dumps(_SNAPSHOT, ensure_ascii=False))


def tool_schema(name: str) -> Optional[Dict[str, Any]]:
    """按名字取白名单 tool 的对外 schema；不在白名单返回 None。"""
    return next((t for t in TOOL_SCHEMAS if t["name"] == name), None)


def is_blacklisted(name: str) -> bool:
    """名字是否命中 ADR-0004 禁暴露的四类危险写（含常见别名）。"""
    normalized = (name or "").strip().lower().replace("-", "_").replace(".", "_")
    if normalized in BLACKLIST or (name or "").strip().lower() in BLACKLIST:
        return True
    if normalized.startswith("history/") or normalized.startswith("history_"):
        return True
    return any(token in normalized for token in _DANGEROUS_TOKENS)


def is_allowlisted(name: str) -> bool:
    return name in TOOL_NAMES


__all__ = [
    "CONTRACT_VERSION", "MCP_PROTOCOL_VERSION", "TRANSPORT", "TRUST_BOUNDARY",
    "CAPABILITIES", "SERVER_INFO", "SERVER_NAME", "SERVER_VERSION",
    "TOOL_SCHEMAS", "TOOL_NAMES", "RESOURCE_SCHEMAS", "BLACKLIST",
    "contract_snapshot", "tool_schema", "is_blacklisted", "is_allowlisted",
]

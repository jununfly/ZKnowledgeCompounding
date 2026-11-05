"""ZKC · MCP 攻击面枚举表的可机读实现（ADR-0004 强制章节）。

三列固定：入口（server 暴露端点）/ 出口（数据流向外部）/ 信任边界。
表以 contract_v1.json 的白名单为唯一名字来源，避免文档表与实装漂移；
单测会断言两者逐项一致，并断言出口恒为空（单边 server，phase 2 才开放）。
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

from zkc.transport.contract import BLACKLIST, TOOL_NAMES, TRUST_BOUNDARY

_GUARDS = {
    "zkc_capture": "写，受 DecisionRouter 分流闸 + 双信号弃权 + review_queue 人审；capture profile 默认开启",
    "zkc_query": "读，响应强制带 evidence_refs 溯源；私人 claim 默认脱敏，须显式授权方可带隐私字段",
    "zkc_review_queue_list": "读，仅列 open 项；不暴露 resolved 历史",
    "zkc_review_queue_resolve": "写，仅标 resolved + HITL 归因；绝不写 interval / distill / meta_claim",
    "zkc_scheduler_due": "读，该关注清单（注意力语义的首个 resource）",
}
_KINDS = {
    "zkc_capture": "write",
    "zkc_query": "read",
    "zkc_review_queue_list": "read",
    "zkc_review_queue_resolve": "write",
    "zkc_scheduler_due": "read",
}

ATTACK_SURFACE: Dict[str, Any] = {
    "entry": [
        {"name": name, "kind": _KINDS[name], "guard": _GUARDS[name]}
        for name in TOOL_NAMES
    ],
    # 单边 server 不调外部；phase 2 双向 client 才开放，须显式决议。
    "egress": [],
    "trustBoundary": (
        "默认 stdio 零网络面、无需 token；外部 agent 一律零信任；"
        "写白名单 + 私人 claim 沙箱；跨机 HTTP/SSE 须端到端加密隧道，"
        "否则不变式⑤自动否决。" + TRUST_BOUNDARY
    ),
    "blacklist": sorted(BLACKLIST),
    "injectionGate": [
        {"id": "unauthorized_write_rejected",
         "assertion": "distill/trigger、interval_adjustment、meta_claim 等未授权写返回权限拒绝"},
        {"id": "private_claim_absent_in_query",
         "assertion": "私人 claim 内容不出现在 zkc_query 响应体（默认脱敏）"},
        {"id": "review_queue_overreach_audited",
         "assertion": "越权企图回写 review_queue 留痕（tool_denied / hitl_attribution 审计事件）"},
    ],
}


def attack_surface_table() -> Dict[str, Any]:
    """返回深拷贝，防调用方就地改全局表。"""
    return copy.deepcopy(ATTACK_SURFACE)


def entry_names() -> List[str]:
    return [e["name"] for e in ATTACK_SURFACE["entry"]]


__all__ = ["ATTACK_SURFACE", "attack_surface_table", "entry_names"]

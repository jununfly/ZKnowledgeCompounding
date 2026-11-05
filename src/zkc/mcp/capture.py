"""ZKC · `zkc_capture` 完整规格（ADR-0004 §3.3）。

push 模型：agent 显式把文档推给 ZKC，ZKC 不主动拉取。
所有文档**必须过 `ingest_with_routing` 分流闸**——双信号路由、弃权入
review_queue 人审；本层不提供任何「预设轨 / 直写」旁路。

capture profile（默认开启）= 安全写契约：
- 允许写：只加源节点 `node`；
- 禁止写：interval_adjustment / distill/trigger / meta_claim / 历史行 delete/update；
- 不绕过 HITL：vague 一律入 review_queue 由人定轨；
- 不可信内容：只作纯文本存储，命中注入标记仅留痕，绝不解析执行；
- 量级节流：单次 ≤1000 文档，超出显式拒绝并要求分批；
- 走 decay 初始化：按 decay 模型算初始 decay_score（静态轨恒 0）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from zkc.decay import compute_decay_score
from zkc.ingest import ingest_with_routing

from .injection import detect_injection_markers

CAPTURE_PROFILE = "capture"
MAX_DOCUMENTS_PER_CALL = 1000

FORBIDDEN_WRITES: FrozenSet[str] = frozenset({
    "interval_adjustment", "distill/trigger", "meta_claim",
    "history/delete", "history/update",
})


@dataclass(frozen=True)
class CaptureProfile:
    """capture 的安全写白名单契约（默认开启）。"""

    enabled: bool = True
    max_documents: int = MAX_DOCUMENTS_PER_CALL
    allowed_writes: FrozenSet[str] = field(default_factory=lambda: frozenset({"node"}))
    forbidden_writes: FrozenSet[str] = field(default_factory=lambda: FORBIDDEN_WRITES)
    untrusted_content: bool = True

    def __post_init__(self) -> None:
        overlap = self.allowed_writes & self.forbidden_writes
        if overlap:
            raise ValueError(f"capture profile 写集合自相矛盾：{sorted(overlap)}")


CAPTURE_PROFILE_DEFAULT = CaptureProfile()


def initialize_decay(node, now: datetime) -> float:
    """按现有 decay 模型算初始分（静态轨恒 0、动态轨按 linear + interval）。"""
    return compute_decay_score(node, now)


def capture_documents(
    documents: List[Dict[str, Any]],
    *,
    store,
    decision_router,
    lexical_router=None,
    llm_available: bool = True,
    audit_sink: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    profile: Optional[CaptureProfile] = None,
) -> Dict[str, Any]:
    """把一批文档过分流闸后落库；返回含 profile / 注入留痕 / decay 的结果。"""
    profile = profile or CAPTURE_PROFILE_DEFAULT
    if not profile.enabled:
        raise ValueError("capture profile 未开启，拒绝写入")
    if len(documents) > profile.max_documents:
        raise ValueError(
            f"单次 capture 文档数上限 {profile.max_documents}"
            f"（收到 {len(documents)}），请分批"
        )

    def audit(event: str, fields: Dict[str, Any]) -> None:
        if audit_sink is not None:
            audit_sink(event, fields)

    now = datetime.now(timezone.utc)
    items: List[Dict[str, Any]] = []
    untrusted_items = 0
    all_markers: set = set()

    for doc in documents:
        title = (doc.get("title") or "").strip()
        if not title:
            raise ValueError("每条 document 必须带非空 title")
        content = doc.get("content")
        markers = detect_injection_markers(content or "") if profile.untrusted_content else []

        node, routing = ingest_with_routing(
            title=title,
            content=content,
            text_for_routing=title + (" " + content if content else ""),
            decision_router=decision_router,
            lexical_router=lexical_router,
            llm_available=llm_available,
            store=store,
        )

        score = initialize_decay(node, now)
        store.nodes.update_decay(node.id, score)

        if markers:
            untrusted_items += 1
            all_markers.update(markers)
            audit("injection_attempt_detected", {
                "node_id": str(node.id), "markers": markers,
                "profile": CAPTURE_PROFILE,
                "handling": "内容按纯文本存储，不解析不执行",
            })
        audit("capture_ingested", {
            "node_id": str(node.id), "track": routing.track,
            "profile": CAPTURE_PROFILE, "decay_score": score,
        })

        items.append({
            "node_id": str(node.id),
            "track": routing.track,
            "vague": routing.track == "unrouted",
            "routing_source": routing.source,
            "decay_score": score,
            "untrusted": bool(markers),
            "injection_markers": markers,
            "writes": ["node"],
        })

    return {
        "profile": CAPTURE_PROFILE,
        "profile_enabled": True,
        "allowed_writes": sorted(profile.allowed_writes),
        "forbidden_writes": sorted(profile.forbidden_writes),
        "gate": "DecisionRouter + 双信号弃权 + review_queue 人审",
        "captured": len(items),
        "items": items,
        "decay_initialized": True,
        "untrusted_items": untrusted_items,
        "injection_markers": sorted(all_markers),
        "note": "不可信内容只作纯文本存储；注入标记仅留痕，不构成任何写授权",
    }


__all__ = [
    "CAPTURE_PROFILE", "MAX_DOCUMENTS_PER_CALL", "FORBIDDEN_WRITES",
    "CaptureProfile", "CAPTURE_PROFILE_DEFAULT", "initialize_decay",
    "capture_documents",
]

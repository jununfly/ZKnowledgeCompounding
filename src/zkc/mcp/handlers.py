"""ZKC · 五个白名单 tool 的 handler（command API 适配层）。

这一层是 transport seam 的**调用方**：它只调 `zkc.ingest` / `zkc.search` /
repository protocol 暴露的既有能力，不写 DDL、不拼 SQL、不绕过分流闸。
`McpServer` 本身完全不知道这些 handler 的存在——由 wiring 注入。

安全不变量（ADR-0004）：
- 黑名单四类危险写不注册为 tool，越权调用在协议层被拒并留痕；
- `zkc_query` 默认脱敏：不返回 node.content、不返回 claim.statement，
  `scope=private_claims` 未经显式授权直接拒绝；
- `zkc_review_queue_resolve` 只标 resolved + 记 HITL 归因，绝不写 interval。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from zkc.search import search

from .capture import capture_documents
from .injection import detect_injection_markers

SchedulerHandler = Callable[[Dict[str, Any]], Any]


def _emit(sink, event: str, **fields: Any) -> None:
    if sink is None:
        return
    try:
        sink({"event": event, **fields})
    except Exception:
        pass


def _as_of(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def build_handlers(
    *,
    store_provider: Callable[[], Any],
    routing_provider: Callable[[], tuple],
    audit_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    allow_private_claims: bool = False,
    capture_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    capture_profile: Optional[Any] = None,
) -> Dict[str, SchedulerHandler]:
    """返回 {tool_name: handler(arguments)->dict}；store 只在 handler 调用时取。"""
    emit = lambda event, **kw: _emit(audit_sink, event, **kw)  # noqa: E731

    def capture(arguments: Dict[str, Any]) -> Dict[str, Any]:
        decision_router, lexical_router, llm_available = routing_provider()
        fn = capture_fn or capture_documents
        return fn(
            arguments["documents"],
            store=store_provider(),
            decision_router=decision_router,
            lexical_router=lexical_router,
            llm_available=llm_available,
            audit_sink=lambda event, fields: emit(event, **fields),
            profile=capture_profile,
        )

    def query(arguments: Dict[str, Any]) -> Dict[str, Any]:
        scope = arguments.get("scope", "public")
        if scope == "private_claims" and not allow_private_claims:
            emit("private_scope_denied", tool="zkc_query", scope=scope,
                 reason="私人 claim 需显式 scope 授权，默认脱敏")
            return {
                "denied": True, "items": [], "scope": scope,
                "reason": "私人 claim 默认脱敏；未获显式授权不返回隐私字段",
            }
        store = store_provider()
        result = search(store, q=arguments["query"], limit=arguments.get("limit", 20))
        items = []
        for hit in result["hits"]:
            node = hit.node
            claims = store.claims.list_by_evidence(node.id)
            refs = sorted({str(ref) for claim in claims for ref in claim.evidence_refs})
            items.append({
                "node_id": str(node.id),
                "title": node.title,
                "track": node.track,
                "decay_score": round(node.decay_score, 3),
                "source": hit.source,
                "evidence_refs": refs,
            })
        return {
            "items": items, "count": len(items), "scope": scope,
            "degraded": result["degraded"],
            "privacy": "node.content / meta_claim.statement 不出现在响应体",
        }

    def review_queue_list(arguments: Dict[str, Any]) -> Dict[str, Any]:
        items = store_provider().review_queue.list_open()
        action = arguments.get("action")
        if action:
            items = [it for it in items if it.action == action]
        limit = arguments.get("limit", 50)
        view = [{
            "id": str(it.id), "node_id": str(it.node_id), "action": it.action,
            "reason": it.reason, "resolved": False,
            "created_at": it.created_at.isoformat() if it.created_at else None,
        } for it in items[:limit]]
        return {"items": view, "count": len(view), "include_resolved": False}

    def review_queue_resolve(arguments: Dict[str, Any]) -> Dict[str, Any]:
        # 外生锚铁律：HITL 归因必须由人给出，文档注入的指令不得冒充人工标注回写队列。
        markers = detect_injection_markers(arguments.get("attribution", ""))
        if markers:
            emit("review_queue_overreach_audited",
                 tool="zkc_review_queue_resolve", markers=markers,
                 reason="注入指令试图回写 review_queue")
            raise ValueError(
                f"检测到注入指令（{', '.join(markers)}）：HITL 归因不得由文档注入伪造"
            )
        try:
            item_id = UUID(arguments["item_id"])
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"item_id 不是合法 UUID：{arguments.get('item_id')!r}") from exc
        store = store_provider()
        open_ids = {it.id for it in store.review_queue.list_open()}
        if item_id not in open_ids:
            raise ValueError(f"复审条目 {item_id} 不存在或已 resolved")
        store.review_queue.resolve(item_id)
        emit("hitl_attribution", tool="zkc_review_queue_resolve",
             item_id=str(item_id), attribution=arguments["attribution"])
        return {
            "resolved": True, "item_id": str(item_id),
            "attribution": arguments["attribution"],
            "writes": ["review_queue.resolved"],
            "note": "仅标 resolved + HITL 归因；不写 interval、不触发 distill",
        }

    def scheduler_due(arguments: Dict[str, Any]) -> Dict[str, Any]:
        as_of = _as_of(arguments.get("as_of"))
        nodes = store_provider().nodes.list_due_for_review(as_of)
        limit = arguments.get("limit", 50)
        items = []
        for node in nodes:
            interval = node.review_interval
            items.append({
                "node_id": str(node.id),
                "title": node.title,
                "track": node.track,
                "decay_score": round(node.decay_score, 3),
                "review_interval_days": (
                    interval.total_seconds() / 86400.0 if interval else None
                ),
                "interval_source": node.interval_source,
            })
        return {
            "as_of": as_of.isoformat(),
            "items": items[:limit],
            "due_count": len(items),
            "semantics": "注意力预算：该关注清单（decay 到期且需投入注意力）",
        }

    return {
        "zkc_capture": capture,
        "zkc_query": query,
        "zkc_review_queue_list": review_queue_list,
        "zkc_review_queue_resolve": review_queue_resolve,
        "zkc_scheduler_due": scheduler_due,
    }


__all__ = ["build_handlers"]

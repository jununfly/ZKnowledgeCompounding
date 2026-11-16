"""真删执行（ADR-0013 Q6/Q8 / S5）：闸门 → 删节点 → 独立审计。

由 sweep（S6）调用；本模块也可单独用于人环显式真删。硬约束：
  - 必先过 S4 引用闸门；被引用 → 拒删（gate_and_report 已写 task_queue 告警）。
  - 墓碑未满 TTL → 拒删（防绕过 7 天反悔窗口）。
  - 审计在删前读 title 快照；purge 事件 node_id 无 FK、不记 content。
  - attention_observation（按天聚合埋点）不随节点回退。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from zkc.purge_gate import gate_and_report
from zkc.repository.models import DeletionAudit


def _as_uuid(node_id) -> UUID:
    return node_id if isinstance(node_id, UUID) else UUID(str(node_id))


def purge_node(store, node_id, *, operator: str, at: datetime | None = None,
               ttl_days: int = 7, enforce_ttl: bool = True) -> dict:
    """过闸门 + TTL 检查后真删节点，写独立 purge 审计。

    enforce_ttl=False 仅供人环显式真删（须 zj 明确）；sweep 调用保持 True。
    """
    nid = _as_uuid(node_id)
    at = at or datetime.now()
    node = store.nodes.get(nid)
    if node is None:
        return {"purged": False, "reason": "node_not_found", "node_id": str(nid)}
    if node.deleted_at is None:
        return {"purged": False, "reason": "not_tombstoned", "node_id": str(nid)}

    if enforce_ttl and node.deleted_at + timedelta(days=ttl_days) > at:
        return {"purged": False, "reason": "ttl_not_elapsed", "node_id": str(nid)}

    gate = gate_and_report(store, nid, now=at)
    if not gate["allowed"]:
        return {
            "purged": False, "reason": "reference_blocked",
            "node_id": str(nid), "blockers": gate["blockers"],
        }

    # 删前抓快照（删后 node 行消失）
    title = node.title
    tombstoned_at = node.deleted_at
    store.purge_node(nid)
    store.append_deletion_audit(DeletionAudit(
        node_id=nid, title=title, tombstoned_at=tombstoned_at,
        event_kind="purge", deleted_at=at, ttl_days=ttl_days, operator=operator,
        reason="ttl_expired" if enforce_ttl else "human_forced",
    ))
    return {"purged": True, "node_id": str(nid), "operator": operator,
            "deleted_at": at, "event_kind": "purge"}

"""节点墓碑人环操作 + 生命周期审计（ADR-0013 / 阶段三 S3）。

人环硬约束（Q7）：mark / restore 的调用即 zj 本人授权，operator 必填且非空；
本模块**只提供显式人环函数**，不含任何自动触发/批量默认路径。sweep（S6）只处理
已满 TTL 的既有墓碑，绝不调用本模块的 mark/restore。

本模块只做「标记 + 审计留痕」，不写标注埋点（不污染外生锚 A/B）、不改 interval、
不触发 distill。真删闸门（S4）、CASCADE + purge 审计（S5）、月扫（S6）在后续切片。
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from zkc.repository.models import DeletionAudit


def _require_operator(operator: str) -> str:
    if not operator or not operator.strip():
        raise ValueError("operator 必填且非空：墓碑标记/恢复是 zj 本人的人环操作，不得缺省")
    return operator.strip()


def mark_tombstone(store, node_id: UUID, *, operator: str,
                   at: datetime | None = None, reason: str | None = None) -> dict:
    """置墓碑（is_delete=1）：人环标记 + 写 tombstone 审计事件。幂等（已墓碑 no-op）。"""
    op = _require_operator(operator)
    node_id = UUID(str(node_id)) if not isinstance(node_id, UUID) else node_id
    node = store.nodes.get(node_id)
    if node is None:
        raise KeyError(f"node not found: {node_id}")
    # 默认时刻必须 aware UTC：sweep/daily 均用 datetime.now(timezone.utc) 做 cutoff，
    # naive 本地时区（如 UTC+8）会把墓碑时刻未来化，导致 deleted_at <= now 恒扫不到。
    at = at or datetime.now(timezone.utc)
    applied = node.deleted_at is None
    if applied:
        store.nodes.tombstone(node_id, at)
        store.append_deletion_audit(DeletionAudit(
            node_id=node_id, title=node.title, tombstoned_at=at,
            event_kind="tombstone", operator=op, reason=reason,
        ))
    return {
        "applied": applied, "node_id": str(node_id), "operator": op,
        "deleted_at": at if applied else node.deleted_at,
        "event_kind": "tombstone",
    }


def restore_node(store, node_id: UUID, *, operator: str,
                 at: datetime | None = None, reason: str | None = None) -> dict:
    """墓碑恢复（is_delete=0）：人环恢复 + 写 restore 审计事件。幂等（未墓碑 no-op）。"""
    op = _require_operator(operator)
    node_id = UUID(str(node_id)) if not isinstance(node_id, UUID) else node_id
    node = store.nodes.get(node_id)
    if node is None:
        raise KeyError(f"node not found: {node_id}")
    at = at or datetime.now(timezone.utc)
    applied = node.deleted_at is not None
    tombstoned_at = node.deleted_at
    if applied:
        store.nodes.restore(node_id)
        store.append_deletion_audit(DeletionAudit(
            node_id=node_id, title=node.title, tombstoned_at=tombstoned_at,
            event_kind="restore", operator=op, reason=reason,
        ))
    return {
        "applied": applied, "node_id": str(node_id), "operator": op,
        "event_kind": "restore", "restored_at": at if applied else None,
    }


def list_audit_events(store, node_id: UUID) -> list[dict]:
    """只读：按 node_id 列审计事件（dict 化供 CLI/UI 消费）。"""
    return [
        {
            "id": str(a.id), "node_id": str(a.node_id), "title": a.title,
            "tombstoned_at": a.tombstoned_at, "event_kind": a.event_kind,
            "deleted_at": a.deleted_at, "ttl_days": a.ttl_days,
            "operator": a.operator, "reason": a.reason, "created_at": a.created_at,
        }
        for a in store.list_deletion_audit(node_id)
    ]

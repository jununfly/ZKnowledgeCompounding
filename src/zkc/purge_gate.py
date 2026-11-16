"""真删引用闸门（ADR-0013 Q6 / S4）。

真删 node 前必过本闸门：扫三处对该节点的引用，任一命中 → 拒绝真删并写 task_queue
告警（避免静默永久挂墓碑）；无引用 → 放行。

三处引用（真实 schema 名，注意 ADR-0013 早期笔误 claim_evidence 不存在）：
  1. meta_claim.evidence_refs       (uuid[] 无 FK，CASCADE 管不到 → 必须手扫)
  2. modeling_artifact.evidence_refs (uuid[] 无 FK，同上)
  3. citation.citing_node_id         (有 FK ON DELETE CASCADE，但 Q6 要求有引用即拒)

本模块不删节点（真删在 S5），不写标注埋点，不改 interval。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from zkc.repository.models import TaskSpec


def _as_uuid(node_id) -> UUID:
    return node_id if isinstance(node_id, UUID) else UUID(str(node_id))


def check_purge_blockers(store, node_id) -> list[dict]:
    """扫三处引用，返回 blocker 列表（空=可删）。每处记 kind + 引用数量/id。"""
    nid = _as_uuid(node_id)
    blockers: list[dict] = []

    claims = store.claims.list_by_evidence(nid)
    if claims:
        blockers.append({
            "kind": "claim_evidence", "table": "meta_claim",
            "field": "evidence_refs", "count": len(claims),
            "refs": [str(c.id) for c in claims],
        })
    artifacts = store.artifacts.list_by_evidence(nid)
    if artifacts:
        blockers.append({
            "kind": "artifact_evidence", "table": "modeling_artifact",
            "field": "evidence_refs", "count": len(artifacts),
            "refs": [str(a.id) for a in artifacts],
        })
    cit = store.node_citation_count(nid)
    if cit:
        blockers.append({
            "kind": "citation", "table": "citation",
            "field": "citing_node_id", "count": cit, "refs": [],
        })
    return blockers


def gate_and_report(store, node_id, *, now: datetime | None = None) -> dict:
    """闸门判定 + 拒绝告警。返回 {allowed, blockers, task_enqueued}。

    拒绝时写一条 task_queue 告警（kind=tombstone_purge_blocked，按 (day, kind) 幂等），
    提示 zj 人工决定「改 claim 的 evidence_refs / 放弃真删」——不静默挂起。
    """
    nid = _as_uuid(node_id)
    blockers = check_purge_blockers(store, nid)
    now = now or datetime.now()
    allowed = not blockers
    enqueued = False
    if not allowed:
        node = store.nodes.get(nid)
        title = node.title if node else str(nid)
        store.tasks.ensure_today([TaskSpec(
            day=now, category="alert", kind="tombstone_purge_blocked",
            title=f"墓碑真删被引用阻塞：{title}",
            detail="; ".join(
                f"{b['table']}.{b['field']}×{b['count']}" for b in blockers
            ),
            source_rule="S4:purge_reference_gate",
            payload={"node_id": str(nid), "blockers": blockers},
        )])
        enqueued = True
    return {
        "allowed": allowed, "node_id": str(nid),
        "blockers": blockers, "task_enqueued": enqueued,
    }

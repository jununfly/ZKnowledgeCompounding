"""ZKC · 内存实现（P1.2）：供 TDD 与无 DB 环境使用，证明 seam 可替换。

不依赖任何 DB 驱动；状态存于进程内 dict。生产默认走 Pg 实现（见 pg.py）。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from .models import (
    AttentionObservation,
    Claim,
    Context,
    Edge,
    MetricInputs,
    Node,
    ReviewItem,
    SchedulableNode,
)
from .. import tuning
from .errors import ConcurrentModification
from .protocols import (
    AttentionRepository,
    ClaimRepository,
    ContextRepository,
    EdgeRepository,
    NodeRepository,
    ReviewQueueRepository,
    Storage,
)


class MemoryNodeRepository(NodeRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, Node] = {}
        self._versions: dict[UUID, list[Node]] = {}  # 逻辑 id -> 历史版本快照（append-only）
        self._audit_log: list[dict] = []             # interval_adjustment 的内存等价（仅供自检）

    def save(self, node: Node) -> Node:
        if node.id is None:
            node.id = uuid4()
            node.tx_from = datetime.now()
            node.tx_to = None
            node.version_seq = 1
            stored = replace(node)
            self._rows[stored.id] = stored
            return replace(stored)
        else:
            old = self._rows.get(node.id)
            if old is not None:
                # OCC：调用方持有版本必须与当前一致，否则视为过期写入冲突
                if node.version_seq != old.version_seq:
                    raise ConcurrentModification(
                        f"node {node.id} 版本冲突：期望 version_seq={node.version_seq}，"
                        f"当前为 {old.version_seq}"
                    )
                # append-only：存旧版本的不可变副本并闭合 tx_to，绝不改写历史
                snap = replace(old)
                snap.tx_to = datetime.now()
                self._versions.setdefault(node.id, []).append(snap)
            node.tx_from = datetime.now()
            node.tx_to = None
            node.version_seq = (old.version_seq if old is not None else 1) + 1
            stored = replace(node)
            self._rows[node.id] = stored
            return replace(stored)

    def get(self, node_id: UUID) -> Node | None:
        # 返回副本：调用方对返回对象的修改不应污染已存状态（与 Pg 每次物化新对象一致）
        stored = self._rows.get(node_id)
        return replace(stored) if stored is not None else None

    def history(self, node_id: UUID) -> list[Node]:
        vs = list(self._versions.get(node_id, []))
        cur = self._rows.get(node_id)
        if cur is not None:
            vs.append(cur)
        return vs

    def list_by_track(self, track: str) -> list[Node]:
        return [n for n in self._rows.values() if n.track == track]

    def list_due_for_review(self, as_of: datetime) -> list[Node]:
        # 阈值走 tuning（禁止裸数字，P1.4 铁律）：SURFACE_THRESHOLD=0.6 进入注意力
        surface = tuning.get("SURFACE_THRESHOLD")
        out: list[Node] = []
        for n in self._rows.values():
            if n.review_interval is None or n.last_reviewed_at is None:
                # 未设定复审节奏 → 不在「到期」判定内（交由 L1 基线补齐）
                continue
            if n.decay_score >= surface and (n.last_reviewed_at + n.review_interval) <= as_of:
                out.append(n)
        return out

    def update_decay(self, node_id: UUID, decay_score: float, version_seq: int | None = None) -> None:
        # 内存实现：与 Pg 轻量路径一致（c2 决议 A-1a，2026-10-31）—— decay_score 是
        # compute_decay_score 的派生投影（可重算），并非事实：不写历史快照、不 bump tx_from
        # （tx_from 始终标记「上次事实变更」），仅更新派生列并自增 version_seq 保活 OCC。
        cur = self._rows[node_id]
        if version_seq is not None and version_seq != cur.version_seq:
            raise ConcurrentModification(
                f"node {node_id} decay 更新版本冲突：期望 version_seq={version_seq}，"
                f"当前为 {cur.version_seq}"
            )
        cur.decay_score = decay_score
        cur.version_seq += 1

    def set_interval(
        self, node_id: UUID, interval: timedelta, source: str, reason: str,
        version_seq: int | None = None,
    ) -> None:
        cur = self._rows[node_id]
        if version_seq is not None and version_seq != cur.version_seq:
            raise ConcurrentModification(
                f"node {node_id} interval 设置版本冲突：期望 version_seq={version_seq}，"
                f"当前为 {cur.version_seq}"
            )
        snap = replace(cur)
        snap.tx_to = datetime.now()
        self._versions.setdefault(node_id, []).append(snap)
        cur.review_interval = interval
        cur.interval_source = source
        cur.tx_from = datetime.now()
        cur.tx_to = None
        cur.version_seq += 1

    def set_baseline_interval(
        self, node_id: UUID, interval: timedelta, source: str, reason: str
    ) -> None:
        cur = self._rows[node_id]
        snap = replace(cur)
        snap.tx_to = datetime.now()
        self._versions.setdefault(node_id, []).append(snap)
        cur.baseline_interval = interval
        cur.review_interval = interval
        cur.interval_source = source
        cur.tx_from = datetime.now()
        cur.tx_to = None
        cur.version_seq += 1

    def audit_interval(
        self, node_id: UUID, kind: str, old_days: float | None,
        new_days: float, reason: str, produced_by: UUID | None = None,
    ) -> None:
        # 内存实现：审计痕迹仅记到内存列表（无独立 interval_adjustment 表），
        # 仅供纯逻辑自检；真实持久化与级联回滚由 PG 实现负责。
        self._audit_log.append(
            dict(node_id=node_id, kind=kind, old_days=old_days,
                 new_days=new_days, reason=reason, produced_by=produced_by)
        )

    def mark_reviewed(self, node_id: UUID, at: datetime) -> None:
        # 内存实现：与 PG 轻量路径一致 —— 复位衰减时钟（last_reviewed_at + decay_score=0）。
        cur = self._rows[node_id]
        cur.last_reviewed_at = at
        cur.decay_score = 0.0
        cur.version_seq += 1


class MemoryClaimRepository(ClaimRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, Claim] = {}

    def save(self, claim: Claim) -> Claim:
        if claim.id is None:
            claim.id = uuid4()
            claim.version_seq = 1
            stored = replace(claim)
        else:
            old = self._rows.get(claim.id)
            if old is not None:
                if claim.version_seq != old.version_seq:
                    raise ConcurrentModification(
                        f"claim {claim.id} 版本冲突：期望 version_seq={claim.version_seq}，"
                        f"当前为 {old.version_seq}"
                    )
                claim.version_seq = old.version_seq + 1
            stored = replace(claim)
        self._rows[stored.id] = stored
        return replace(stored)

    def get(self, claim_id: UUID) -> Claim | None:
        return self._rows.get(claim_id)

    def list_by_evidence(self, node_id: UUID) -> list[Claim]:
        return [c for c in self._rows.values() if node_id in c.evidence_refs]


class MemoryEdgeRepository(EdgeRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, Edge] = {}

    def link(
        self,
        src: UUID,
        dst: UUID,
        kind: str,
        weight: float | None = None,
        produced_by: UUID | None = None,
    ) -> Edge:
        e = Edge(id=uuid4(), src=src, dst=dst, kind=kind, weight=weight, produced_by=produced_by)
        self._rows[e.id] = e
        return e

    def list_for_node(self, node_id: UUID) -> list[Edge]:
        return [e for e in self._rows.values() if e.src == node_id or e.dst == node_id]

    def delete(self, edge_id: UUID) -> None:
        self._rows.pop(edge_id, None)


class MemoryContextRepository(ContextRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, Context] = {}
        self._members: dict[UUID, dict[UUID, float]] = {}  # context_id -> {node_id: weight}

    def save(self, context: Context) -> Context:
        if context.id is None:
            context.id = uuid4()
            context.version_seq = 1
            stored = replace(context)
        else:
            old = self._rows.get(context.id)
            if old is not None:
                if context.version_seq != old.version_seq:
                    raise ConcurrentModification(
                        f"context {context.id} 版本冲突：期望 version_seq={context.version_seq}，"
                        f"当前为 {old.version_seq}"
                    )
                context.version_seq = old.version_seq + 1
            stored = replace(context)
        self._rows[stored.id] = stored
        return replace(stored)

    def add_member(
        self,
        context_id: UUID,
        node_id: UUID,
        weight: float = 1.0,
        produced_by: UUID | None = None,
    ) -> None:
        self._members.setdefault(context_id, {})[node_id] = weight

    def list_members(self, context_id: UUID) -> list[UUID]:
        return list(self._members.get(context_id, {}).keys())

    def list_for_node(self, node_id: UUID) -> list[Context]:
        return [
            self._rows[cid]
            for cid in self._members
            if node_id in self._members[cid]
        ]


class MemoryReviewQueueRepository(ReviewQueueRepository):
    def __init__(self) -> None:
        self._rows: dict[UUID, ReviewItem] = {}
        self._seq: list[UUID] = []

    def enqueue(
        self, node_id: UUID, action: str, reason: str | None = None
    ) -> ReviewItem:
        item = ReviewItem(id=uuid4(), node_id=node_id, action=action, reason=reason)
        self._rows[item.id] = item
        self._seq.append(item.id)
        return item

    def pop_open(self, limit: int | None = None) -> list[ReviewItem]:
        out = [self._rows[i] for i in self._seq if not self._rows[i].resolved]
        return out[:limit] if limit else out

    def resolve(self, item_id: UUID) -> None:
        self._rows[item_id].resolved = True

    def list_open(self) -> list[ReviewItem]:
        return [self._rows[i] for i in self._seq if not self._rows[i].resolved]


class MemoryAttentionRepository(AttentionRepository):
    def __init__(self) -> None:
        self._rows: dict[datetime, AttentionObservation] = {}

    def record_observation(self, obs: AttentionObservation) -> None:
        self._rows[obs.day] = obs

    def get(self, day) -> AttentionObservation | None:
        return self._rows.get(day)

    def list_recent(self, days: int = 30) -> list[AttentionObservation]:
        # 内存实现按插入序返回最近 days 条（不做真实日期计算，仅供单测）
        items = list(self._rows.values())
        return items[-days:] if days else items


class MemoryStorage(Storage):
    """聚合 6 个内存仓库；provenance 用自增计数模拟 transform id。"""

    def __init__(self) -> None:
        self.nodes = MemoryNodeRepository()
        self.claims = MemoryClaimRepository()
        self.edges = MemoryEdgeRepository()
        self.contexts = MemoryContextRepository()
        self.review_queue = MemoryReviewQueueRepository()
        self.attention = MemoryAttentionRepository()
        self._transform_seq = 0

    def record_transform(self, kind: str, params: dict) -> UUID:
        self._transform_seq += 1
        # 内存实现用一个确定性的伪 id（测试可重复）
        return UUID(int=self._transform_seq)

    def load_schedulable(self) -> list[SchedulableNode]:
        out = []
        for node in self.nodes._rows.values():
            if node.track != "dynamic" or node.archived_at is not None:
                continue
            nid = node.id
            captured = any(nid in c.evidence_refs for c in self.claims._rows.values())
            conn_count = sum(
                1 for e in self.edges._rows.values() if e.src == nid or e.dst == nid
            )
            self_loop_count = higher_dim_count = 0
            for cid, members in self.contexts._members.items():
                if nid in members:
                    scope = self.contexts._rows[cid].scope
                    if scope == "self_loop":
                        self_loop_count += 1
                    elif scope == "higher_dim":
                        higher_dim_count += 1
            iv = node.review_interval
            bi = node.baseline_interval
            out.append(SchedulableNode(
                id=nid, track=node.track, title=node.title, content=node.content,
                captured=captured, conn_count=conn_count,
                self_loop_count=self_loop_count, higher_dim_count=higher_dim_count,
                interval_days=(iv.total_seconds() / 86400.0) if iv is not None else None,
                baseline_days=(bi.total_seconds() / 86400.0) if bi is not None else None,
                source=node.interval_source, archived=False,
            ))
        return out

    def load_metric_inputs(self) -> MetricInputs:
        """复利度量快照（P5.2）：遍历内存集合。

        注：内存 fake 暂未持久化 modeling_artifact / citation（P3 结合算子落地时补），
        故 artifact_evidence / citations 返回空 —— 对应分量(methodology_output / 复用率
        的 citation 部分)在 fake 下为 0；连接密度 / 衰减可控 / claim 复用口径可完整验证。
        """
        nodes = [
            (n.id, n.track, n.decay_score or 0.0, n.archived_at is not None)
            for n in self.nodes._rows.values()
        ]
        edges = [(e.src, e.dst, e.kind) for e in self.edges._rows.values()]
        claim_evidence = [list(c.evidence_refs) for c in self.claims._rows.values()]
        return MetricInputs(
            nodes=nodes, edges=edges, claim_evidence=claim_evidence,
            artifact_evidence=[], citations=[],
        )

    def revert_interval_transform(self, transform_id: UUID) -> int:
        # 内存实现不持久化 interval_adjustment 表，级联回滚由 PG 负责；
        # 这里仅清掉对应审计痕迹并返回计数（保持协议行为一致）。
        before = len(self._audit_log)
        self._audit_log = [
            a for a in self._audit_log if a.get("produced_by") != transform_id
        ]
        return before - len(self.nodes._audit_log)

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
    Node,
    ReviewItem,
)
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
        out: list[Node] = []
        for n in self._rows.values():
            if n.review_interval is None or n.last_reviewed_at is None:
                # 未设定复审节奏 → 不在「到期」判定内（交由 L1 基线补齐）
                continue
            if n.decay_score >= 0.6 and (n.last_reviewed_at + n.review_interval) <= as_of:
                out.append(n)
        return out

    def update_decay(self, node_id: UUID, decay_score: float, version_seq: int | None = None) -> None:
        # 内存实现：update 也走 append-only 版本快照，与 Pg 语义一致
        cur = self._rows[node_id]
        if version_seq is not None and version_seq != cur.version_seq:
            raise ConcurrentModification(
                f"node {node_id} decay 更新版本冲突：期望 version_seq={version_seq}，"
                f"当前为 {cur.version_seq}"
            )
        snap = replace(cur)
        snap.tx_to = datetime.now()
        self._versions.setdefault(node_id, []).append(snap)
        cur.decay_score = decay_score
        cur.tx_from = datetime.now()
        cur.tx_to = None
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

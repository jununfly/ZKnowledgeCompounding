"""ZKC · repository 协议层（P1.2）：按聚合拆的多协议。

每个聚合一个 ABC，未来切 Kuzu/TerminusDB 只需新增对应实现类，不波及其他聚合。
`Storage` 是门面，聚合 6 个仓库 + 一个 provenance 助手 `record_transform`。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from uuid import UUID

from .models import (
    AttentionObservation,
    Claim,
    Context,
    Edge,
    Node,
    ReviewItem,
)


class NodeRepository(ABC):
    @abstractmethod
    def save(self, node: Node) -> Node: ...

    @abstractmethod
    def get(self, node_id: UUID) -> Node | None: ...

    @abstractmethod
    def history(self, node_id: UUID) -> list[Node]:
        """双时态版本链：返回该逻辑 node 的全部版本（含当前态），按 tx_from 升序。
        append-only —— 历史版本不可变，仅供溯源与「某时刻快照」重建。"""

    @abstractmethod
    def list_by_track(self, track: str) -> list[Node]: ...

    @abstractmethod
    def list_due_for_review(self, as_of: datetime) -> list[Node]:
        """decay_score ≥ tuning.SURFACE_THRESHOLD（见 zkc.tuning）且
        (last_reviewed_at + review_interval) ≤ as_of 的节点。"""

    @abstractmethod
    def update_decay(
        self, node_id: UUID, decay_score: float, version_seq: int | None = None
    ) -> None: ...

    @abstractmethod
    def set_interval(
        self,
        node_id: UUID,
        interval: timedelta,
        source: str,
        reason: str,
        version_seq: int | None = None,
    ) -> None: ...


class ClaimRepository(ABC):
    @abstractmethod
    def save(self, claim: Claim) -> Claim: ...

    @abstractmethod
    def get(self, claim_id: UUID) -> Claim | None: ...

    @abstractmethod
    def list_by_evidence(self, node_id: UUID) -> list[Claim]: ...


class EdgeRepository(ABC):
    @abstractmethod
    def link(
        self,
        src: UUID,
        dst: UUID,
        kind: str,
        weight: float | None = None,
        produced_by: UUID | None = None,
    ) -> Edge: ...

    @abstractmethod
    def list_for_node(self, node_id: UUID) -> list[Edge]: ...

    @abstractmethod
    def delete(self, edge_id: UUID) -> None: ...


class ContextRepository(ABC):
    @abstractmethod
    def save(self, context: Context) -> Context: ...

    @abstractmethod
    def add_member(
        self,
        context_id: UUID,
        node_id: UUID,
        weight: float = 1.0,
        produced_by: UUID | None = None,
    ) -> None: ...

    @abstractmethod
    def list_members(self, context_id: UUID) -> list[UUID]: ...

    @abstractmethod
    def list_for_node(self, node_id: UUID) -> list[Context]: ...


class ReviewQueueRepository(ABC):
    @abstractmethod
    def enqueue(
        self, node_id: UUID, action: str, reason: str | None = None
    ) -> ReviewItem: ...

    @abstractmethod
    def pop_open(self, limit: int | None = None) -> list[ReviewItem]: ...

    @abstractmethod
    def resolve(self, item_id: UUID) -> None: ...

    @abstractmethod
    def list_open(self) -> list[ReviewItem]: ...


class AttentionRepository(ABC):
    @abstractmethod
    def record_observation(self, obs: AttentionObservation) -> None: ...

    @abstractmethod
    def get(self, day) -> AttentionObservation | None: ...

    @abstractmethod
    def list_recent(self, days: int = 30) -> list[AttentionObservation]: ...


class Storage(ABC):
    """门面：聚合 6 个仓库 + provenance 助手。应用只依赖此门面。"""

    nodes: NodeRepository
    claims: ClaimRepository
    edges: EdgeRepository
    contexts: ContextRepository
    review_queue: ReviewQueueRepository
    attention: AttentionRepository

    @abstractmethod
    def record_transform(self, kind: str, params: dict) -> UUID:
        """写一行 `transform`（溯源），返回其 id，供 produced_by 引用。"""

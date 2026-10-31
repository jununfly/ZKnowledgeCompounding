"""ZKC · context 拓扑装配算子（P3.4，生产落地 spike-06）。

设计要点（spike-06 已验证）：
- 一次「装配」= 一个 transform -> 一个 context + 其若干 member；所有产物带 produced_by，
  撤消 transform 时 context + members 级联消失（PG 走 FK CASCADE，Memory 走等价级联）。
- T4.1 自闭环 vs 更高维 context：discover 用 pgvector k-NN 提议更高维 context 的种子邻域。
- 人审成员（produced_by=NULL）可单独增删，不受 transform 级联撤影响。

本算子** provider 无关**：只依赖注入的 Storage 门面，内存 fake 与 PG 同行为，免 DB 单测。
铁律（P1.4）：scope 仅限 ('self_loop' | 'higher_dim')，越界即 ValueError；阈值走 zkc.tuning。
"""
from __future__ import annotations

from uuid import UUID

from .repository.protocols import Storage


class ContextAssembler:
    """context 拓扑装配算子（provider 无关）。"""

    def __init__(self, store: Storage) -> None:
        self.store = store

    def assemble(
        self,
        scope: str,
        node_ids: list[UUID],
        title: str | None = None,
        weight: float = 1.0,
    ) -> tuple[UUID, UUID]:
        """装配一个 context。返回 (context_id, transform_id)。"""
        return self.store.assemble_context(scope, node_ids, title, weight)

    def revert(self, transform_id: UUID) -> int:
        """撤消装配：删 transform -> 级联撤 context + members。返回撤掉的 context 数。"""
        return self.store.revert_assembly(transform_id)

    def discover(self, seed_node_id: UUID, k: int = 5) -> list:
        """T4.1：种子节点的 k 近邻（PG 走 pgvector；内存 fake 返回空）。"""
        return self.store.discover_higher_dim(seed_node_id, k)

    def add_human_member(
        self, context_id: UUID, node_id: UUID, weight: float = 1.0
    ) -> None:
        """人审添加成员（produced_by=NULL，可单独删）。"""
        self.store.contexts.add_member_human(context_id, node_id, weight)

    def remove_human_member(self, context_id: UUID, node_id: UUID) -> None:
        """仅删人审成员（produced_by IS NULL）；transform 产成员须走 revert。"""
        self.store.contexts.remove_member_human(context_id, node_id)

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
    LLMCallScore,
    MetricInputs,
    ModelingArtifact,
    Node,
    ReviewItem,
    SchedulableNode,
    TaskItem,
    TaskSpec,
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
        (last_reviewed_at + review_interval) ≤ as_of 的节点。

        **硬契约（D2）**：必须排除 ``archived_at`` 非空的节点——归档节点退出
        整个调度回路（due 队列、queue_remaining 真值收口、衰减维护扫描）。
        任何新后端实现都要满足，由 ``make invariant`` 的 P3 谓词机械守门。
        """

    @abstractmethod
    def count_nodes_created_since(self, since: datetime) -> int:
        """since 之后创建的节点数（ingest 吞吐真值源，供每日收口 pushed 字段；只读）。"""

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

    @abstractmethod
    def set_baseline_interval(
        self,
        node_id: UUID,
        interval: timedelta,
        source: str,
        reason: str,
    ) -> None:
        """L1 基线赋值：同时写 baseline_interval 与 review_interval（二者在此刻一致）。"""

    @abstractmethod
    def audit_interval(
        self,
        node_id: UUID,
        kind: str,
        old_days: float | None,
        new_days: float,
        reason: str,
        produced_by: UUID | None = None,
    ) -> None:
        """写一行 interval_adjustment（append-only 审计；produced_by 指向 transform 可整体回滚）。"""

    @abstractmethod
    def mark_reviewed(self, node_id: UUID, at: datetime) -> None:
        """复审触碰：复位衰减时钟（last_reviewed_at=at, decay_score=0）。

        闭环关键：标签标注（或浏览）后必须调用，否则 (last_reviewed_at+interval) 永远 ≤ now，
        该条目会立刻「再次到期」陷入死循环；同时 decay 归 0 让下一轮从干净状态重新积累。
        """

    @abstractmethod
    def archive(self, node_id: UUID, at: datetime) -> None:
        """单程票终局：标记节点已归档（archived_at=at）。

        由 expiry.route_and_apply 在「已捕获节点到期 → ARCHIVE」分支调用；归档后节点
        退出 load_schedulable（不再参与调度），但保留在 node_history 供溯源。轻量路径：
        同 update_decay —— 不写历史版本快照、不 bump tx_from（archived_at 是派生状态），
        仅置列并自增 version_seq 保活 OCC。
        """

    @abstractmethod
    def search(
        self,
        track: str | None = None,
        q: str | None = None,
        decay_min: float | None = None,
        decay_max: float | None = None,
        include_archived: bool = False,
        order: str = "created_desc",
        limit: int = 50,
    ) -> list[Node]:
        """P5.1 结构化检索（R18 缓解：主检索路）。

        q 对 title/content 大小写不敏感子串匹配；track 精确过滤；decay 区间对
        decay_score（仅动态轨有语义）；order ∈ {created_desc, created_asc, decay_desc}；
        默认排除已归档。全部可选，组合生效。
        """

    @abstractmethod
    def search_by_embedding(
        self,
        vector: list[float],
        k: int = 10,
        include_archived: bool = False,
        column: str = "embedding",
    ) -> list[tuple[Node, float]]:
        """P5.1 候选召回（R18 缓解：embedding 只做候选，结果交人工确认）。

        query 向量与指定列余弦相似 top-k（pg 用 pgvector <=>，memory 用 Python
        余弦）；无该列向量的节点跳过。返回 (node, sim) 按 sim 降序。
        column ∈ {"embedding"(nomic 768d), "embedding_4096"(qwen3 4096d)}，
        实现必须白名单校验（防注入）。
        """

    @abstractmethod
    def set_embedding_column(
        self, node_id: UUID, column: str, vector: list[float]
    ) -> None:
        """写入指定 embedding 列（1-8-4-1 双列共存；回填/补齐用）。

        派生数据轻量路径（与 update_decay 同理由）：FOR UPDATE 持锁 + version_seq
        自增保活 OCC，但不写 node_history、不 bump tx_from（embedding 非事实）。
        column 白名单同 search_by_embedding。
        """


class ClaimRepository(ABC):
    @abstractmethod
    def save(self, claim: Claim) -> Claim: ...

    @abstractmethod
    def get(self, claim_id: UUID) -> Claim | None: ...

    @abstractmethod
    def list_by_evidence(self, node_id: UUID) -> list[Claim]: ...

    @abstractmethod
    def list_by_status(self, faithfulness_status: str) -> list[Claim]:
        """按 D9 忠实度状态列 claims（P3.5 闸门消费口：pending_human 人审队列、
        human_* 校准语料导出）。值域见 zkc.faithfulness.FAITHFULNESS_STATUSES。"""

    @abstractmethod
    def list_all(self, limit: int = 200) -> list[Claim]:
        """P5.1 复利产物浏览：全部 claims，created_at 降序。"""

    @abstractmethod
    def delete(self, claim_id: UUID) -> None:
        """删除一条 claim（蒸馏撤销路径）；级联由调用方负责（见 zkc.distill.revert_claim）。"""


class ArtifactRepository(ABC):
    """modeling_artifact（结合算子产物）：与 ClaimRepository 同构的捕获载体仓库。"""

    @abstractmethod
    def save(self, artifact: ModelingArtifact) -> ModelingArtifact: ...

    @abstractmethod
    def get(self, artifact_id: UUID) -> ModelingArtifact | None: ...

    @abstractmethod
    def list_by_evidence(self, node_id: UUID) -> list[ModelingArtifact]: ...

    @abstractmethod
    def list_all(self, limit: int = 200) -> list[ModelingArtifact]:
        """P5.1 复利产物浏览：全部 artifacts，created_at 降序。"""

    @abstractmethod
    def delete(self, artifact_id: UUID) -> None:
        """删除一条建模产物（结合撤销路径）；级联由调用方负责（见 zkc.distill.revert_artifact）。"""


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

    @abstractmethod
    def add_member_human(
        self, context_id: UUID, node_id: UUID, weight: float = 1.0
    ) -> None:
        """人审添加成员：produced_by=NULL，可单独删除（不随 transform 级联撤）。"""

    @abstractmethod
    def remove_member_human(self, context_id: UUID, node_id: UUID) -> None:
        """仅删人审成员（produced_by IS NULL）；transform 产成员走 revert_assembly 级联。"""

    @abstractmethod
    def find_higher_dim_for_seed(self, node_id: UUID) -> UUID | None:
        """T4.1 去重闸门：若某 higher_dim context 已含该节点则返回其 id，否则 None。"""


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

    @abstractmethod
    def record_proposal(self, day, kind: str = "higher_dim", seed_id=None) -> None:
        """记录一条「系统提议」（调度层·注意力预算）。kind 区分 higher_dim / self_loop /
        higher_dim_dismissed（人忽略，不占创建额度）。seed_id 记录命中的种子（可空），
        供 dismissed_seed_ids 当日跳过被忽略种子的去重。"""

    @abstractmethod
    def count_proposals(self, day, kind: str = "higher_dim") -> int:
        """当日已提议数（按 kind）。供 scheduling.proposal_budget_for_day 跨种子累计限流。"""

    @abstractmethod
    def dismissed_seed_ids(self, day) -> set:
        """当日被人工忽略（kind='higher_dim_dismissed'）的种子集合。
        供 propose_higher_dim_daily 当日跳过，确保 dismiss 真生效（否则每刷新都再提议）。"""


class TaskQueueRepository(ABC):
    @abstractmethod
    def ensure_today(self, specs: list[TaskSpec]) -> None:
        """幂等 upsert 当日任务：按 (day, kind) 去重，已存在则保留其 status（done 不被覆盖）。"""

    @abstractmethod
    def list_open(self, day) -> list[TaskItem]:
        """某日全部未完成（status='open'）任务，按创建时间升序。"""

    @abstractmethod
    def list_by_day(self, day) -> list[TaskItem]:
        """某日全部任务（含 done），按创建时间升序——供视图统计开放/完成数。"""

    @abstractmethod
    def complete(self, task_id: UUID, at: datetime) -> TaskItem:
        """标记完成：status='done' + completed_at=at；返回更新后的项。"""

    @abstractmethod
    def get(self, task_id: UUID) -> TaskItem | None:
        """按 id 取一项（供完成动作回填）。"""


class ScoreRepository(ABC):
    """llm_call_score（1-5-6）：轻量 LLM 调用度量（Langfuse 替代），append-only。"""

    @abstractmethod
    def record(self, score: LLMCallScore) -> LLMCallScore:
        """落一行调用度量（成功与失败都记）；返回带 id/created_at 的实体。"""

    @abstractmethod
    def set_human_verdict(self, score_id: UUID, verdict: str) -> None:
        """rubric 人工打分回填（'good'|'bad'）；由复审流调用。"""

    @abstractmethod
    def list_recent(self, limit: int = 50) -> list[LLMCallScore]:
        """最近 limit 条（created_at 降序），供观测面板/校准导出。"""


class Storage(ABC):
    """门面：聚合 9 个仓库 + provenance 助手。应用只依赖此门面。"""

    nodes: NodeRepository
    claims: ClaimRepository
    artifacts: ArtifactRepository
    edges: EdgeRepository
    contexts: ContextRepository
    review_queue: ReviewQueueRepository
    attention: AttentionRepository
    scores: ScoreRepository
    tasks: TaskQueueRepository

    @abstractmethod
    def record_transform(self, kind: str, params: dict) -> UUID:
        """写一行 `transform`（溯源），返回其 id，供 produced_by 引用。"""

    @abstractmethod
    def load_schedulable(self) -> list[SchedulableNode]:
        """所有「动态轨 + 未归档」节点的调度信号快照（L1/L2 规则输入，跨聚合查询）。"""

    @abstractmethod
    def load_metric_inputs(self) -> MetricInputs:
        """复利度量所需的普通数据快照（P5.2）；纯函数度量只吃此快照，存储无关。"""

    @abstractmethod
    def revert_interval_transform(self, transform_id: UUID) -> int:
        """逆序恢复某 transform 产生的全部 interval 改动并清空审计痕迹，返回恢复条数。"""

    @abstractmethod
    def assemble_context(
        self, scope: str, node_ids: list[UUID], title: str | None = None, weight: float = 1.0
    ) -> tuple[UUID, UUID]:
        """一次装配：一 transform -> 一 context + 其 members（均带 produced_by）。
        返回 (context_id, transform_id)；撤消时 revert_assembly(transform_id) 级联撤全部。"""

    @abstractmethod
    def revert_assembly(self, transform_id: UUID) -> int:
        """撤消装配：删 transform -> FK CASCADE 撤 context + members（produced_by 级联）。
        返回撤掉的 context 数。"""

    def rollback(self) -> None:
        """丢弃当前未提交事务（pg 实现），memory 为 no-op。

        背景：pg 连接共享且各 repo 方法「成功即 commit」，但失败路径无人回滚——
        一次 CheckViolation 会让连接进入 aborted transaction，后续所有请求
        InFailedSqlTransaction 连坐。web 层异常守卫统一调这里兜底。
        默认 no-op：memory 后端无事务语义。
        """

    @abstractmethod
    def discover_higher_dim(self, seed_node_id: UUID, k: int = 5,
                            column: str = "embedding_4096") -> list:
        """T4.1：种子节点的 k 近邻。默认用 qwen3 4096d 生产召回列（R18 / D4）；
        pg 走 pgvector 余弦、memory 走等价 Python 余弦，双实现语义一致。"""

    @abstractmethod
    def citation_counts(self) -> dict[UUID, int]:
        """P5.1 产物浏览：claim_id -> 被后续条目引用次数（citation 表聚合；内存 fake 恒空）。"""

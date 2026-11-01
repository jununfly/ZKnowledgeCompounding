"""ZKC · repository 层实体模型（P1.2）。

纯 dataclass，无 ORM：seam 只搬运结构化实体，具体存储语义由实现类（Pg / Memory）负责。
这是「依赖最少 + 存储可替换 seam」不变量的一部分——领域代码只认这些类型与 protocol，
不认 psycopg / SQLAlchemy / 图库驱动。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID, uuid4


class Track(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    UNROUTED = "unrouted"


@dataclass
class Node:
    """双轨 + 双时态 + decay + 调度字段（对应 schema `node` 当前态 + `node_history` 版本）。

    双时态版本链（已落地，见 0002 迁移 + PgNodeRepository）：
    - `save` 是 append-only —— 更新时先 snapshot 当前行进 `node_history`（置 `tx_to`），
      再 UPDATE 当前行并刷新 `tx_from`；历史版本永不改写。
    - `tx_from` = 本版本写入的事务时刻；`tx_to` = 被新版本闭合的时刻（当前态为 NULL）。
    """

    id: UUID | None = None
    track: str = Track.UNROUTED.value
    routing_confidence: float | None = None
    title: str = ""
    content: str | None = None
    # 双时态（主要服务静态轨事实演进 + 溯源）
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    # 双时态事务时刻（版本窗口）；当前态 tx_to=None，历史版本有闭合时刻
    tx_from: datetime | None = None
    tx_to: datetime | None = None
    # decay：仅动态轨有意义；静态轨恒 0
    decay_score: float = 0.0
    review_interval: timedelta | None = None
    last_reviewed_at: datetime | None = None
    attention_signal: float = 0.0
    embedding: list[float] | None = None
    archived_at: datetime | None = None
    # D6：基线 interval + 来源（human 不被自动化改写）
    baseline_interval: timedelta | None = None
    interval_source: str = "auto"
    # OCC 乐观版本号（2026-10-31 遗留②解决）：每次写自增，写时校验期望版本
    version_seq: int = 1
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.decay_score < 0 or self.decay_score > 1:
            raise ValueError(f"decay_score 必须 ∈[0,1]，收到 {self.decay_score}")
        if self.interval_source not in ("auto", "human"):
            raise ValueError(f"interval_source 必须 ∈{{auto,human}}，收到 {self.interval_source}")


@dataclass
class Claim:
    """元认知 claim（对应 schema `meta_claim`，D9 忠实度六字段在此）。"""

    id: UUID | None = None
    statement: str = ""
    level: str | None = None
    confidence: float | None = None
    # 溯源权威：claim 存在的前提
    evidence_refs: list[UUID] = field(default_factory=list)
    produced_by: UUID | None = None
    revises: UUID | None = None
    # D9 忠实度闸门六字段
    faithfulness_status: str | None = None
    faithfulness_route: str | None = None
    judge_raw: dict | None = None
    judge_model: str | None = None
    human_verdict: str | None = None
    human_verdict_at: datetime | None = None
    # OCC 乐观版本号（2026-10-31 遗留②解决）
    version_seq: int = 1
    created_at: datetime | None = None


@dataclass
class ModelingArtifact:
    """结合算子产出的建模/方法论产物（对应 schema `modeling_artifact`）。

    与 meta_claim 同语义的「价值升层」载体：evidence_refs 是其来源引用（ZKC 结合语义：
    产物必须带来源），也是节点「已捕获」的第二个信号（与 claim 并列，见 load_schedulable）。
    """

    id: UUID | None = None
    title: str = ""
    kind: str = "methodology"  # methodology | mental_model | tradeoff_map（DB CHECK 同）
    body: dict = field(default_factory=dict)
    evidence_refs: list[UUID] = field(default_factory=list)
    produced_by: UUID | None = None
    revises: UUID | None = None
    created_at: datetime | None = None


@dataclass
class Edge:
    """连接 / 反向连接（对应 schema `edge`）。"""

    id: UUID | None = None
    src: UUID = field(default_factory=uuid4)
    dst: UUID = field(default_factory=uuid4)
    kind: str = ""
    weight: float | None = None
    produced_by: UUID | None = None


@dataclass
class Context:
    """context 拓扑装配（对应 schema `context`，D1/D2）。"""

    id: UUID | None = None
    scope: str = "self_loop"
    label: str | None = None
    title: str | None = None
    produced_by: UUID | None = None
    # OCC 乐观版本号（2026-10-31 遗留②解决）
    version_seq: int = 1


@dataclass
class ReviewItem:
    """复审队列项（对应 schema `review_queue`，D5）。"""

    id: UUID | None = None
    node_id: UUID = field(default_factory=uuid4)
    action: str = "distill"  # distill | archive | abstain | classify(路由人工兜底)
    reason: str | None = None
    created_at: datetime | None = None
    resolved: bool = False


@dataclass
class SchedulableNode:
    """调度信号快照（L1/L2 规则输入；由 `Storage.load_schedulable()` 产出，存储无关）。

    所有字段都是纯数据：title/content 用于 L1 时间锚解析；captured/conn/self_loop/
    higher_dim 是「是否腐化快」的结构信号；interval_days/baseline_days/source 是现状。
    `days` 统一用 float 天作工作单元（与 schema 的 `interval` 类型解耦，便于纯函数测试）。
    """

    id: UUID | None = None
    track: str = "dynamic"
    title: str = ""
    content: str | None = None
    captured: bool = False                 # 已是某 claim/artifact 的 evidence（价值已沉淀）
    conn_count: int = 0                    # edge 连接数
    self_loop_count: int = 0               # 所属 self_loop context 数（项目躬身入局）
    higher_dim_count: int = 0              # 所属 higher_dim context 数
    interval_days: float | None = None     # 当前生效 review_interval（天）
    baseline_days: float | None = None    # 当前 baseline_interval（天）
    source: str = "auto"                   # auto / human（人工设定豁免自动化）
    archived: bool = False
    decay_score: float = 0.0               # 当前衰减分（到期判定用：≥ ROT_THRESHOLD 即到期）


@dataclass
class AttentionObservation:
    """注意力观测埋点（对应 schema `attention_observation`，D8；budget 估计唯一输入）。"""

    day: datetime = field(default_factory=datetime.utcnow)  # 仅用 date 部分
    pushed: int = 0
    completed: int = 0
    queue_remaining: int = 0
    labeled_completed: int = 0


@dataclass
class LLMCallScore:
    """一次 LLM 调用的轻量度量（对应 schema `llm_call_score`，1-5-6；Langfuse 替代）。

    成功与失败都记：失败行的 error 是接线质量的第一手观测。
    human_verdict = 蒸馏质量 rubric 的人工打分入口（复审流回填，默认 NULL）。
    """

    id: UUID | None = None
    operation: str = "distill"
    node_id: UUID | None = None
    model: str | None = None
    latency_ms: float | None = None
    parse_ok: bool = True
    attempts: int | None = None
    n_claims: int | None = None
    n_citations: int | None = None
    error: str | None = None
    human_verdict: str | None = None
    created_at: datetime | None = None


@dataclass
class MetricInputs:
    """复利度量计算的普通数据快照（存储无关）。

    由 ``Storage.load_metric_inputs()`` 按后端捞取（PG 跑 SQL、内存跑 Python），
    纯函数度量只吃本快照，无 DB/仓库依赖 → 可脱离存储单测（沿用 load_schedulable 的 seam）。
    各字段都是最小可计算单元：
      nodes            : list[(id, track, decay_score, archived)]
      edges            : list[(src, dst, kind)]
      claim_evidence   : list[list[node_id]]  每条 meta_claim 的 evidence_refs
      artifact_evidence: list[list[node_id]]  来自 combine 的 modeling_artifact 的 evidence_refs
      citations        : list[cited_claim_id]  citation 表记录的被复用 claim
    """

    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    claim_evidence: list = field(default_factory=list)
    artifact_evidence: list = field(default_factory=list)
    citations: list = field(default_factory=list)

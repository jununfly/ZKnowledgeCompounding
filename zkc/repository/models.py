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
    action: str = "distill"  # distill | archive | abstain
    reason: str | None = None
    created_at: datetime | None = None
    resolved: bool = False


@dataclass
class AttentionObservation:
    """注意力观测埋点（对应 schema `attention_observation`，D8；budget 估计唯一输入）。"""

    day: datetime = field(default_factory=datetime.utcnow)  # 仅用 date 部分
    pushed: int = 0
    completed: int = 0
    queue_remaining: int = 0
    labeled_completed: int = 0

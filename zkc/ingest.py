"""ZKC · 业务/领域服务层（P1.2 后续：业务代码一律走 repository seam）。

本模块是「业务代码从 docker-exec 直连切到 get_storage()」的落地示范与默认入口：
- 所有领域操作都通过 `get_storage()` 门面（依赖注入：调用方传入 `store`，默认取全局 seam），
  **绝不**直接碰 docker / psql / psycopg / 具体驱动。
- 唯一允许 docker-exec 的路径是 `zkc/migrate.py`（它管理 schema，不是领域数据）；
  领域代码若需要 schema，应假设它已就绪，只消费 repository。

这样未来 ingest / scheduler / transform 等业务模块都复用这套签名，
seam 可替换性（Pg ↔ 内存 fake）在业务层之上依然成立。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from .repository import Storage, get_storage
from .repository.models import Node, ReviewItem
from . import routing
from .routing import RoutingResult


def ingest_node(
    *,
    title: str,
    content: str | None = None,
    track: str = "unrouted",
    valid_from: Optional[datetime] = None,
    embedding: Optional[list[float]] = None,
    routing_confidence: Optional[float] = None,
    store: Optional[Storage] = None,
) -> Node:
    """摄入一个 node，落到 repository（当前态 + 双时态版本链由 Pg/Memory 实现负责）。

    返回保存后的 Node（含 id / created_at / tx_from）。provenance（transform）留给
    编排层（LangGraph）记录，本层只负责实体持久化。
    """
    store = store or get_storage()
    node = Node(
        title=title,
        content=content,
        track=track,
        valid_from=valid_from or datetime.now(),
        embedding=embedding,
        routing_confidence=routing_confidence,
    )
    return store.nodes.save(node)


def record_review(
    *,
    node_id: UUID,
    action: str,
    reason: str | None = None,
    store: Optional[Storage] = None,
) -> UUID:
    """入队一条复审项（distill / archive / abstain），落到 review_queue。"""
    store = store or get_storage()
    item = store.review_queue.enqueue(node_id, action, reason)
    return item.id


def record_attention_day(
    *,
    day,
    pushed: int,
    completed: int,
    queue_remaining: int,
    labeled_completed: int = 0,
    store: Optional[Storage] = None,
) -> None:
    """写一条每日注意力观测埋点（D8；budget 估计的唯一外生锚）。

    day 可为 date 或 datetime，只取日期部分。
    """
    store = store or get_storage()
    from .repository.models import AttentionObservation

    obs = AttentionObservation(
        day=day,
        pushed=pushed,
        completed=completed,
        queue_remaining=queue_remaining,
        labeled_completed=labeled_completed,
    )
    store.attention.record_observation(obs)


def list_due_for_review(
    *,
    as_of: Optional[datetime] = None,
    store: Optional[Storage] = None,
) -> list[Node]:
    """返回 decay≥0.6 且已到期的 node（调度器每日收口用）。"""
    store = store or get_storage()
    return store.nodes.list_due_for_review(as_of or datetime.now())


# 人工兜底用的复审动作：路由弃权/vague 条目需人工定轨（数据层无字符串校验，仅文档约束）。
CLASSIFY_ACTION = "classify"


def ingest_with_routing(
    *,
    title: str,
    content: str | None = None,
    text_for_routing: str | None = None,
    decision_router: routing.DecisionRouter,
    lexical_router: routing.LexicalRouter | None = None,
    llm_available: bool = True,
    valid_from: Optional[datetime] = None,
    embedding: Optional[list[float]] = None,
    store: Optional[Storage] = None,
) -> tuple[Node, RoutingResult]:
    """摄入并自动分流（P2.2 主入口）。

    - 用双信号路由引擎决定 track（见 `routing.route_text`）。
    - 提交真实轨道时：node.track 落定、routing_confidence 存 LLM 置信。
    - 弃权/vague 时：track 保持 unrouted，并向 review_queue 入队 action='classify'
      （人工兜底），由每日复审队列 UI（P4.2）消费人工定轨。
    返回 (Node, RoutingResult)，调用方可用 result 决定 UI 提示/埋点。
    """
    store = store or get_storage()
    text = text_for_routing if text_for_routing is not None else (title + (" " + content if content else ""))
    result = routing.route_text(
        text, decision_router, lexical_router, llm_available=llm_available,
    )
    node = Node(
        title=title,
        content=content,
        track=result.track,
        valid_from=valid_from or datetime.now(),
        embedding=embedding,
        routing_confidence=result.llm_conf if result.track != routing.VAGUE else None,
    )
    saved = store.nodes.save(node)
    if result.track == routing.VAGUE:
        store.review_queue.enqueue(saved.id, CLASSIFY_ACTION, reason=result.aborted)
    return saved, result


# ----------------------------------------------------------------- P2.3 联调：classify 的消费与回灌
# 人工兜底可定轨的轨道集合；vague 不是轨道——定了轨就不再是 unrouted。
RESOLVABLE_TRACKS = ("static", "dynamic")


def list_pending_classify(*, store: Optional[Storage] = None) -> list[ReviewItem]:
    """待人工定轨的 classify 条目（每日复审队列 UI / P4.2 消费）。

    只返回 action=classify 且未 resolved 的条目，按入队序（FIFO）。
    """
    store = store or get_storage()
    return [it for it in store.review_queue.list_open() if it.action == CLASSIFY_ACTION]


def resolve_classify(
    item_id: UUID,
    track: str,
    *,
    store: Optional[Storage] = None,
    lexical_router: Optional[routing.LexicalRouter] = None,
    lexical_corpus_path: Optional[str] = None,
    text: Optional[str] = None,
) -> Node:
    """人工兜底定轨（P2.3 联调闭环）。

    - 校验 track ∈ {static, dynamic}，非法即拒（人工输入同样过闸）。
    - node.track 落定（OCC 版本快照，append-only），routing_confidence 留 None（人工路径无 LLM 置信）。
    - review_queue 条目标记 resolved。
    - 可选回灌：提供 lexical_router + lexical_corpus_path 时，把 (text, track) 追加进
      词法语料并 refit —— 人工定轨样本积累 ≥3/类后 LexicalRouter 逐渐自动化
      （冷启动安全欠覆盖 → 学习闭环）。
    text 缺省用 node.title + content 重建（与 ingest_with_routing 的路由文本同式）。
    """
    if track not in RESOLVABLE_TRACKS:
        raise ValueError(f"track 必须 ∈ {RESOLVABLE_TRACKS}，收到 {track!r}")
    store = store or get_storage()

    item = next(
        (it for it in store.review_queue.list_open()
         if it.id == item_id and it.action == CLASSIFY_ACTION),
        None,
    )
    if item is None:
        raise ValueError(f"classify 条目 {item_id} 不存在或已 resolved")

    node = store.nodes.get(item.node_id)
    if node is None:
        raise ValueError(f"node {item.node_id} 不存在（数据不一致）")

    node.track = track
    node.routing_confidence = None
    saved = store.nodes.save(node)  # OCC：version_seq 校验 + 历史快照
    store.review_queue.resolve(item_id)

    if lexical_router is not None and lexical_corpus_path is not None:
        if text is None:
            text = saved.title + (" " + saved.content if saved.content else "")
        examples = routing.load_lexical_corpus(lexical_corpus_path)
        examples.append((text, track))
        routing.save_lexical_corpus(lexical_corpus_path, examples)
        lexical_router.fit(examples)
    return saved

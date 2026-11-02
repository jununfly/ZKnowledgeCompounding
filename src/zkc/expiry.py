"""ZKC · 到期条目分流路由（T5.x，生产落地 spike-08）。

把 spike-08 的「蒸馏 vs 归档 vs 弃权」纯读侧决策表提升进生产：确定性、可解释，
强制无法判定时交人审（PRD §8 宁少勿错）。与 spike-08 的差异：信号不再走裸 cur.execute，
而是吃 zkc.repository 的 ``SchedulableNode`` 快照（captured/conn/self_loop/higher_dim/
decay_score），**存储无关**——内存 fake 与 PG 同一行为。

决策表（``route_expired``）：
  decay < ROT_THRESHOLD，或 非 dynamic，或 已归档  → not routable（action=None）
  captured（已是 claim/artifact 的 evidence）       → ARCHIVE（价值已升元认知层，原始归档）
  connected/contextual（未捕获）                    → DISTILL（除非 attention_pressure ≥ 0.8 → ABSTAIN）
  orphan（无连接/上下文/未捕获）                    → ABSTAIN（永不静默丢弃）

应用层（``route_and_apply``）：
  ARCHIVE  本地立即执行（apply_archive）
  DISTILL  有可注入 distiller → 真跑蒸馏落 claim（apply_distill）；失败回落入队人审
           无 distiller（默认）→ 入 review_queue 交人审（MVP 缺省仍安全欠覆盖）
  ABSTAIN  入 review_queue 交人审
``process_expired_dynamic_nodes`` 是接入 review/decay 流水线的批量入口
（先 refresh_decay 再路由全部到期节点，distiller 透传）。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import UUID

from . import tuning
from .decay import refresh_decay
from .repository.models import Claim
from .repository.protocols import Storage


DECISION_DISTILL = "distill"
DECISION_ARCHIVE = "archive"
DECISION_ABSTAIN = "abstain"


def _as_uuid(node_id):
    return node_id if isinstance(node_id, UUID) else UUID(str(node_id))


def _row_for(store: Storage, node_id) -> Optional[object]:
    nid = _as_uuid(node_id)
    for r in store.load_schedulable():
        if r.id == nid:
            return r
    return None


def route_expired(store: Storage, node_id, attention_pressure: float = 0.0) -> dict:
    """为单个节点做到期分流决策。

    返回 ``{routable, action, reason, signals}``。不可路由（非到期/非 dynamic/已归档）时
    ``action=None``。``signals`` 回带底层结构信号，便于审计与排错。
    """
    rot = tuning.get("ROT_THRESHOLD")
    row = _row_for(store, node_id)
    if row is None:
        # 不在 load_schedulable：静态轨或已归档 → 不可路由
        return dict(routable=False, action=None,
                    reason="not an expired dynamic node (static/archived/not schedulable)",
                    signals={})
    if row.decay_score < rot:
        return dict(routable=False, action=None,
                    reason=f"decay {row.decay_score:g} < ROT {rot:g}: not yet expired",
                    signals=dict(decay_score=row.decay_score))
    signals = dict(
        decay_score=row.decay_score,
        captured=row.captured,
        conn_count=row.conn_count,
        self_loop_count=row.self_loop_count,
        higher_dim_count=row.higher_dim_count,
    )
    if row.captured:
        # 价值已升入元认知层（被 claim/artifact 引用）→ 原始记录归档，不回 distill
        return dict(routable=True, action=DECISION_ARCHIVE,
                    reason="value already lifted to meta layer (claim/artifact evidence) -> archive raw",
                    signals=signals)
    contextual = (row.conn_count >= 1 or row.self_loop_count >= 1
                  or row.higher_dim_count >= 1)
    if contextual:
        if attention_pressure >= tuning.get("PRESSURE_DEFER"):
            return dict(routable=True, action=DECISION_ABSTAIN,
                        reason="would distill but attention budget full -> defer to human",
                        signals=signals)
        return dict(routable=True, action=DECISION_DISTILL,
                    reason="connected/contextual but not captured -> lift insight",
                    signals=signals)
    # 孤儿：绝不静默丢弃，交人判定（保留/蒸馏/归档）
    return dict(routable=True, action=DECISION_ABSTAIN,
                reason="orphan (no connection/context) -> human decides, never silently drop",
                signals=signals)


def apply_archive(store: Storage, node_id, now: Optional[datetime] = None) -> None:
    """单程票终局：标记节点已归档（archived_at=now）。"""
    store.nodes.archive(node_id, now or datetime.now(timezone.utc))


def enqueue_review(store: Storage, node_id, action: str, reason: str):
    """把 DISTILL/ABSTAIN 结论落入人审网关（review_queue）。"""
    return store.review_queue.enqueue(node_id, action, reason)


def _already_open(store: Storage, node_id, action: str) -> bool:
    nid = _as_uuid(node_id)
    return any(
        (it.node_id == nid and it.action == action and not it.resolved)
        for it in store.review_queue.list_open()
    )


def _resolve_open(store: Storage, node_id, action: str) -> int:
    """resolve 该节点全部已开的同 action 队列项（蒸馏成功后清理旧人审项）。"""
    nid = _as_uuid(node_id)
    n = 0
    for it in store.review_queue.list_open():
        if it.node_id == nid and it.action == action:
            store.review_queue.resolve(it.id)
            n += 1
    return n


def apply_distill(
    store: Storage,
    node_id,
    distiller: Callable,
    now: Optional[datetime] = None,
    model: Optional[str] = None,
) -> dict:
    """执行 distill 决策的「真蒸馏」分支（残余 B：不再只入队）。

    distiller: 可注入 callable ``(store, node_id) -> DistillationResult``——真实环境用
    ``distill.distill_node`` + LLM（zkc.llm.make_distill_llm），测试用 fake。语义流程：
      1. 跑蒸馏并强制 ZKC 语义校验（每条 claim ≥1 来源引用，见 distill.validate_result）；
      2. 每条 MetaClaim 落一条 Claim（statement=text, level='insight',
         evidence_refs=citations 的来源节点）——节点由此进入「已捕获」；
      3. mark_reviewed 复位衰减钟 → 节点进入 captured 28d 观察期（单程票 pacing，
         下次到期由 ARCHIVE 分支收口）；
      4. resolve 该节点已开的 distill 人审项（先前无 distiller 轮次入队的）。
    任一步失败（DistillationError / LLM 异常）→ 回落 enqueue 人审 + applied=False，
    绝不静默丢弃（PRD §8 宁少勿错）。

    度量（1-5-6）：每次调用落一行 llm_call_score（成功与失败都记）——latency_ms /
    parse_ok / attempts（来自 result.attempts）/ n_claims / n_citations / error；
    ``model`` 由调用方从 ``getattr(llm, "model_name", None)`` 透传（distiller 是
    不透明 callable，模型名不在本层可见）。rubric 人工打分经
    ``store.scores.set_human_verdict`` 回填（复审流消费口）。

    返回 ``{applied, action, claim_ids, reason, enqueued}``。
    """
    nid = _as_uuid(node_id)
    now = now or datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        from .distill import DistillationError, validate_result
        from .repository.models import LLMCallScore

        result = distiller(store, nid)
        result = validate_result(result)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        n_cit = sum(len(mc.citations) for mc in result.claims)
        store.scores.record(LLMCallScore(
            operation=DECISION_DISTILL, node_id=nid, model=model,
            latency_ms=latency_ms, parse_ok=True, attempts=result.attempts,
            n_claims=len(result.claims), n_citations=n_cit,
        ))
        claim_ids = []
        for mc in result.claims:
            c = store.claims.save(Claim(
                statement=mc.text,
                level="insight",
                evidence_refs=[cit.source_node_id for cit in mc.citations],
            ))
            claim_ids.append(c.id)
        store.nodes.mark_reviewed(nid, now)
        _resolve_open(store, nid, DECISION_DISTILL)
        return dict(
            applied=True, action=DECISION_DISTILL, claim_ids=claim_ids,
            reason=f"distilled {len(claim_ids)} claim(s); node re-enters captured pacing",
            enqueued=False,
        )
    except Exception as e:  # noqa: BLE001 —— 失败必须回落人审，绝不静默丢
        from .repository.models import LLMCallScore

        latency_ms = (time.perf_counter() - t0) * 1000.0
        try:
            store.scores.record(LLMCallScore(
                operation=DECISION_DISTILL, node_id=nid, model=model,
                latency_ms=latency_ms, parse_ok=False, error=str(e)[:500],
            ))
        except Exception:  # noqa: BLE001 —— 度量失败绝不掩盖主失败路径
            pass
        enqueue_review(store, nid, DECISION_DISTILL, f"auto-distill failed: {e}")
        return dict(
            applied=False, action=DECISION_DISTILL, claim_ids=[],
            reason=f"distillation failed -> human queue: {e}", enqueued=True,
        )


def route_and_apply(
    store: Storage,
    node_id,
    attention_pressure: float = 0.0,
    distiller: Optional[Callable] = None,
) -> dict:
    """路由一个节点并应用本地可落地部分。

    ARCHIVE 立即归档；DISTILL 有 distiller 则真蒸馏（apply_distill），否则入队（去重）；
    ABSTAIN 始终入队（人审网关）。
    """
    decision = route_expired(store, node_id, attention_pressure)
    if not decision["routable"]:
        return decision
    action = decision["action"]
    if action == DECISION_ARCHIVE:
        apply_archive(store, node_id)
    elif action == DECISION_DISTILL and distiller is not None:
        res = apply_distill(store, node_id, distiller)
        decision = dict(decision, applied=res["applied"], claim_ids=res["claim_ids"])
    elif action in (DECISION_DISTILL, DECISION_ABSTAIN):
        if not _already_open(store, node_id, action):
            enqueue_review(store, node_id, action, decision["reason"])
    return decision


def process_expired_dynamic_nodes(
    store: Storage,
    attention_pressure: float = 0.0,
    now: Optional[datetime] = None,
    distiller: Optional[Callable] = None,
) -> dict:
    """批量入口（接入 review/decay 流水线）：先 refresh_decay，再路由全部到期动态节点。

    返回 ``{processed, archived, distilled, abstained, decisions}``；ARCHIVE 立即落库，
    DISTILL 有 distiller 则真蒸馏、否则入 review_queue，ABSTAIN 入队。
    未到期节点被跳过（不污染队列）。
    """
    now = now or datetime.now(timezone.utc)
    refresh_decay(store.nodes, now)
    counts = {DECISION_ARCHIVE: 0, DECISION_DISTILL: 0, DECISION_ABSTAIN: 0}
    decisions = []
    for row in store.load_schedulable():
        if row.decay_score < tuning.get("ROT_THRESHOLD"):
            continue
        d = route_and_apply(store, row.id, attention_pressure, distiller=distiller)
        if not d["routable"]:
            continue
        decisions.append(d)
        counts[d["action"]] += 1
    return dict(
        processed=len(decisions),
        archived=counts[DECISION_ARCHIVE],
        distilled=counts[DECISION_DISTILL],
        abstained=counts[DECISION_ABSTAIN],
        decisions=decisions,
    )

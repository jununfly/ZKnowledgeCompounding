"""ZKC · 每日复审队列的**纯领域层**（domain，无 HTTP / 无 fastapi 依赖）。

本模块是从 `zkc.web.review` 物理迁出的领域逻辑（ADR：web.review 三函数定性为 domain）。
迁出动机（finding 26）：原先 `cli.py` / `mcp` 经 `zkc.web.review` 取这些函数，会触发
`zkc.web.__init__` 的 eager `from zkc.web.app import ...` → `from fastapi import ...`，
使「无 HTTP 依赖的纯编排函数」被 web 栈拖住、无法脱离 fastapi 录制/运行。

承载两个自指闭环的唯一外生锚（架构 §6.5.1 / PRD 目标 5）：

  锚 A · 复审结果标注（still_valid / changed / stale[cover|purge] / browse）
       → v2（ADR-0011/0012）：走「终局动作」替代 AIMD 乘因子——
         changed / stale+cover 写节点双时态新版本 + 重置 L1 基线；stale+purge 走 archive；
         still_valid / browse 仅时钟复位。AIMD 自适应环路的人工输入由此归零（外生锚 A）。
         内容载荷（--content）与 stale 分支（--stale-branch）只能由 Human 逐条给出。

  锚 B · 每日收口埋点（pushed / completed / queue_remaining / labeled_completed）
       → 驱动 budget 估计（zkc.scheduling.estimate_budget / update_budget）
       → 容量只能观测，budget 估计器在 confidence='none' 时永远静止

SSR 页面与 FastAPI 路由装配（`register_review_routes` / `REVIEW_HTML`）留在 `zkc.web.review`，
它反过来从这里导入领域函数。`zkc.web.review` 仍 re-export 本模块的公开名以兼容既有调用方/测试。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from zkc import scheduling as S
from zkc import expiry as EX
from zkc import faithfulness as F
from zkc.context import ContextAssembler, HigherDimProposal
from zkc.decay import refresh_decay
from zkc.ingest import list_pending_classify, resolve_classify
from zkc.repository.models import AttentionObservation
from zkc.repository.protocols import Storage

# v2（ADR-0011/0012）：复审标注四类终局动作的审计 reason，集中常量、禁止字符串散落（规格 F1）。
# 注意：v2 不再把 verdict 映射成 AIMD 因子（changed/stale 不再走 too_late×0.7）；
# 旧 OUTCOME_VERDICT（still_valid:on_time / changed:too_late / stale:too_late）已删除。
# 四类 reason 互异，且与 D2（expiry archive reason「archived」）无关、不混同（S1-c）。
REVIEW_REASON = {
    "still_valid": "still_valid",            # 仅时钟复位，不调 AIMD
    "changed": "changed",                    # changed 写节点双时态新版本
    "stale_overwrite": "stale_overwrite",    # stale 覆盖写节点双时态新版本
    "stale_purged": "stale_purged",          # stale 清除走 archive 软归档
    "browsed_without_label": "browsed_without_label",  # 仅浏览不标注
}


# ---------------------------------------------------------------- 序列化助手

def _node_to_dict(n) -> dict:
    iv = n.review_interval
    return dict(
        id=str(n.id),
        title=n.title,
        track=n.track,
        decay_score=round(n.decay_score, 3) if n.decay_score is not None else None,
        review_interval_days=(iv.total_seconds() / 86400.0) if iv is not None else None,
        interval_source=n.interval_source,
        last_reviewed_at=(n.last_reviewed_at.isoformat() if n.last_reviewed_at else None),
    )


def _obs_to_dict(o: Optional[AttentionObservation]) -> Optional[dict]:
    if o is None:
        return None
    return dict(day=o.day.isoformat() if isinstance(o.day, datetime) else o.day.isoformat(),
                pushed=o.pushed, completed=o.completed,
                queue_remaining=o.queue_remaining, labeled_completed=o.labeled_completed)


# ---------------------------------------------------------------- 纯函数编排层

def review_queue_view(store: Storage, now: Optional[datetime] = None) -> dict:
    """取当前复审队列 + 两个闭环的状态快照（供页面渲染与 API 返回）。"""
    now = now or datetime.now(timezone.utc)
    refresh_decay(store.nodes, now)                      # 应用层触发器：先重算衰减
    due = store.nodes.list_due_for_review(now)
    today = now.date()
    gate = S.labeling_rate_from(store.attention.list_recent(30))
    budget = S.estimate_budget(store)
    return dict(
        as_of=now.isoformat(),
        items=[_node_to_dict(n) for n in due],
        due_count=len(due),
        today_observation=_obs_to_dict(store.attention.get(today)),
        gate=gate,
        budget=budget,
    )


def _iv_days(node) -> Optional[float]:
    return (node.review_interval.total_seconds() / 86400.0
            if node.review_interval is not None else None)


def _write_content_version(store: Storage, node_id, content: str) -> None:
    """changed / stale 覆盖：把内容载荷写节点双时态新版本（nodes.save 触发 OCC 版本链）。

    不触发 distill（≠ 复利变换 claim，规格 S1-b / DI-9）。
    """
    node = store.nodes.get(node_id)
    if node is None:
        raise ValueError(f"node {node_id} not found")
    node.content = content
    store.nodes.save(node)   # OCC：node 持有当前 version_seq，save 写新版本 + 版本链 +1


def _reset_to_l1_baseline(store: Storage, node_id, now: datetime) -> None:
    """changed / stale 覆盖：review_interval 重置为 L1 基线（baseline_interval），不继承旧收缩。

    规格 §4 表 A：重置 L1 基线（同构）。若 baseline_interval 缺失，按当前结构信号重算兜底。
    """
    node = store.nodes.get(node_id)
    if node is None:
        return
    baseline = node.baseline_interval
    if baseline is None:
        row = next((r for r in store.load_schedulable() if r.id == node_id), None)
        if row is not None:
            sug = S.baseline_for_node(row)
            if sug["days"] is not None:
                baseline = timedelta(days=sug["days"])
    if baseline is not None:
        store.nodes.set_baseline_interval(
            node_id, baseline, "auto",
            "verdict v2: reset review_interval to L1 baseline")


def decide_review(
    store: Storage,
    node_id,
    outcome: str,
    now: Optional[datetime] = None,
    content: Optional[str] = None,
    stale_branch: Optional[str] = None,
) -> dict:
    """处理一次复审标注（锚 A + 锚 B 累加，v2 语义）。

    verdict 语义矩阵（ADR-0011 §语义矩阵 v2 / ADR-0012 §4 表 A）：
      still_valid : 仅时钟复位（维持 interval），不调 AIMD
      changed     : 写内容新版本 + review_interval 重置 L1 基线（不退出调度回路）；内容载荷必填
      stale+cover : 写内容新版本 + 重置 L1 基线（不退出）；分支与内容载荷均必填
      stale+purge: archive 软归档（退出调度回路）；仅分支必填
      browse      : 时钟复位 + completed++（不标注，不调 L3）

    外生锚 A（ADR-0011）：verdict 不再调 S.adapt_interval，AIMD 自适应环路人工输入归零。

    content / stale_branch 是 Human-only 门禁参数：缺失即 ValueError（不自动填 / 不默认 purge）。
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(node_id, str):
        node_id = UUID(node_id)
    node = store.nodes.get(node_id)
    if node is None:
        raise ValueError(f"node {node_id} not found")

    # ---- 内容载荷 / stale 分支门禁（Human-only，缺失即拒，不自动填/不默认 purge）----
    if outcome == "changed":
        if not content:
            raise ValueError(
                "changed 需要内容载荷（--content），且只能由人工逐条给出；缺失即拒收")
    elif outcome == "stale":
        if stale_branch not in ("cover", "purge"):
            raise ValueError(
                "stale 需要 --stale-branch cover|purge，且只能由人工逐条给出；"
                "缺失或非法即拒收，绝不默认 purge")
        if stale_branch == "cover" and not content:
            raise ValueError(
                "stale cover 需要内容载荷（--content）；缺失即拒收")
    elif outcome in ("still_valid", "browse"):
        # 规格 C4：非内容类 verdict 不应携带载荷；携带即拒（一致处理，避免静默丢信息）
        if content is not None or stale_branch is not None:
            raise ValueError(
                f"{outcome} 不接受 --content / --stale-branch；请仅用于 changed / stale")

    result = dict(node_id=str(node_id), outcome=outcome)

    if outcome == "browse":
        # 仅浏览未标注：复位时钟 + completed++（不标注），不触发 L3
        store.nodes.mark_reviewed(node_id, now)
        result.update(verdict=None, applied=False, new_interval_days=None,
                      reason=REVIEW_REASON["browsed_without_label"])
    elif outcome == "still_valid":
        # 仅时钟复位；不再走 AIMD（规格 A3 人工输入归零）
        store.nodes.mark_reviewed(node_id, now)
        result.update(verdict=REVIEW_REASON["still_valid"], applied=False,
                      new_interval_days=_iv_days(node),
                      reason=REVIEW_REASON["still_valid"])
    elif outcome == "changed":
        _write_content_version(store, node_id, content)
        _reset_to_l1_baseline(store, node_id, now)
        store.nodes.mark_reviewed(node_id, now)
        result.update(verdict=REVIEW_REASON["changed"], applied=True,
                      new_interval_days=_iv_days(store.nodes.get(node_id)),
                      reason=REVIEW_REASON["changed"])
    elif outcome == "stale":
        if stale_branch == "cover":
            _write_content_version(store, node_id, content)
            _reset_to_l1_baseline(store, node_id, now)
            store.nodes.mark_reviewed(node_id, now)
            result.update(verdict=REVIEW_REASON["stale_overwrite"], applied=True,
                          new_interval_days=_iv_days(store.nodes.get(node_id)),
                          reason=REVIEW_REASON["stale_overwrite"])
        else:  # purge
            store.nodes.archive(node_id, now)
            result.update(verdict=REVIEW_REASON["stale_purged"], applied=True,
                          new_interval_days=None,
                          reason=REVIEW_REASON["stale_purged"])
    else:
        raise ValueError(f"unknown outcome: {outcome}")

    # 累加今日观测：completed++ 与 labeled_completed++（仅标注动作）
    today = now.date()
    existing = store.attention.get(today)
    labeled = outcome != "browse"
    obs = AttentionObservation(
        day=today,
        pushed=existing.pushed if existing else 0,
        completed=(existing.completed if existing else 0) + 1,
        queue_remaining=existing.queue_remaining if existing else 0,
        labeled_completed=(existing.labeled_completed if existing else 0) + (1 if labeled else 0),
    )
    store.attention.record_observation(obs)

    result["gate"] = S.labeling_rate_from(store.attention.list_recent(30))
    result["today_observation"] = _obs_to_dict(store.attention.get(today))
    return result


def classify_queue_view(store: Storage) -> dict:
    """捕获弃权的人工定轨队列视图（P2.3 消费端上 UI，2026-11-02 补齐）。

    路由引擎弃权（vague/低置信/离线不可判）的条目在此等待人工定轨；
    resolve 后节点落轨 + review_queue 条目标记 resolved。
    """
    items = []
    for it in list_pending_classify(store=store):
        node = store.nodes.get(it.node_id)
        # preview 服务端截断：全文可能上百 KB，API 不该整包下发
        preview = (node.content[:120] if node and node.content else None) or None
        items.append(dict(
            id=str(it.id),
            title=node.title if node else "(节点缺失)",
            preview=preview,
            created_at=(it.created_at.isoformat() if it.created_at else None),
        ))
    return dict(items=items, count=len(items))


def classify_resolve_action(store: Storage, item_id: str, track: str) -> dict:
    """人工定轨动作：track ∈ {static, dynamic}，非法即拒（resolve_classify 内校验）。"""
    node = resolve_classify(UUID(item_id), track, store=store)
    return dict(ok=True, node_id=str(node.id), track=track)


def record_daily_observation(
    store: Storage,
    pushed: int,
    queue_remaining: int,
    now: Optional[datetime] = None,
) -> dict:
    """每日收口（锚 B）：写入 pushed / queue_remaining，保留当日已累加的 completed/labeled。"""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    existing = store.attention.get(today)
    obs = AttentionObservation(
        day=today,
        pushed=pushed,
        completed=existing.completed if existing else 0,
        queue_remaining=queue_remaining,
        labeled_completed=existing.labeled_completed if existing else 0,
    )
    store.attention.record_observation(obs)
    return _obs_to_dict(store.attention.get(today))


def record_daily_observation_auto(store: Storage, now: Optional[datetime] = None) -> dict:
    """每日收口（锚 B）的真值自动版：服务端计算 pushed / queue_remaining，避免手工填表造假。

    - pushed        = 今日（本地零点起）创建的节点数（ingest 吞吐真值源）
    - queue_remaining = 当前仍未复审的到期条目数（list_due_for_review(now) 长度）
    二者均为系统可观测真值；pushed 当前不被任何 E1 判据消费（纯遥测），queue_remaining
    是「饱和日」定义的唯一输入（estimate_budget_from / calibration_readiness 都靠它）。
    保留当日已累加的 completed/labeled，只覆盖 pushed/queue_remaining。
    """
    now = now or datetime.now(timezone.utc)
    start_of_today = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
    pushed = store.nodes.count_nodes_created_since(start_of_today)
    queue_remaining = len(store.nodes.list_due_for_review(now))
    return record_daily_observation(store, pushed, queue_remaining, now=now)


# ---------------------------------------------------------------- 到期分流流水线（残余 1 收口）

def process_expired_view(store: Storage, attention_pressure: float = 0.0,
                         now: Optional[datetime] = None) -> dict:
    """把 spike-08 到期分流路由接入 review/decay 流水线。

    纯函数层（无 HTTP 依赖）：refresh_decay 后路由全部到期动态节点——已捕获节点立即归档
    （单程票终局），有连接/上下文未捕获节点入队蒸馏，孤儿入队交人审。返回路由计数。

    既可被每日 cron 调用，也可经 web 层 POST 端点手动触发。
    """
    return EX.process_expired_dynamic_nodes(store, attention_pressure=attention_pressure, now=now)


# ---------------------------------------------------------------- 更高维聚合提议（P1 收尾·接入复审流）

def _proposal_to_dict(p: HigherDimProposal) -> dict:
    return dict(
        seed_node_id=str(p.seed_node_id),
        neighbor_ids=[str(n) for n in p.neighbor_ids],
        similarities=[round(s, 4) for s in p.similarities],
        suggested_title=p.suggested_title,
        would_create=p.would_create,
        reason=p.reason,
        existing_context_id=(str(p.existing_context_id)
                             if p.existing_context_id is not None else None),
        calibrated=p.calibrated,
    )


def higher_dim_proposals_view(store: Storage, now: Optional[datetime] = None,
                              k: int = 5, llm=None) -> dict:
    """把 propose_higher_dim_daily 接入复审流：种子 = 当日待复审节点（已在该人类注意力里，
    与复审同会话，自然攒出校准埋点批）。返回可序列化提议 + 预算状态 + 校准就绪度。

    纯函数层（无 HTTP 依赖），可脱离 web 栈单测（内存 fake / PG 同构）。
    """
    now = now or datetime.now(timezone.utc)
    refresh_decay(store.nodes, now)
    day = now.date()
    excluded = store.attention.dismissed_seed_ids(day)
    # 候选 = 当日待复审节点，排除已被人工忽略的种子（dismiss 真生效）
    seeds = [n.id for n in store.nodes.list_due_for_review(now)
             if n.id not in excluded]
    asm = ContextAssembler(store)
    proposals, budget_status = asm.propose_higher_dim_daily(
        seeds, day, k=k, llm=llm, excluded=excluded)
    return dict(
        as_of=now.isoformat(),
        day=str(day),
        seeds_total=len(seeds),
        proposals=[_proposal_to_dict(p) for p in proposals],
        actionable=[_proposal_to_dict(p) for p in proposals if p.would_create],
        budget_status=budget_status,
        calibration=S.calibration_readiness(store),
    )


def approve_higher_dim(store: Storage, seed_node_id, k: int = 5,
                       llm=None, now: Optional[datetime] = None) -> dict:
    """人工确认：从种子重新派生提议（重过门槛/校准/去重），通过则落库为 higher_dim context。

    与「系统提议」同源：人类确认创建也消耗当日 higher_dim 注意力预算，故落 proposal_log。
    纯函数层，可脱离 web 栈单测。
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(seed_node_id, str):
        seed_node_id = UUID(seed_node_id)
    asm = ContextAssembler(store)
    prop = asm.propose_higher_dim(seed_node_id, k=k, llm=llm)
    if not prop.would_create:
        return dict(seed_node_id=str(seed_node_id), created=False,
                    reason=prop.reason, context_id=None)
    cid, tid = asm.create_higher_dim(prop)
    store.attention.record_proposal(now.date(), "higher_dim", seed_node_id)
    return dict(seed_node_id=str(seed_node_id), created=True,
                context_id=str(cid), transform_id=str(tid),
                suggested_title=prop.suggested_title, reason="人工确认创建")


def dismiss_higher_dim(store: Storage, seed_node_id,
                       now: Optional[datetime] = None) -> dict:
    """人工忽略：落 proposal_log(kind='higher_dim_dismissed', seed_id)，当日 sweep 跳过该种子。

    纯函数层，可脱离 web 栈单测。
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(seed_node_id, str):
        seed_node_id = UUID(seed_node_id)
    store.attention.record_proposal(now.date(), "higher_dim_dismissed", seed_node_id)
    return dict(seed_node_id=str(seed_node_id), dismissed=True,
                day=str(now.date()))


# ---------------------------------------------------------------- 忠实度人审卡片（忠实度闸门）

def faithfulness_queue_view(store: Storage, now: Optional[datetime] = None) -> dict:
    """忠实度人审查看视图：F_cap 日队列 + 校准语料概览（纯函数，无 HTTP 依赖）。

    R11 独立预算：本视图与 adjudicate_claim 均不写 attention_observation——
    蒸馏人审不占复审容量口径，R10 的标注率语义不被 claim 人审污染。
    校准语料在 judge 上线前恒空（human_only 的 judge_raw 无 atomic_facts，
    无对照价值），属预期而非缺陷。
    """
    now = now or datetime.now(timezone.utc)
    corpus = F.calibration_corpus(store)
    correct = sum(1 for c in corpus if c["judge_correct"])
    return dict(
        as_of=now.isoformat(),
        queue=F.daily_faithfulness_queue(store),
        calibration=dict(
            size=len(corpus),
            judge_correct=correct,
            judge_correct_rate=(correct / len(corpus)) if corpus else None,
        ),
    )


def adjudicate_claim(
    store: Storage,
    claim_id,
    verdict: str,
    now: Optional[datetime] = None,
) -> dict:
    """审查卡片操作入口：包装 faithfulness.adjudicate（confirm/reject/edit）。

    返回裁决结果 + 刷新后的队列计数。同样不写 attention_observation（R11）。
    """
    res = F.adjudicate(store, claim_id, verdict, now=now)
    res["queue"] = F.daily_faithfulness_queue(store)
    return res

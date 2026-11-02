"""ZKC · 资源感知调度（P4.1，生产落地 spike-09）。

三层规则（详见架构 §6.5 / spike-09 README）：

  L1 基线（个体）  ：这条信息自身暗示的腐化速率 → ``baseline_interval``
  L2 预算归一（全局）：个体基线压进注意力硬预算 → 生效 ``review_interval``
  L3 反馈（闭环）   ：先验不可靠 → 复审结果标注 → AIMD 修正

另含切片 B 的 ``budget_per_day`` 删失感知估计与 L3 标注率闸门（P4.4）。

铁律（P1.4）：所有阈值走 ``zkc.tuning``（禁止裸数字）。本模块纯函数层（``_pure``
后缀/无副作用函数）可在无 DB 环境单测；编排层（``assign_baselines`` /
``fit_budget`` / ``adapt_interval`` / ``estimate_budget`` / ``update_budget``）依赖
``Storage`` 门面，对 PG 与内存 fake 同构（seam 可替换）。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from . import tuning
from .repository.models import AttentionObservation, SchedulableNode
from .repository.protocols import Storage

# ---------------------------------------------------------------- 常量（全部走 tuning）

def _t(name: str):
    return tuning.get(name)


# ---------------------------------------------------------------- L1 时间锚解析

# 显式时间锚是腐化速率最强证据。中英文，保守取最早命中的 horizon。
_HORIZON_RULES = [
    (re.compile(r"今天|今日|今夜|tonight|today"), 1.0),
    (re.compile(r"明天|明日|明早|tomorrow"), 1.0),
    (re.compile(r"后天"), 2.0),
    (re.compile(r"本周|这周|这星期|this week"), 7.0),
    (re.compile(r"下周|下星期|next week"), 7.0),
    (re.compile(r"(\d+)\s*天(内|后|以内|之后)?|in\s+(\d+)\s+days?"), "days"),
    (re.compile(r"(\d+)\s*周(内|后)?|in\s+(\d+)\s+weeks?"), "weeks"),
    (re.compile(r"(\d+)\s*个?月(内|后)?|in\s+(\d+)\s+months?"), "months"),
    (re.compile(r"本月|这个月|this month"), 30.0),
    (re.compile(r"下个?月|next month"), 30.0),
    (re.compile(r"本季度|这季度|this quarter|Q[1-4]"), 90.0),
    (re.compile(r"月底|月末|end of month"), 14.0),
    (re.compile(r"截止|deadline|ddl|DDL|due"), 7.0),
]


def _rule_days(pattern: re.Pattern, value: object, text: str) -> Optional[float]:
    m = pattern.search(text)
    if not m:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = [g for g in m.groups() if g and g.isdigit()]
    if not digits:
        return None
    n = float(digits[0])
    return n if value == "days" else n * 7.0 if value == "weeks" else n * 30.0


def extract_horizon_days(text: Optional[str]) -> Optional[float]:
    """文本中最短显式时间锚对应的天；无则返回 None。

    保守：多条锚取最早（复审太早只浪费一点注意力，太晚则已腐化，PRD §8「宁少勿错」）。
    """
    if not text:
        return None
    found = [_rule_days(p, v, text) for p, v in _HORIZON_RULES]
    found = [d for d in found if d]
    return min(found) if found else None


def clamp_days(days: float) -> float:
    return max(_t("MIN_INTERVAL_DAYS"), min(_t("MAX_INTERVAL_DAYS"), float(days)))


# ---------------------------------------------------------------- L1 基线决策（纯）

def baseline_for_signals(
    track: str,
    archived: bool,
    title: str,
    content: Optional[str],
    captured: bool,
    self_loop_count: int,
    higher_dim_count: int,
    conn_count: int,
) -> dict:
    """给定结构信号，返回 {days, reason, tier}。静态轨/已归档返回 days=None。"""
    if track != "dynamic":
        return dict(days=None, reason="static track does not decay", tier="n/a")
    if archived:
        return dict(days=None, reason="already archived", tier="n/a")

    text = f"{title or ''} {content or ''}"
    horizon = extract_horizon_days(text)
    if horizon is not None:
        return dict(
            days=clamp_days(horizon),
            reason=f"explicit temporal anchor -> {horizon:g}d horizon",
            tier="horizon",
        )
    # 边界 2（ADR-0002）：self_loop(3d) 压过已捕获(28d)——项目躬身入局的原件仍在变。
    # 原 spike 09 的 L1 表把「已捕获 28d」排在 self_loop 3d 之前，与 L2 优先级表顺序相反，
    # 此处修正为 self_loop 优先。
    if self_loop_count >= 1:
        return dict(days=_t("BASELINE_SELF_LOOP_DAYS"),
                    reason="self-loop context (active project) -> fastest rot",
                    tier="self_loop")
    if captured:
        return dict(days=_t("BASELINE_CAPTURED_DAYS"),
                    reason="value lifted to meta layer -> raw needs less attention",
                    tier="captured")
    if higher_dim_count >= 1 or conn_count >= 1:
        return dict(days=_t("BASELINE_CONNECTED_DAYS"),
                    reason="connected / shared higher-dim context -> medium rot",
                    tier="connected")
    return dict(days=_t("BASELINE_ORPHAN_DAYS"),
                reason="orphan dynamic item -> default cadence", tier="orphan")


def baseline_for_node(row: SchedulableNode) -> dict:
    return baseline_for_signals(
        row.track, row.archived, row.title, row.content,
        row.captured, row.self_loop_count, row.higher_dim_count, row.conn_count,
    )


# ---------------------------------------------------------------- L2 预算归一（纯）

def priority_of(row: SchedulableNode) -> int:
    """越高越该保住节奏（预算压力下最后延后）。"""
    if extract_horizon_days(f"{row.title} {row.content}") is not None:
        return 3                      # 显式时间锚：过期就是真过期
    if row.self_loop_count >= 1:
        return 2                      # 项目躬身入局
    if row.higher_dim_count >= 1 or row.conn_count >= 1:
        return 1                      # 有复用迹象 / 共享更高维 context
    return 0                          # 孤儿或价值已沉淀


def effective_days(row: SchedulableNode) -> float:
    return row.interval_days if row.interval_days else (row.baseline_days or _t("BASELINE_ORPHAN_DAYS"))


def daily_demand(rows: list[SchedulableNode]) -> float:
    """每日注意力需求：每条需每 SURFACE × I 天复审一次（均匀时退化为 n/(0.6×I)）。"""
    surface = _t("SURFACE_THRESHOLD")
    return sum(1.0 / (surface * effective_days(r)) for r in rows)


def fit_budget_rows(
    rows: list[SchedulableNode],
    budget_per_day: Optional[float],
    *,
    expand: Optional[float] = None,
) -> dict:
    """纯函数版 L2：在需求超预算时按优先级延后低优先条目，返回 {degraded, demand_after, ...}。

    诚实降级契约：预算 None（warm-up）→ 不归一（confidence 不足时归一会 fabrication 天花板）；
    人工设定（source='human'）永不改；延后到 MAX 仍超 → infeasible + max_dynamic_items。
    """
    expand = expand if expand is not None else 2.0
    surface = _t("SURFACE_THRESHOLD")
    max_iv = _t("MAX_INTERVAL_DAYS")
    demand = daily_demand(rows)
    report = dict(
        budget=budget_per_day,
        demand_before=round(demand, 6),
        demand_after=round(demand, 6),
        degraded=[],
        infeasible=False,
        max_dynamic_items=(int(budget_per_day * surface * max_iv)
                           if budget_per_day is not None else None),
        applied=False,
    )
    if budget_per_day is None:
        report["note"] = "no budget estimate yet (warm-up): L2 stays passive"
        return report
    if demand <= budget_per_day:
        return report

    # 延后最低优先级先；同优先级内短 interval 先（把 3 天砍半收益远大于 28 天）
    order = sorted(rows, key=lambda r: (priority_of(r), effective_days(r)))
    for row in order:
        if demand <= budget_per_day:
            break
        if row.source == "human":
            continue
        old = effective_days(row)
        new = clamp_days(old * expand)
        if new <= old:              # 已在 MAX，无空间
            continue
        demand += 1.0 / (surface * new) - 1.0 / (surface * old)
        report["degraded"].append(dict(
            id=(str(row.id) if row.id is not None else None),
            old_days=old, new_days=new, priority=priority_of(row),
        ))

    report["demand_after"] = round(demand, 6)
    report["applied"] = bool(report["degraded"])
    report["infeasible"] = demand > budget_per_day
    return report


# ---------------------------------------------------------------- L3 反馈（纯）

def classify_review(decay_at_review: float) -> str:
    if decay_at_review < _t("EARLY_THRESHOLD"):
        return "too_early"
    if decay_at_review >= _t("ROT_THRESHOLD"):
        return "too_late"
    return "on_time"


def _aimd_factor(verdict: str) -> float:
    return {"too_early": _t("AIMD_UP"), "on_time": 1.0, "too_late": _t("AIMD_DOWN")}[verdict]


def adapt_interval_math(old_days: float, verdict: str, *, human: bool = False) -> dict:
    """纯 AIMD 计算（不落库）。human=True 时豁免（返回 unchanged）。"""
    if human:
        return dict(old_days=old_days, new_days=old_days, verdict=verdict,
                    applied=False, reason="human override preserved")
    factor = _aimd_factor(verdict)
    new = clamp_days(old_days * factor)
    return dict(old_days=old_days, new_days=new, verdict=verdict,
                applied=abs(new - old_days) > 1e-9,
                reason=f"{verdict}: x{factor} correction")


# ---------------------------------------------------------------- 标注率闸门（纯，P4.4）

def labeling_rate_from(
    observations: list[AttentionObservation],
    *,
    window_days: Optional[int] = None,
    min_samples: Optional[int] = None,
    min_rate: Optional[float] = None,
) -> dict:
    """滚动窗口内 labeled_completed / completed。样本不足不判（闸门放行），不冻死 warm-up。"""
    window_days = window_days or _t("LABEL_WINDOW_DAYS")
    min_samples = min_samples or _t("LABEL_MIN_SAMPLES")
    min_rate = min_rate or _t("LABEL_RATE_MIN")
    window = _window(observations, window_days)
    completed = sum(o.completed for o in window)
    labeled = sum(o.labeled_completed for o in window)
    if completed < min_samples:
        return dict(rate=None, completed=completed, labeled=labeled, threshold=min_rate,
                    gate="open",
                    reason=f"only {completed} completed in last {window_days}d (< {min_samples}) "
                           f"-> insufficient evidence, gate open")
    rate = labeled / completed
    ok = rate >= min_rate
    return dict(rate=round(rate, 3), completed=completed, labeled=labeled,
                threshold=min_rate, gate="open" if ok else "closed",
                reason=(f"labeling rate {rate:.0%} over {completed} completed "
                        f"{'meets' if ok else 'below'} {min_rate:.0%} -> "
                        f"L3 {'runs' if ok else 'halted'}"))


def _window(observations: list[AttentionObservation], window_days: int) -> list[AttentionObservation]:
    if not observations:
        return []
    # 锚定最新一天（重放/回填历史时不能锚 today，否则返回空）
    latest = max((o.day for o in observations), default=None)
    if isinstance(latest, datetime):
        cut = latest.date() - timedelta(days=window_days - 1)
    else:
        cut = latest - timedelta(days=window_days - 1)
    return [o for o in observations if _as_date(o.day) >= cut]


def _as_date(d):
    return d.date() if isinstance(d, datetime) else d


# ---------------------------------------------------------------- budget 估计（纯，切片 B）

def estimate_budget_from(
    observations: list[AttentionObservation],
    *,
    lookback_days: Optional[int] = None,
    saturated_quantile: float = 0.25,
    min_saturated_samples: int = 3,
) -> dict:
    """删失感知点估计。confidence:
    observed=足够饱和日；provisional=有饱和日但太少；lower_bound=无饱和日（仅知 capacity≥max）；
    none=warm-up 无数据（L2 必须静止）。"""
    lookback_days = lookback_days or 28
    rows = _window(observations, lookback_days)
    if not rows:
        return dict(estimate=None, confidence="none", n_days=0, n_saturated=0,
                    saturated_samples=[], max_completed=0,
                    reason="no observations yet (warm-up): L2 must stay passive")
    saturated = [r for r in rows if r.queue_remaining > 0]
    max_completed = max(r.completed for r in rows)
    if saturated:
        vals = sorted(float(r.completed) for r in saturated)
        est = max(0.1, _percentile(vals, saturated_quantile))
        confidence = "observed" if len(saturated) >= min_saturated_samples else "provisional"
        reason = (f"{len(saturated)} saturated day(s): ceiling hit at {vals} -> "
                  f"p{int(saturated_quantile*100)} = {est:g}")
    else:
        est = max(0.1, float(max_completed))
        confidence = "lower_bound"
        reason = (f"no saturated day: queue always emptied -> capacity >= {max_completed} "
                  f"(LOWER BOUND, must never lower budget)")
    est = min(est, 500.0)
    return dict(estimate=round(est, 3), confidence=confidence, n_days=len(rows),
                n_saturated=len(saturated), saturated_samples=[r.completed for r in saturated],
                max_completed=max_completed, reason=reason)


def _percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return float(s[lo] + (s[hi] - s[lo]) * frac)


def update_budget_from(
    observations: list[AttentionObservation],
    current: Optional[float],
    *,
    guardrail: bool = True,
) -> dict:
    """把最新观测折叠进预算，带三道防线（删失感知 / 单调护栏 / 阻尼 EMA / 校准期 oversubscribe）。"""
    obs = estimate_budget_from(observations)
    out = dict(old=current, new=current, applied=False, **obs)
    if obs["estimate"] is None:
        out["reason"] += " -> budget unchanged (warm-up)"
        return out
    target = obs["estimate"]
    if current is None:
        out.update(new=round(target, 3), applied=True,
                   reason=obs["reason"] + f" -> bootstrap budget = {target:g}")
        return out
    if target < current and obs["confidence"] == "lower_bound" and guardrail:
        out["reason"] += (" -> guardrail: lower-bound obs cannot LOWER budget "
                          "(that is the collapse path)")
        return out
    alpha = _t("EMA_ALPHA")
    damp = _t("EMA_CLAMP")
    smoothed = current + alpha * (target - current)
    new = max(current * (1 - damp), min(current * (1 + damp), smoothed))
    new = max(0.1, min(500.0, new))
    direction = "raised" if new > current else "lowered" if new < current else "held"
    out.update(new=round(new, 3), applied=abs(new - current) > 1e-9,
               reason=f"{obs['reason']} -> EMA {current:g}->{smoothed:.2f}, "
                      f"damped to {new:.2f} ({direction})")
    return out


def l2_target(budget: Optional[float], confidence: str) -> Optional[float]:
    """L2 拟合目标：未确认估计期 oversubscribe ×1.5（否则 queue 天天空、永远无饱和日）。"""
    if budget is None:
        return None
    if confidence in ("none", "lower_bound", "provisional"):
        return budget * _t("OVERSUBSCRIBE_FACTOR")
    return budget


# ---------------------------------------------------------------- 校准就绪度（同批外生锚）

def calibration_readiness(
    store: Storage,
    *,
    lookback_days: Optional[int] = None,
    calib_min_days: Optional[int] = None,
    calib_min_saturated_days: Optional[int] = None,
) -> dict:
    """更高维阈值校准是否攒够「同批外生锚」。

    与 R13/R14（预算/节奏校准）吃**同一批** ``attention_observation`` 埋点：
    - ``days_with_observation`` = 有观测记录的不同日期数；
    - ``saturated_days``        = 其中 ``queue_remaining > 0`` 的天数（与
      ``estimate_budget_from`` 同一饱和日口径，避免各自重算漂移）。

    两条都达 ``CALIB_MIN_DAYS`` / ``CALIB_MIN_SATURATED_DAYS`` 阈值 → ``can_calibrate``
    通过（``ready=True``），此时 ``tuning.calibrate(CONTEXT_HIGHER_DIM_*, ...)`` 才被放行。

    纯函数层：只吃 ``store.attention.list_recent``，provider 无关（内存 fake / PG 同行为）。
    """
    lookback_days = lookback_days or 28
    c_min_days = calib_min_days or _t("CALIB_MIN_DAYS")
    c_min_sat = calib_min_saturated_days or _t("CALIB_MIN_SATURATED_DAYS")
    rows = store.attention.list_recent(lookback_days)
    days_with_obs = {_as_date(o.day) for o in rows}
    saturated = {_as_date(o.day) for o in rows if o.queue_remaining > 0}
    n_days = len(days_with_obs)
    n_sat = len(saturated)
    ok = tuning.can_calibrate(
        days_with_observation=n_days, saturated_days=n_sat)
    return dict(
        days_with_observation=n_days,
        saturated_days=n_sat,
        calib_min_days=c_min_days,
        calib_min_saturated_days=c_min_sat,
        can_calibrate=ok,
        ready=ok,
        reason=(
            "同批外生锚攒够，可校准" if ok else
            f"外生锚不足：需 ≥{c_min_days} 天埋点(现有 {n_days}) 且 "
            f"≥{c_min_sat} 个饱和日(现有 {n_sat})"
        ),
    )


# ---------------------------------------------------------------- 更高维提议限流（调度层·注意力预算，P1）

def proposal_budget_for_day(store: Storage, day) -> dict:
    """全局每日更高维 context 提议上限（注意力预算一类）。

    归属：调度层，不属 T4.1 切片（去重闸门只防同种子，不防全库每日过量）。本函数是
    该上限的唯一权威来源；逐种子 propose 只防同种子重复，跨种子限流由
    ``ContextAssembler.propose_higher_dim_daily`` 调本函数完成。

    返回 {cap, used, remaining, source}：cap 来自 tuning.PROPOSAL_PER_DAY_CAP
    （占位，待 calibrate() 校准），used 来自 store.attention.count_proposals（当日已提议）。
    """
    p = tuning.param("PROPOSAL_PER_DAY_CAP")
    cap = int(p.value)
    used = store.attention.count_proposals(day, "higher_dim")
    return dict(cap=cap, used=used, remaining=max(0, cap - used), source=p.source)


# ================================================================ 存储编排层

def days_to_interval(days: Optional[float]) -> Optional[timedelta]:
    return None if days is None else timedelta(days=float(days))


def recompute_baseline_on_capture_loss(
    store: Storage, node_id, *, produced_by=None
) -> dict:
    """边界 1（ADR-0002，显式路径）：承载节点的 claim/artifact 被 produced_by 级联撤销后，
    「已捕获」状态消失 → 按未捕获基线重算（有连接 14d / 孤儿 7d）并写 D7 interval_adjustment
    留痕，禁止静默变化。

    与 ``assign_baselines`` 的被动检测互补：本函数供 claim/artifact 撤销路径**立即**调用，
    不依赖下一次 ``assign_baselines`` 全量扫描；两者都写显式 capture-loss 审计。

    返回 {applied, old_days, new_days, reason, tier}。still captured / 不可调度则 applied=False。
    """
    node = store.nodes.get(node_id)
    if node is None:
        raise ValueError(f"node {node_id} not found")
    row = next((r for r in store.load_schedulable() if r.id == node_id), None)
    if row is None:
        return dict(applied=False, old_days=None, new_days=None,
                    reason="node not schedulable (static/archived)", tier=None)
    if row.captured:
        return dict(applied=False, old_days=row.interval_days, new_days=row.interval_days,
                    reason="still captured: no recalc needed", tier="captured")
    sug = baseline_for_node(row)
    if sug["days"] is None:
        return dict(applied=False, old_days=row.interval_days, new_days=row.interval_days,
                    reason="no uncaptured baseline (static/archived)", tier=None)
    old = row.interval_days
    reason = (f"capture-loss via produced_by cascade: recalc by uncaptured rule "
              f"({sug['tier']})")
    store.nodes.set_baseline_interval(
        node_id, days_to_interval(sug["days"]), "auto", reason)
    store.nodes.audit_interval(
        node_id, "baseline", old, sug["days"], reason, produced_by)
    return dict(applied=abs((sug["days"] or 0) - (old or 0)) > 1e-9,
                old_days=old, new_days=sug["days"], reason=reason, tier=sug["tier"])


def assign_baselines(store: Storage, produced_by=None) -> list[dict]:
    """计算并持久化 L1 基线（跳过人工覆盖）。返回每条结果摘要。

    闭环启动：首次给某动态条目赋基线时，同步把 last_reviewed_at 设为 now —— 否则
    last_reviewed_at 为 NULL，list_due_for_review 永远排不出该条目，复审死循环无法启动。
    （已排过期的条目保留原 last_reviewed_at，不重置衰减时钟。）
    """
    out = []
    now = datetime.now(timezone.utc)
    for row in store.load_schedulable():
        if row.source == "human":
            out.append(dict(id=_hid(row.id), days=row.interval_days,
                            reason="human override preserved", tier="human", applied=False))
            continue
        sug = baseline_for_node(row)
        if sug["days"] is None:
            continue
        old = row.interval_days
        # 边界 1（ADR-0002，被动检测）：原基线为已捕获(28d) 但「已捕获」状态已消失
        # （承载它的 claim/artifact 被 produced_by 级联撤销）→ 按未捕获基线重算，且必须
        # 写显式 capture-loss 审计，禁止静默变化（否则「撤销」在调度层不可见）。
        reason = sug["reason"]
        was_captured_baseline = (
            row.baseline_days is not None
            and abs(row.baseline_days - _t("BASELINE_CAPTURED_DAYS")) < 1e-9
            and sug["tier"] != "captured"
        )
        if was_captured_baseline:
            reason = (f"capture-loss via produced_by cascade: recalc by uncaptured rule "
                      f"({sug['tier']})")
        store.nodes.set_baseline_interval(
            row.id, days_to_interval(sug["days"]), "auto", reason)
        store.nodes.audit_interval(
            row.id, "baseline", old, sug["days"], reason, produced_by)
        node = store.nodes.get(row.id)
        if node is not None and node.last_reviewed_at is None:
            store.nodes.mark_reviewed(node.id, now)
        out.append(dict(id=_hid(row.id), applied=True, **sug))
    return out


def fit_budget(store: Storage, budget_per_day: Optional[float],
               produced_by=None) -> dict:
    """L2 预算归一（落到库）。budget None → 被动（warm-up）。"""
    rows = store.load_schedulable()
    result = fit_budget_rows(rows, budget_per_day)
    if not result["degraded"]:
        return result
    tid = store.record_transform("budget_fit", dict(
        budget_per_day=budget_per_day, demand_before=result["demand_before"]))
    for d in result["degraded"]:
        nid = _uuid(store, d["id"])
        store.nodes.set_interval(
            nid, days_to_interval(d["new_days"]), "auto",
            f"attention budget {budget_per_day:g}/day exceeded -> deferred "
            f"(priority={d['priority']})")
        store.nodes.audit_interval(
            nid, "budget", d["old_days"], d["new_days"],
            f"budget {budget_per_day:g}/day exceeded", tid)
    result["transform_id"] = str(tid)
    return result


def adapt_interval(
    store: Storage,
    node_id,
    decay_at_review: float,
    outcome: Optional[str] = None,
    enforce_label_gate: bool = True,
) -> dict:
    """L3 反馈（落到库）。outcome 显式标注或标注率达标才允许改写；否则返回 applied=False。"""
    node = store.nodes.get(node_id)
    if node is None:
        raise ValueError(f"node {node_id} not found")
    verdict = outcome or classify_review(decay_at_review)
    old = (node.review_interval.total_seconds() / 86400.0
           if node.review_interval is not None else None)
    if old is None:
        old = _t("BASELINE_ORPHAN_DAYS")

    if enforce_label_gate and outcome is None:
        gate = labeling_rate_from(_recent_obs(store))
        if gate["rate"] is not None and gate["rate"] < gate["threshold"]:
            return dict(id=_hid(node_id), old_days=old, new_days=old, verdict=verdict,
                        applied=False,
                        reason=f"label gate closed: {gate['reason']} -> interval unchanged")

    if node.interval_source == "human":
        return dict(id=_hid(node_id), old_days=old, new_days=old, verdict=verdict,
                    applied=False, reason="human override preserved")

    math = adapt_interval_math(old, verdict, human=False)
    store.nodes.set_interval(
        node_id, days_to_interval(math["new_days"]), "auto", math["reason"])
    # 无操作（如 on_time 的 AIMD 因子 1.0 → new==old）不写 audit_interval，
    # 避免 7→7 这类无信息量行污染 interval_adjustment 审计表（锚 A 噪声治理）。
    if math["applied"]:
        store.nodes.audit_interval(
            node_id, "feedback", math["old_days"], math["new_days"],
            f"review at decay={decay_at_review:.2f} -> {verdict}", None)
    return dict(id=_hid(node_id), **math)


def estimate_budget(store: Storage) -> dict:
    return estimate_budget_from(_recent_obs(store))


def update_budget(store: Storage, current: Optional[float]) -> dict:
    return update_budget_from(_recent_obs(store), current)


def revert_interval_transform(store: Storage, transform_id) -> int:
    """逆序恢复某 transform 产生的全部 interval 改动并清审计（架构 §6.4 C2 可回滚）。"""
    return store.revert_interval_transform(transform_id)


# ---------------------------------------------------------------- 内部助手

def _recent_obs(store: Storage, days: int = 30) -> list[AttentionObservation]:
    return store.attention.list_recent(days)


def _hid(nid) -> Optional[str]:
    return nid.hex if nid is not None else None


def _uuid(store, hexstr):
    from uuid import UUID
    return UUID(hexstr)

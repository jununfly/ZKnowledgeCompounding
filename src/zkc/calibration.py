"""ZKC · E1 校准闭环进度仪表（roadmap node 1-1 退出判据实时读数）。

原 scripts/e1_calibration_progress.py 的纯逻辑已**提升为本模块**（Form B：zkc CLI
正式化，composer Plan `zkc-daily-run-forms-v1`）。scripts/e1_calibration_progress.py
现为其薄外壳，`zkc meter` 子命令亦复用同一份。详见 docs/roadmap/roadmap.json
1-1.exit_criteria。

E1 退出判据（来自 roadmap 1-1）：
  1) 连续 ≥7 活跃日运行已交付复审队列
  2) 复审标注率闸门 ≥70%（滚动 7 天 labeled_completed / completed）
  3) budget_per_day 派生估计在 [7,14,21,28] 天窗口轨迹收敛（CV≤10% 且 28d confidence=observed）

注意（ADR-0006，A 无状态）：budget_per_day 即 scheduling.estimate_budget_from，
每次从原始埋点重算，无持久化初始值。故「收敛」读数=estimate 在多窗口轨迹聚拢 +
28d confidence=observed。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from zkc import scheduling as S
from zkc.repository import get_storage
from zkc.task_queue import LABEL_JUDGMENT_THRESHOLD


def _as_date(d):
    return d.date() if isinstance(d, datetime) else d


def _classify(o) -> str:
    """单日观测分类（fork 3b 活跃日语义）：
    - active  ：completed >= 1（当日真实复审）
    - missed  ：completed == 0 且 queue_remaining > 0（有 due 未复审 → 断签）
    - excused ：completed == 0 且 queue_remaining == 0（空队列日，不破不断）
    """
    if o.completed >= 1:
        return "active"
    if (o.queue_remaining or 0) > 0:
        return "missed"
    return "excused"


def _evaluate_active_streak(observations) -> dict:
    """E1-① 活跃日语义：连续非断签窗口内活跃日 ≥ 7。

    断签(missed) = 有 due 未复审；空队列日(excused) 不破不断；无观测日按断签处理
    （daemon 应每日写行，缺失即视为漏跑）。返回当前窗口（截至最新观测日）活跃数、
    是否含最新日、历史最长窗口活跃数。
    """
    status: dict = {}
    for o in observations:
        status[_as_date(o.day)] = _classify(o)
    if not status:
        return dict(window_active=0, required=7, latest_ok=False, met=False,
                    longest_window_active=0)
    lo, hi = min(status), max(status)
    best_run = best_active = cur_run = cur_active = 0
    d = lo
    while d <= hi:
        s = status.get(d, "missed")
        if s == "missed":
            best_run = max(best_run, cur_run)
            best_active = max(best_active, cur_active)
            cur_run = cur_active = 0
        else:
            cur_run += 1
            if s == "active":
                cur_active += 1
        d += timedelta(days=1)
    best_run = max(best_run, cur_run)
    best_active = max(best_active, cur_active)
    latest = hi
    run = active = 0
    d = latest
    while d in status and status[d] != "missed":
        run += 1
        if status[d] == "active":
            active += 1
        d -= timedelta(days=1)
    latest_ok = status.get(latest) != "missed"
    met = latest_ok and active >= 7
    return dict(window_active=active, required=7, latest_ok=latest_ok, met=met,
                longest_window_active=best_active)


def _budget_trajectory(observations) -> dict:
    """多窗口估计轨迹：若 [7,14,21,28] 天估计值聚拢 → 收敛信号。"""
    traj = {}
    for w in (7, 14, 21, 28):
        est = S.estimate_budget_from(observations, lookback_days=w)
        traj[w] = est
    estimates = [traj[w]["estimate"] for w in (7, 14, 21, 28) if traj[w]["estimate"] is not None]
    if len(estimates) >= 2:
        spread = max(estimates) - min(estimates)
        mean = sum(estimates) / len(estimates)
        cv = (spread / mean) if mean else 0.0
        converged = cv <= 0.10 and traj[28]["confidence"] == "observed"
    else:
        spread = None
        cv = None
        converged = False
    return dict(windows=traj, spread=spread, cv=cv, converged=converged)


def build_report(storage_kind: str = "pg", storage=None) -> dict:
    """E1 退出判据读数。storage 可注入（direct 模式复用同一 store，内存后端一致）；
    不传则按 storage_kind 新建。"""
    store = storage or get_storage(storage_kind)
    now = datetime.now(timezone.utc)
    obs = store.attention.list_recent(60)  # 宽窗口算连续活跃日串

    streak_info = _evaluate_active_streak(obs)
    active_days_count = sum(1 for o in obs if _classify(o) == "active")

    readiness = S.calibration_readiness(store, lookback_days=28)
    labeling = S.labeling_rate_from(store.attention.list_recent(7))
    budget = _budget_trajectory(obs)

    c1 = streak_info["met"]
    c2 = (labeling.get("gate") == "open"
          and labeling.get("rate") is not None
          and labeling["rate"] >= labeling["threshold"])
    c3 = budget["converged"]
    all_met = c1 and c2 and c3

    return dict(
        as_of=now.isoformat(),
        criteria=dict(
            c1_consecutive_active_days=dict(
                window_active=streak_info["window_active"],
                required=streak_info["required"],
                latest_ok=streak_info["latest_ok"],
                longest_window_active=streak_info["longest_window_active"],
                active_days_in_60d=active_days_count,
                met=c1,
            ),
            c2_labeling_rate_gate=dict(
                rate=labeling.get("rate"),
                threshold=labeling.get("threshold"),
                completed=labeling.get("completed"),
                labeled=labeling.get("labeled"),
                gate=labeling.get("gate"),
                met=c2,
            ),
            c3_budget_convergence=dict(
                estimate_28d=budget["windows"][28]["estimate"],
                confidence_28d=budget["windows"][28]["confidence"],
                saturated_samples=budget["windows"][28]["saturated_samples"],
                spread=budget["spread"],
                cv=budget["cv"],
                converged=budget["converged"],
                met=c3,
            ),
        ),
        calibration_readiness=readiness,
        all_exit_criteria_met=all_met,
    )


def format_human(r: dict) -> None:
    """E1 读数人类可读输出（供 zkc meter 与脚本共用）。"""
    print("=== ZKC · E1 校准闭环进度（node 1-1）===")
    print(f"  as_of: {r['as_of']}")
    c1 = r["criteria"]["c1_consecutive_active_days"]
    c2 = r["criteria"]["c2_labeling_rate_gate"]
    c3 = r["criteria"]["c3_budget_convergence"]
    print(f"\n[1] 连续 ≥7 活跃日（空队列日豁免）：{'✓' if c1['met'] else '✗'} "
          f"（当前窗口活跃 {c1['window_active']}/{c1['required']} 日，"
          f"含最新日={c1['latest_ok']}，历史最长窗口活跃 {c1['longest_window_active']}，"
          f"60 日内活跃日 {c1['active_days_in_60d']}）")
    rate = c2["rate"]
    print(f"[2] 标注率闸门 ≥70%：{'✓' if c2['met'] else '✗'} "
          f"（7 日率 {rate if rate is not None else 'N/A'}，"
          f"阈值 {c2['threshold']}，completed={c2['completed']} labeled={c2['labeled']}，"
          f"gate={c2['gate']}）")
    print(f"[3] budget 收敛：{'✓' if c3['met'] else '✗'} "
          f"（28d 估计 {c3['estimate_28d']}，confidence={c3['confidence_28d']}，"
          f"饱和样本 {c3['saturated_samples']}，spread={c3['spread']}，cv={c3['cv']}）")
    rd = r["calibration_readiness"]
    print(f"\n校准就绪度（can_calibrate 门禁）：days_with_obs={rd['days_with_observation']}"
          f"/{rd['calib_min_days']}，saturated_days={rd['saturated_days']}/{rd['calib_min_saturated_days']}，"
          f"ready={rd['ready']}")
    print(f"\n>>> E1 退出判据全满足：{'YES ✅' if r['all_exit_criteria_met'] else 'NO ⏳'}")


# --- PRD §9 P6.4 观察期达成读数（只读；与 E1 校准闭环判据独立）-------------

def build_p64_report(storage_kind: str = "pg", storage=None) -> dict:
    """P6.4 观察期两条判据的实时读数；纯读，不写任何埋点。

    判据与 E1 校准闭环独立：
      ① 累计 labeled_completed ≥ LABEL_JUDGMENT_THRESHOLD（不要求日历连续）；
      ② 滚动 7 天样本达标且标注率 ≥ 阈值。

    `S.labeling_rate_from` 的 gate 字段**不可**直接当判据：样本不足时返回
    rate=None / gate="open"（warm-up 放行），rate≥阈值时同样是 gate="open"，
    而 gate="closed" 反而是 rate<阈值停机。故只认 rate 是否非 None 且达标。
    阈值复用 task_queue.LABEL_JUDGMENT_THRESHOLD，禁止另起常量。
    """
    store = storage or get_storage(storage_kind)
    now = datetime.now(timezone.utc)
    obs = store.attention.list_recent(366)
    total_completed = sum((o.completed or 0) for o in obs)
    total_labeled = sum((o.labeled_completed or 0) for o in obs)
    threshold = LABEL_JUDGMENT_THRESHOLD
    c1 = total_labeled >= threshold

    labeling = S.labeling_rate_from(store.attention.list_recent(7))
    rate = labeling.get("rate")
    c2 = rate is not None and rate >= labeling["threshold"]

    return dict(
        as_of=now.isoformat(),
        criteria=dict(
            c1_cumulative_labeled=dict(
                total_labeled=total_labeled,
                threshold=threshold,
                remaining=max(0, threshold - total_labeled),
                total_completed=total_completed,
                days_with_observation=len(obs),
                met=c1,
            ),
            c2_rolling_labeling_rate=dict(
                rate=rate,
                threshold=labeling.get("threshold"),
                completed=labeling.get("completed"),
                labeled=labeling.get("labeled"),
                gate=labeling.get("gate"),
                reason=labeling.get("reason"),
                met=c2,
            ),
        ),
        all_exit_criteria_met=c1 and c2,
    )


def format_p64_human(r: dict) -> None:
    """P6.4 读数人类可读输出（供 `zkc p64` 与脚本共用）。"""
    c1 = r["criteria"]["c1_cumulative_labeled"]
    c2 = r["criteria"]["c2_rolling_labeling_rate"]
    print("=== ZKC · PRD §9 P6.4 观察期达成读数（只读）===")
    print(f"  as_of: {r['as_of']}")
    print(f"\n[1] 累计带标注复审 ≥{c1['threshold']}：{'✓' if c1['met'] else '✗'} "
          f"（{c1['total_labeled']}/{c1['threshold']}，还差 {c1['remaining']}；"
          f"累计 completed={c1['total_completed']}，观测天数={c1['days_with_observation']}）")
    rate = c2["rate"]
    print(f"[2] 滚动 7 天标注率 ≥{c2['threshold']:.0%}：{'✓' if c2['met'] else '✗'} "
          f"（rate={rate if rate is not None else 'N/A'}，"
          f"completed={c2['completed']} labeled={c2['labeled']}，gate={c2['gate']}）")
    print(f"    {c2['reason']}")
    print(f"\n>>> P6.4 判据全满足：{'YES ✅' if r['all_exit_criteria_met'] else 'NO ⏳'}")
    print("    本读数只读、不写埋点；达成后 PRD §9 TODO 与风险册状态由 zj 决定，勿自动勾销。")

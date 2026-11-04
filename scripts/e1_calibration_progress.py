"""ZKC · E1 校准闭环进度仪表（roadmap node 1-1 退出判据实时读数）。

E1 退出判据（来自 docs/roadmap/roadmap.json 1-1.exit_criteria）：
  1) 连续 ≥7 活跃日运行已交付复审队列
  2) 复审标注率闸门 ≥70%（滚动 7 天 labeled_completed / completed）
  3) budget_per_day 派生估计在 [7,14,21,28] 天窗口轨迹收敛（CV≤10% 且 28d confidence=observed）

注意（见 ADR-0006，2026-11-04 zj 拍板取 A 无状态）：budget_per_day 即
scheduling.estimate_budget_from(attention_observation)，每次从原始埋点重算，
没有也不需要有「持久化初始值」。故「收敛」读数为：estimate 在多窗口
[7/14/21/28] 天轨迹上聚拢（CV≤10%）且 28d confidence=observed。

本脚本只读，不写任何数据，可直接在 zj 本机（PG 起 + make serve）跑：
    python scripts/e1_calibration_progress.py            # 默认 PG
    python scripts/e1_calibration_progress.py --storage memory
    python scripts/e1_calibration_progress.py --json     # 机器可读（管道/周报复盘）

单会话无法伪造：≥7 活跃日依赖真实日历推进，须在 zj 本机每日用 /review
做真实复审 + 每日收口（/review/api/observe）累积 attention_observation。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zkc import scheduling as S
from zkc.repository import get_storage


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

    注：收口(queue_remaining) 只影响 E1-③/can_calibrate，不影响本判据——活跃日
    仅靠 decide 产生的 completed>=1 判定（见 ADR-0007）。
    """
    status: dict = {}
    for o in observations:
        status[_as_date(o.day)] = _classify(o)
    if not status:
        return dict(window_active=0, required=7, latest_ok=False, met=False,
                    longest_window_active=0)
    lo, hi = min(status), max(status)
    # 全局最长连续非断签窗口 + 其中活跃数
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
    # 当前窗口：截至最新观测日向后连续的活跃数
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

    # 退出判据逐条判等
    c1 = streak_info["met"]
    c2 = labeling.get("gate") == "open" and labeling.get("rate") is not None and labeling["rate"] >= labeling["threshold"]
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


def _print_human(r: dict) -> None:
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


def main() -> None:
    ap = argparse.ArgumentParser(description="ZKC E1 校准闭环进度仪表（只读）")
    ap.add_argument("--storage", default="pg", help="pg（默认）或 memory")
    ap.add_argument("--json", action="store_true", help="输出 JSON 供管道消费")
    args = ap.parse_args()
    r = build_report(args.storage)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(r)


if __name__ == "__main__":
    main()

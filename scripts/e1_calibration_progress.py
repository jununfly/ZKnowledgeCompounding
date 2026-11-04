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


def _distinct_active_days(observations, *, min_completed: int = 1) -> set:
    """活跃日 = 当日 real 复审发生（completed >= min_completed）。"""
    return {
        _as_date(o.day)
        for o in observations
        if o.completed >= min_completed
    }


def _longest_consecutive_streak(days: set[object]) -> tuple[int, bool]:
    """返回 (最长连续活跃日串长度, 是否含最新一天)。"""
    if not days:
        return 0, False
    sorted_days = sorted(days)
    latest = sorted_days[-1]
    best = run = 1
    for prev, cur in zip(sorted_days, sorted_days[1:]):
        if (cur - prev).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    # 含最新一天？
    contains_latest = True
    d = latest
    while (d in days) and run >= 1:
        run -= 1
        d -= timedelta(days=1)
    return best, (latest in days)


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


def build_report(storage_kind: str = "pg") -> dict:
    store = get_storage(storage_kind)
    now = datetime.now(timezone.utc)
    obs = store.attention.list_recent(60)  # 宽窗口算连续活跃日串

    active_days = _distinct_active_days(obs)
    streak, contains_latest = _longest_consecutive_streak(active_days)

    readiness = S.calibration_readiness(store, lookback_days=28)
    labeling = S.labeling_rate_from(store.attention.list_recent(7))
    budget = _budget_trajectory(obs)

    # 退出判据逐条判等
    c1 = streak >= 7 and contains_latest
    c2 = labeling.get("gate") == "open" and labeling.get("rate") is not None and labeling["rate"] >= labeling["threshold"]
    c3 = budget["converged"]
    all_met = c1 and c2 and c3

    return dict(
        as_of=now.isoformat(),
        criteria=dict(
            c1_consecutive_active_days=dict(
                longest_streak=streak,
                includes_latest_day=contains_latest,
                distinct_active_days_in_60d=len(active_days),
                required=7,
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
    print(f"\n[1] 连续 ≥7 活跃日：{'✓' if c1['met'] else '✗'} "
          f"（最长连续串 {c1['longest_streak']} 日，含最新日={c1['includes_latest_day']}，"
          f"60 日内活跃日 {c1['distinct_active_days_in_60d']}）")
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

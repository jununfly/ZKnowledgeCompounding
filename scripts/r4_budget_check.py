#!/usr/bin/env python
"""R4 注意力预算校验（1-8-6）：对真实语料跑 n/(0.6×interval) 需求 vs 预算。

复用 zkc/scheduling.py 现成机器（零重复实现）：
  daily_demand = Σ 1/(0.6×Iᵢ)（架构 §6.5 需求公式）
  fit_budget_rows = L2 预算归一（优先级延后，诚实降级契约）
  estimate_budget = 删失感知预算估计（attention_observation 埋点）

健康度量（R4 真信号）：被 L2 延后的条目若 0.6×I_eff/I_base ≥ ROT_THRESHOLD(0.9)，
复审时 decay 必已到腐化线——该比例 >0 说明当前预算撑不住真实腐化节奏，
「衰减可控」指标将恒 0。**只报告不调参**：处置选项见 roadmap 1-8-6 decide
（① 观察期真实 budget 产出后重跑 ② 缩动态集 ③ 调 SURFACE_THRESHOLD）。

用法：python scripts/r4_budget_check.py [--dry-run 默认即只读]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc import scheduling, tuning  # noqa: E402
from zkc.repository import get_storage  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="R4 注意力预算校验（只读）")
    ap.parse_args(argv)

    store = get_storage()
    rows = store.load_schedulable()
    n = len(rows)
    surface = tuning.get("SURFACE_THRESHOLD")
    max_iv = tuning.get("MAX_INTERVAL_DAYS")

    # ① 预算：观察期估计 → confidence=none 回退 DEFAULT
    est = scheduling.estimate_budget(store)
    if est["estimate"] is None:
        budget = float(tuning.get("BUDGET_PER_DAY_DEFAULT"))
        budget_source = f"DEFAULT（estimator confidence=none，warm-up 回退）"
    else:
        budget = est["estimate"]
        budget_source = f"观测估计（confidence={est['confidence']}）"
    target = scheduling.l2_target(budget, est["confidence"])

    # ② L1 需求 + L2 拟合（纯函数，不落库）
    demand_l1 = scheduling.daily_demand(rows)
    fit = scheduling.fit_budget_rows(rows, target)

    # ③ 健康度量：复审前已到 ROT 的被延后条目
    row_by_id = {str(r.id): r for r in rows if r.id is not None}
    rot = tuning.get("ROT_THRESHOLD")
    rot_before_review = []
    for d in fit["degraded"]:
        r = row_by_id.get(d["id"])
        base = r.baseline_days if (r and r.baseline_days) else d["old_days"]
        ratio = surface * d["new_days"] / base  # 复审时 decay = 0.6×I_eff/I_base
        if ratio >= rot:
            rot_before_review.append(dict(id=d["id"], old_days=d["old_days"],
                                          new_days=d["new_days"],
                                          decay_at_review=round(min(ratio, 9.9), 2)))

    out = dict(
        n_schedulable=n,
        budget=budget,
        budget_source=budget_source,
        l2_target=round(target, 3) if target else None,
        budget_estimate_obs=est,
        demand_at_L1=round(demand_l1, 3),
        demand_after_L2=fit["demand_after"],
        l2_applied=fit["applied"],
        n_degraded=len(fit["degraded"]),
        infeasible=fit["infeasible"],
        max_dynamic_items=fit["max_dynamic_items"],
        max_allowed=int(budget * surface * max_iv),
        n_rot_before_review=len(rot_before_review),
        rot_before_review_detail=rot_before_review,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))

    print("\n=== R4 判定 ===")
    print(f"  预算: {budget:g}/天（{budget_source}）; L2 拟合目标 {target:g}")
    print(f"  L1 需求 Σ1/(0.6×I) = {demand_l1:g}/天 → {'超预算' if demand_l1 > target else '可承载'}")
    if fit["applied"]:
        print(f"  L2 延后 {len(fit['degraded'])} 条; demand_after={fit['demand_after']:g}; "
              f"infeasible={fit['infeasible']}; max_dynamic_items={fit['max_dynamic_items']}")
    if rot_before_review:
        print(f"  ⚠ 健康信号: {len(rot_before_review)}/{n} 条被延后后在复审时 decay 已 ≥{rot:g}"
              f"（注定腐化）→ 当前预算撑不住真实腐化节奏，衰减可控指标将恒 0")
        print("  处置选项（不静默调参）: ① 1-7-4 观察期产出真实 budget 后重跑本探针；"
              "② 缩小动态集（DISTILL/ARCHIVE 归档）；③ 调 SURFACE_THRESHOLD（需留痕）")
    elif not fit["applied"]:
        print("  需求 ≤ 预算，L2 未触发——预算校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

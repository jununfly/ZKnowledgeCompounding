#!/usr/bin/env python3
"""ZKC · R14 真实数据侧裁决状态（R14 真实数据侧视图工具）。

读 data/r14_telemetry.jsonl（由 dogfood 脚本在真实 run 时落库），跑 judge_r14
聚合，打印当前 R14 裁决。供 zj 积累真实 run 后随时查看是否该关补全。

用法：
    python3 scripts/r14_status.py [--min-runs N] [--path <telemetry.jsonl>]
    python3 scripts/r14_status.py --reset        # 清空遥测样本（重新积累）

判据（risks.md R14）：触发率 > 50% 且 补全延迟中位 > 主生成延迟中位 × 1.5 → 关补全。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc.cross_source import R14_MIN_RUNS_DEFAULT  # noqa: E402
from zkc.r14_telemetry import DEFAULT_TELEMETRY_PATH, aggregate, load_runs  # noqa: E402


def _fmt(v) -> str:
    return (
        f"total={v.total}  fired={v.fired}  trigger_rate={v.trigger_rate:.3f}\n"
        f"main_latency_median={v.main_latency_median:.1f}ms\n"
        f"completion_latency_median="
        f"{'None' if v.completion_latency_median is None else f'{v.completion_latency_median:.1f}ms'}\n"
        f"should_close_completion={v.should_close_completion}\n"
        f"reason={v.reason}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="R14 真实数据侧裁决状态")
    ap.add_argument("--min-runs", type=int, default=R14_MIN_RUNS_DEFAULT)
    ap.add_argument("--path", default=DEFAULT_TELEMETRY_PATH)
    ap.add_argument("--reset", action="store_true", help="清空遥测样本（重新积累）")
    args = ap.parse_args()

    p = Path(args.path)
    if args.reset:
        if p.exists():
            p.unlink()
            print(f"RESET: removed {p}")
        else:
            print(f"RESET: nothing to remove ({p} absent)")
        return 0

    runs = load_runs(p)
    print(f"=== R14 telemetry status (file={p}) ===")
    print(f"samples_on_disk={len(runs)}  min_runs={args.min_runs}")
    v = aggregate(p, min_runs=args.min_runs)
    print("--- judge_r14 verdict ---")
    print(_fmt(v))
    print("--- action ---")
    if v.should_close_completion:
        print("→ 真实数据满足关补全条件：建议 zj 据实更新 risks.md R14 为关补全（complete_on_shortfall 默认关）。")
    elif v.reason == "insufficient_data":
        print("→ 样本不足：继续用 dogfood 跑真实 run 积累样本（≥ min_runs）。")
    else:
        print("→ 真实数据下补全回路预算可控：保持 completion 开启，R14 据实收口为『确认安全』。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

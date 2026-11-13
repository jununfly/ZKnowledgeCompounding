"""ZKC · E1 校准闭环进度仪表（CLI 便捷入口）。

纯逻辑已提升为 zkc.calibration（Form B：zkc meter 子命令复用同一份）。本脚本保留为
可选便捷入口，等价于 `zkc meter`：

    python scripts/e1_calibration_progress.py            # 默认 PG
    python scripts/e1_calibration_progress.py --storage memory
    python scripts/e1_calibration_progress.py --json     # 机器可读

详见 src/zkc/calibration.py 与 ADR-0006（E1 校准闭环）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from zkc.calibration import build_report, format_human


def main() -> None:
    ap = argparse.ArgumentParser(description="ZKC E1 校准闭环进度仪表（只读）")
    ap.add_argument("--storage", default="pg", help="pg（默认）或 memory")
    ap.add_argument("--json", action="store_true", help="输出 JSON 供管道消费")
    args = ap.parse_args()
    r = build_report(args.storage)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        format_human(r)


if __name__ == "__main__":
    main()

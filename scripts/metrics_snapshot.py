"""ZKC · 每周度量快照（P6.3 复盘节奏的可执行入口）。

打印当前 `zkc.metrics.metrics_report` 为 JSON，供周五复盘或管道消费：

    python scripts/metrics_snapshot.py                  # 用默认存储（PG）
    python scripts/metrics_snapshot.py --storage memory # 用内存 fake（CI / 无 PG 时自测）

输出即 metrics_report 的字典（含复利系数、五项分量、口径说明与注意力预算需求）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 允许脚本脱离 `python -m` 直接运行：把项目根（scripts 的上一级）加入导入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zkc import metrics as M
from zkc.repository import get_storage


def build_snapshot(storage_kind: str = "pg") -> dict:
    store = get_storage(storage_kind)
    report = M.metrics_report(store)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="ZKC 复利度量快照（JSON 输出）")
    ap.add_argument("--storage", default="pg",
                    help="存储后端：pg（默认）或 memory（CI/自测）")
    args = ap.parse_args()
    print(json.dumps(build_snapshot(args.storage), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""ZKC · R14 真实数据侧落库聚合（R14 真实数据侧）。

背景：``cross_source.judge_r14``（R14 判据 TDD 收口）已把 R14「补全回路延迟成本」
判据落成可机械判定的纯函数，但真实生产 run 的 report
（``completion_fired`` / ``main_latency_ms`` / ``completion_latency_ms``）此前
只在 dogfood 脚本里 print，**从不被持久化聚合**——这正是 ``risks.md`` R14 行
「关闭仍挂真实生产 run 落库聚合」所指的缺口。

本模块把「真实 run 落库聚合」补上，是 agent 能交付的工程部分；**真实 run 由 zj
经 dogfood 脚本产生，本模块绝不伪造数据**：

- ``record_run``：把一次真实 combine/apply_combine 的 report 追加到 JSONL 遥测
  文件（append-only；run_id 去重，绝不修改已写行、绝不改写 completion_fired/延迟）。
- ``load_runs``：读回全部真实 run 的 report。
- ``aggregate``：``load_runs`` + ``judge_r14``，把裁决交给调用方/Human 据实判定。

落库载体 = ``data/r14_telemetry.jsonl``（append-only 本地遥测，不引 DB migration、
不碰核心 schema；最小可行、可人审、可清空重采）。判据完全复用 ``judge_r14``，不重写。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .cross_source import R14_MIN_RUNS_DEFAULT, R14Verdict, judge_r14

# 真实 run 遥测落点（相对项目根；dogfood 从项目根运行）
DEFAULT_TELEMETRY_PATH = "data/r14_telemetry.jsonl"

# judge_r14 要求 report 必备的三字段（R14 埋点）
REQUIRED_FIELDS = ("completion_fired", "main_latency_ms", "completion_latency_ms")


def _validate_report(report: dict) -> None:
    if not isinstance(report, dict):
        raise ValueError("report must be a dict")
    missing = [f for f in REQUIRED_FIELDS if f not in report]
    if missing:
        raise ValueError(f"report missing required field(s): {', '.join(missing)}")


def record_run(
    report: dict,
    *,
    path: str | Path = DEFAULT_TELEMETRY_PATH,
    run_id: Optional[str] = None,
) -> dict:
    """把一次真实 combine run 的 report 追加到遥测 JSONL（append-only）。

    返回被写入的记录 dict（含写入时间戳与 run_id）；若 ``run_id`` 已存在则跳过
    写入并返回 ``{"skipped": True, "run_id": run_id}``，避免重复 run 污染触发率。
    绝不修改已有行、绝不伪造 ``completion_fired`` / 延迟字段。

    真实 run 由 zj 经 dogfood 产生；本函数只负责落库，不通模型、不碰核心 schema。
    """
    _validate_report(report)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    existing_ids: set[str] = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec.get("run_id")
            if rid:
                existing_ids.add(rid)

    if run_id is not None and run_id in existing_ids:
        return {"skipped": True, "run_id": run_id}

    rec = {
        "run_id": run_id,
        "recorded_at": time.time(),
        "report": {
            "completion_fired": bool(report["completion_fired"]),
            "main_latency_ms": float(report["main_latency_ms"]),
            "completion_latency_ms": (
                None if report["completion_latency_ms"] is None
                else float(report["completion_latency_ms"])
            ),
        },
    }
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load_runs(path: str | Path = DEFAULT_TELEMETRY_PATH) -> list[dict]:
    """读回全部真实 run 的 report（空文件/不存在 → []）。

    容错：跳过空行、JSON 损坏行，以及缺少必备字段的记录（不计入触发率）。
    """
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        rep = rec.get("report")
        if rep and all(f in rep for f in REQUIRED_FIELDS):
            out.append(rep)
    return out


def aggregate(
    path: str | Path = DEFAULT_TELEMETRY_PATH,
    *,
    min_runs: int = R14_MIN_RUNS_DEFAULT,
) -> R14Verdict:
    """``load_runs`` + ``judge_r14``：在真实数据上给出 R14 裁决（不读模型、不碰 IO 之外状态）。"""
    return judge_r14(load_runs(path), min_runs=min_runs)

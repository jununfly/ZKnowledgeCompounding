"""墓碑真删月扫（ADR-0013 Q5 / S6）。

触发：挂现有每日 automation 的非侵入调用；本模块内部月度门闩判定，未到月份 no-op。
不注册系统级调度（launchd/schtasks）。硬约束：
  - 月度门闩：最近 purge 审计与 now 同月 → no-op（同月重复扫描幂等）。
  - TTL=7d 从墓碑时刻起算（ADR-0013 Q5 裁决，非校准阈值，不入 REGISTRY）。
    月扫实际真删落在墓碑后 7~37 天（Q5 已接受此延迟）。
  - 只处理已满 TTL 的既有墓碑；**绝不**自动 mark/restore（人环不可被定时任务代理）。
  - dry-run 零写入；每候选过 S4 引用闸门，被引用则跳过（闸门已写 task_queue 告警）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from zkc.purge import purge_node

TTL_DAYS = 7  # ADR-0013 Q5：7d 墓碑起算；月度门闩 → 实际 7~37d。非校准阈值，不入 REGISTRY。


def _same_month(a: datetime, b: datetime) -> bool:
    return a.year == b.year and a.month == b.month


def sweep_tombstones(store, *, now: datetime, operator: str,
                     dry_run: bool = False) -> dict:
    """月扫：月度门闩 → 列已满 TTL 墓碑 → 逐个过闸门真删。返回报告 dict。"""
    report = {
        "now": now.isoformat(), "dry_run": dry_run, "operator": operator,
        "ttl_days": TTL_DAYS, "noop_month_gate": False,
        "scanned": 0, "eligible": 0, "purged": 0, "blocked": 0,
        "purged_ids": [], "blocked_ids": [],
    }

    last = store.last_purge_at()
    if last is not None and _same_month(last, now):
        report["noop_month_gate"] = True
        return report

    all_tombstones = store.nodes.list_tombstones_before(now)
    report["scanned"] = len(all_tombstones)
    cutoff = now - timedelta(days=TTL_DAYS)
    candidates = [n for n in all_tombstones if n.deleted_at is not None and n.deleted_at <= cutoff]

    for node in candidates:
        # dry-run：只统计合格候选，不写任何数据、不调闸门（闸门会写 task_queue）
        if dry_run:
            report["eligible"] += 1
            continue
        res = purge_node(store, node.id, operator=operator, at=now, ttl_days=TTL_DAYS)
        if res["purged"]:
            report["purged"] += 1
            report["purged_ids"].append(str(node.id))
        else:
            report["blocked"] += 1
            report["blocked_ids"].append(str(node.id))

    return report

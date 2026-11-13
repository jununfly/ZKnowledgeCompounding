"""ZKC · D2 导入语料隔离（只读筛选 + 批量归档，绝不碰外生锚）。

导入的 AI-Coding 子文档按 orphan 1d 节奏逐日逾期，不是 zj 真实消费的知识；
对其给 verdict 属伪标注（架构 §6.5.1 / ADR-0006）。正确处置是**移出调度回路**。

识别方式（等价字段，不新增 schema 列）：动态轨 + decay=1.0 + review_interval=1d
+ last_reviewed_at=2026-11-01 + 未归档。归档只写 archived_at，
不写 attention_observation、不写 labeled、不 resolve 任何 review_queue 条目。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

CORPUS_ACTION = "bulk corpus cleanup"
CORPUS_LAST_REVIEWED_DATE = "2026-11-01"
CORPUS_INTERVAL_SECONDS = 86400.0


def select_corpus_nodes(store, *, track: str = "dynamic") -> list:
    """按派生特征列出仍是活跃状态的导入语料。"""
    out = []
    for node in store.nodes.list_by_track(track):
        if node.archived_at is not None:
            continue
        if (node.decay_score or 0.0) < 1.0:
            continue
        interval = node.review_interval
        if interval is None or float(interval.total_seconds()) != CORPUS_INTERVAL_SECONDS:
            continue
        last = node.last_reviewed_at
        if last is None or last.date().isoformat() != CORPUS_LAST_REVIEWED_DATE:
            continue
        out.append(node)
    return out


def archive_corpus(store, *, dry_run: bool = False, at=None) -> dict[str, Any]:
    """批量归档；dry_run 只预览命中，不写库。"""
    matched = select_corpus_nodes(store)
    at = at or datetime.now(timezone.utc)
    archived_ids: list[str] = []
    if not dry_run:
        for node in matched:
            store.nodes.archive(node.id, at)
            archived_ids.append(str(node.id))
    return {
        "action": CORPUS_ACTION,
        "matched": len(matched),
        "archived": len(archived_ids),
        "dry_run": dry_run,
        "archived_at": at.isoformat(),
        "matched_node_ids": [str(n.id) for n in matched],
        "archived_node_ids": archived_ids,
        # 外生锚保护：以下三项必须恒为 0。
        "labeled_touched": 0,
        "attention_observation_touched": 0,
        "review_queue_resolved": 0,
        "note": (
            "识别 = 动态轨 + decay=1.0 + 1d 节奏 + last_reviewed_at=2026-11-01 + 未归档；"
            "归档只写 archived_at，退出 list_due_for_review / load_schedulable，"
            "不计入 labeled、不污染校准标注率"
        ),
    }


__all__ = [
    "CORPUS_ACTION", "CORPUS_LAST_REVIEWED_DATE",
    "select_corpus_nodes", "archive_corpus",
]

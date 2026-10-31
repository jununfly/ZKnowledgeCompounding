"""ZKC · 冷启动 dogfood 种子（P4.2 复审队列验证前置）。

向 PG 播种 4 条「到期待复审」的动态轨节点（标题前缀 DOGFOOD，便于清理），
分别用于验证四种复审结果：still_valid / changed / stale / browse。

  入队条件（zkc.repository.pg.list_due_for_review）：
    decay_score >= SURFACE(0.6) AND review_interval NOT NULL
    AND last_reviewed_at NOT NULL AND (last_reviewed_at + review_interval) <= now

  故设：review_interval=7d, baseline_interval=7d, last_reviewed_at=now-12d
    → decay ≈ 12/7 钳到 1.0(>=0.6)；last_reviewed_at+7d = now-5d <= now（入队）

运行：python scripts/dogfood_review_seed.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

# 允许脚本脱离 `python -m` 直接运行：把项目根（scripts 的上一级）加入导入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zkc.repository import get_storage
from zkc.repository.models import Node

PREFIX = "DOGFOOD"
TITLES = [
    "DOGFOOD 待复审-仍有效样本",
    "DOGFOOD 待复审-已变样本",
    "DOGFOOD 待复审-已腐样本",
    "DOGFOOD 待复审-仅浏览样本",
]


def seed() -> list[str]:
    store = get_storage("pg")
    now = datetime.now(timezone.utc)
    # 幂等：先清旧 DOGFOOD（含今日 attention_observation，避免按天累加污染验证）
    with store._conn.cursor() as cur:  # type: ignore[attr-defined]
        cur.execute("DELETE FROM public.interval_adjustment WHERE node_id IN "
                    "(SELECT id FROM public.node WHERE title LIKE %(p)s)", dict(p=PREFIX + "%"))
        cur.execute("DELETE FROM public.attention_observation WHERE day = current_date")
        cur.execute("DELETE FROM public.node WHERE title LIKE %(p)s", dict(p=PREFIX + "%"))
        store._conn.commit()

    ids: list[str] = []
    for title in TITLES:
        node = Node(
            id=None,
            track="dynamic",
            routing_confidence=1.0,
            title=title,
            content=None,
            valid_from=now,
            decay_score=0.9,
            review_interval=timedelta(days=7),
            last_reviewed_at=now - timedelta(days=12),
            attention_signal=0.0,
            archived_at=None,
            baseline_interval=timedelta(days=7),
            interval_source="auto",
        )
        saved = store.nodes.save(node)
        ids.append(str(saved.id))
        print(f"seeded {saved.id}  {title}")
    return ids


if __name__ == "__main__":
    ids = seed()
    print(f"DONE {len(ids)} nodes: {ids}")

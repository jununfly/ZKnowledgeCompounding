"""ZKC · MCP `zkc_scheduler_due` handler 契约入口（A 路径原始侧）。

同 zkc_query.py / zkc_review_queue.py：MCP tool 是 stdio，本脚本把 handler 的业务载荷在 seed 库上
直接跑并打印 JSON，作为可录制契约。

    ZKC_PG_DSN=... python3 scripts/zkc_scheduler_due.py --json --as-of 2026-06-15T00:00:00+00:00 --limit 50

契约：{"as_of":str,"items":[{"node_id","title","track","decay_score","review_interval_days","interval_source"}...],
       "due_count":int, "semantics":str}

刻意约束：
  - as_of 必填显式（handler 默认 datetime.now ⇒ 非确定；本契约要求 canonical UTC-ISO 串，echo 之）。
  - 排序规范化：pg.py::list_due_for_review 无 ORDER BY（堆序未定义）。为可重放，本契约与 sqlx 侧
    一律按 node_id 升序输出，再取 [:limit]；due_count = 过滤后全量。这是对**未定义顺序的合法规范化**，
    不改变「哪些节点 due」的判定（谓词逐字复刻 pg.py：decay>=SURFACE & interval/last_reviewed 非空
    & last_reviewed+interval<=as_of & archived/deleted IS NULL）。
  - decay_score round(...,3)；review_interval_days = review_interval.total_seconds()/86400.0。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zkc.repository import get_storage

SEMANTICS = "注意力预算：该关注清单（decay 到期且需投入注意力）"


def _as_of(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main() -> None:
    ap = argparse.ArgumentParser(description="ZKC zkc_scheduler_due 契约（JSON）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--storage", default=None)
    ap.add_argument("--as-of", dest="as_of", required=True)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    store = get_storage(args.storage or os.environ.get("ZKC_STORAGE", "pg"))
    as_of = _as_of(args.as_of)
    due = sorted(store.nodes.list_due_for_review(as_of), key=lambda n: str(n.id))
    items = []
    for node in due:
        iv = node.review_interval
        items.append({
            "node_id": str(node.id),
            "title": node.title,
            "track": node.track,
            "decay_score": round(node.decay_score, 3),
            "review_interval_days": (iv.total_seconds() / 86400.0) if iv is not None else None,
            "interval_source": node.interval_source,
        })
    out = {
        "as_of": as_of.isoformat(),
        "items": items[: args.limit],
        "due_count": len(items),
        "semantics": SEMANTICS,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

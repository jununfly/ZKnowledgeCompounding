"""ZKC · 检索的对外契约入口（search A 路径的原始侧 / app-record 入口）。

结构化检索（R18「结构化为主」）的稳定 JSON 输出，供前端/管道与 Rust A 路径对齐：

    python3 scripts/zkc_search.py --json --storage pg --track dynamic --order created_desc --limit 10
    python3 scripts/zkc_search.py --json --storage memory
    ZKC_PG_DSN=... python3 scripts/zkc_search.py --json --q shared --decay-min 0.5

契约（deterministic，sqlx 侧须逐字节复现）：
  {"hits":[{"id","title","content","track","decay_score","created_at","source","sim"}...],
   "structured_count":int, "embedding_count":int, "degraded":bool, "degrade_reason":str|null}

刻意约束，避免已知编码/浮点雷区：
  - 结构化-only：不注入 encoder，故 embedding 候选召回分支恒空、degraded=false（余弦/双列属另一 A 路径）。
  - decay_score 统一 round(…,4)：PG `real`(float32) 直读会得到 0.8999999761581421 之类噪声（见
    metrics_report 同类踩坑），按 4 位收敛成与原实现「显示值」一致的确定数。
  - created_at 用 aware UTC datetime.isoformat()（形如 ...+00:00）；null 透传 null。
  - 字段顺序固定（dict 插入序 = JSON 序），键序即契约。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zkc import search as SE
from zkc.repository import get_storage

# Fixed UTC format; byte-matches the sqlx A-path's
# `to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') || '+00:00'`, and is immune
# to session-timezone / microsecond drift that `.isoformat()` would leak.
_UTC_FMT = "%Y-%m-%dT%H:%M:%S+00:00"


def _node_dict(n) -> dict:
    ca = n.created_at.astimezone(timezone.utc).strftime(_UTC_FMT) if n.created_at is not None else None
    return {
        "id": str(n.id),
        "title": n.title,
        "content": n.content,
        "track": n.track,
        "decay_score": round(n.decay_score or 0.0, 4),
        "created_at": ca,
    }


def run_search(store, *, q, track, decay_min, decay_max, include_archived, order, limit) -> dict:
    res = SE.search(
        store, q=q, track=track, decay_min=decay_min, decay_max=decay_max,
        include_archived=include_archived, order=order, limit=limit,
    )
    return {
        "hits": [{**_node_dict(h.node), "source": h.source, "sim": h.sim} for h in res["hits"]],
        "structured_count": res["structured_count"],
        "embedding_count": res["embedding_count"],
        "degraded": res["degraded"],
        "degrade_reason": res["degrade_reason"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="ZKC 结构化检索（JSON 契约）")
    ap.add_argument("--storage", default=None, help="pg（默认经 get_storage）或 memory")
    ap.add_argument("--json", action="store_true", help="JSON 输出（契约默认即 JSON）")
    ap.add_argument("--q", default=None)
    ap.add_argument("--track", default=None)
    ap.add_argument("--decay-min", dest="decay_min", type=float, default=None)
    ap.add_argument("--decay-max", dest="decay_max", type=float, default=None)
    ap.add_argument("--include-archived", dest="include_archived", action="store_true")
    ap.add_argument("--order", default="created_desc",
                    choices=["created_desc", "created_asc", "decay_desc"])
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    store = get_storage(args.storage or os.environ.get("ZKC_STORAGE", "pg"))
    out = run_search(
        store, q=args.q, track=args.track, decay_min=args.decay_min, decay_max=args.decay_max,
        include_archived=args.include_archived, order=args.order, limit=args.limit,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

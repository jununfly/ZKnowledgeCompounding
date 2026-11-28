"""ZKC · MCP `zkc_review_queue_list` handler 的对外契约入口（A 路径原始侧）。

同 zkc_query.py：MCP tool 是 stdio，本脚本把 handler 的业务返回体在 seed 库上直接跑并打印 JSON，
作为可录制的原始侧契约（process-only，非生产 transport）。

    ZKC_PG_DSN=... python3 scripts/zkc_review_queue.py --json --limit 50 [--action classify]

契约（handler 原样）：{"items":[{"id","node_id","action","reason","resolved":false,"created_at"}...],
                     "count":int, "include_resolved":false}
created_at 由 handler 的 datetime.isoformat() 产出（aware UTC ⇒ ...+00:00）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zkc.mcp.handlers import build_handlers
from zkc.repository import get_storage


def main() -> None:
    ap = argparse.ArgumentParser(description="ZKC review_queue handler 契约（JSON）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--storage", default=None)
    ap.add_argument("--mode", default="list", choices=["list", "resolve"])
    ap.add_argument("--action", default=None)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--item-id", dest="item_id", default=None)
    ap.add_argument("--attribution", default="")
    args = ap.parse_args()

    store = get_storage(args.storage or os.environ.get("ZKC_STORAGE", "pg"))
    handlers = build_handlers(
        store_provider=lambda: store,
        routing_provider=lambda: (None, None, True),
        allow_private_claims=False,
    )
    if args.mode == "resolve":
        # resolve-then-list: the write is not captured by dump.sh (review_queue not dumped), so
        # re-listing open items after resolve makes the persistence observable in stdout for replay.
        try:
            result = handlers["zkc_review_queue_resolve"]({
                "item_id": args.item_id, "attribution": args.attribution,
            })
            resolve = {"ok": True, "value": result}
        except ValueError as exc:
            resolve = {"ok": False, "error": f"ValueError: {exc}"}
        open_after = handlers["zkc_review_queue_list"]({"limit": args.limit})
        out = {"resolve": resolve, "remaining_ids": [it["id"] for it in open_after["items"]]}
    else:
        arguments = {"limit": args.limit}
        if args.action:
            arguments["action"] = args.action
        out = handlers["zkc_review_queue_list"](arguments)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

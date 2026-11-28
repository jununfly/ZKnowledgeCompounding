"""ZKC · MCP `zkc_query` handler 的对外契约入口（query 工具的 A 路径原始侧）。

`zkc_query` 是 stdio JSON-RPC tool，不经 `zkc` CLI，故无 app-record 入口。本脚本把 handler 的
业务返回体（`build_handlers(...)["zkc_query"]`）在给定 seed 库上直接跑并打印 JSON，作为可录制
的原始侧契约（与 zkc_search.py 同理：process-only 契约入口，非生产 transport）。transport 信封
（`result_response` 等）已在 `transport-rs`，本入口只覆盖 handler 的业务载荷。

    ZKC_PG_DSN=... python3 scripts/zkc_query.py --json --query shared --limit 20

契约（deterministic，sqlx A 路径须逐字节复现）：
  {"items":[{"node_id","title","track","decay_score","source","evidence_refs":[...]}...],
   "count":int, "scope":str, "degraded":bool, "privacy":str}

刻意约束：
  - 无 encoder ⇒ search 走结构化路径 ⇒ degraded=false、hits 来自 pg.py::search。
  - decay_score 用 round(...,3)（handler 原样，非 zkc_search 的 4）。
  - evidence_refs = sorted(set(claim.evidence_refs for claims where node_id ∈ refs))，按 uuid 文本升序。
  - private_claims 未授权 → 返回 denied 体（不触库）。本入口默认 allow_private_claims=False。
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
    ap = argparse.ArgumentParser(description="ZKC zkc_query handler 契约（JSON）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--storage", default=None)
    ap.add_argument("--query", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--scope", default="public")
    args = ap.parse_args()

    store = get_storage(args.storage or os.environ.get("ZKC_STORAGE", "pg"))
    handlers = build_handlers(
        store_provider=lambda: store,
        routing_provider=lambda: (None, None, True),
        allow_private_claims=False,
    )
    out = handlers["zkc_query"]({"query": args.query, "limit": args.limit, "scope": args.scope})
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

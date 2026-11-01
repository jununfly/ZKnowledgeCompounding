#!/usr/bin/env python3
"""ZKC · 蒸馏算子真实 LLM dogfood（roadmap 1-5-6 验证器）。

用途：在本机起 Ollama 后手动执行，验证 1-5-6 结构化接线全链路：
  zkc.llm.make_distill_llm（铁律①②③内置）
    → zkc.distill.distill_node（JSON 契约解析 + 校验重试）
    → zkc.expiry.apply_distill（落 claim + llm_call_score）。

无 Ollama 环境执行 → 打印 SKIP 并以 0 退出（非失败）。

用法：
    python3 scripts/dogfood_distill.py [ollama_url] [model]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc import expiry as E  # noqa: E402
from zkc.llm import DEFAULT_DISTILL_MODEL, make_distill_llm, ollama_reachable  # noqa: E402
from zkc.repository import get_storage  # noqa: E402

DEFAULT_URL = "http://localhost:11434"

# 复用 dogfood_cross_source 语料形态：3 条关联中文动态条目（同一项目经历的不同侧面）
SOURCES = [
    ("鉴权返工", "把鉴权逻辑放在客户端做，被安全评审整体打回，服务端全部重做，返工两周。"),
    ("临时绕过", "评审提出的临时绕过方案最后都变成长期负担，没有任何人主动回头拆。"),
    ("压测前置", "把连接池压测前置到设计阶段后，上线前的瓶颈改动成本接近于零。"),
]


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DISTILL_MODEL

    if not ollama_reachable(url):
        print(f"SKIP: ollama unreachable ({url})")
        return 0
    names = [m["name"] for m in json.loads(
        urllib.request.urlopen(url + "/api/tags", timeout=3).read()).get("models", [])]
    if model not in names:
        print(f"SKIP: model {model!r} not in ollama ({names})")
        return 0

    llm = make_distill_llm(url, model)

    # ---- 真实数据流：node 落库 → distill_node(真实 LLM) → apply_distill 落 claim + score
    store = get_storage("memory")
    node_ids = []
    for title, content in SOURCES:
        from zkc.repository.models import Node
        n = store.nodes.save(Node(track="dynamic", title=title, content=content))
        node_ids.append(n.id)
    target = node_ids[0]

    from zkc import distill as D
    t0 = time.perf_counter()
    try:
        result = D.distill_node(
            target, [(nid, store.nodes.get(nid).title + "：" + (store.nodes.get(nid).content or ""))
                     for nid in node_ids],
            llm,
            system_prompt="将以下项目经历材料蒸馏为 1-3 条去繁后的元认知方法论结论；"
                          "每条结论必须在 citations 数组中引用支撑它的来源节点 uuid。",
        )
        distill_wall = time.perf_counter() - t0
    except D.DistillationError as e:
        print(f"DISTILL GATE: FAIL ({e})")
        return 1

    res = E.apply_distill(store, target,
                          lambda s, nid: result, model=getattr(llm, "model_name", None))

    print("=== dogfood distill (real Ollama) ===")
    print(f"model={model}  wall={distill_wall:.1f}s  attempts={result.attempts}")
    for c in result.claims:
        print(f"  - [{c.topic}] {c.text!r} <- {[str(u)[:8] for u in c.reverse_links]}")
    claims = store.claims.list_by_evidence(target)
    rows = store.scores.list_recent()
    print(f"applied={res['applied']}  claims_saved={len(claims)}  "
          f"score_rows={len(rows)}")
    if rows:
        r = rows[0]
        print(f"score: parse_ok={r.parse_ok} latency={r.latency_ms:.0f}ms "
              f"attempts={r.attempts} n_claims={r.n_claims} model={r.model}")
    gate = res["applied"] and len(claims) >= 1 and len(rows) == 1
    print(f"DISTILL GATE: {'PASS' if gate else 'FAIL'}")
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())

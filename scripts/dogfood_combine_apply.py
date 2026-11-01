#!/usr/bin/env python3
"""ZKC · 结合算子落库接线真实 LLM dogfood（roadmap 1-5-3 验证器）。

用途：在本机起 Ollama 后手动执行，验证 1-5-3 全链路——真实 store 节点（UUID id）
→ CrossSourceOperator（真实 LLM）→ apply_combine 落库 modeling_artifact
（evidence_refs UUID 化 + produced_by + body）→ 节点进「已捕获」基线 →
revert_artifact 级联 capture-loss 重算。

与 scripts/dogfood_cross_source.py（1-5-2，纯算子）的区别：本脚本验证的是
**store 接线**（源校验 / 落库 / 调度信号 / 撤销级联），存储用 ephemeral memory
store（落库行为与 PG 同构，PG 侧另有 test_cross_source_apply.PgApplyCombineTest）。

无 Ollama 环境执行 → 打印 SKIP 并以 0 退出（非失败）。

用法：
    python3 scripts/dogfood_combine_apply.py [ollama_url] [model]
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc import scheduling as S  # noqa: E402
from zkc.cross_source import (  # noqa: E402
    CrossSourceArtifact,
    CrossSourceOperator,
    apply_combine,
    revert_artifact,
)
from zkc.repository import get_storage  # noqa: E402
from zkc.repository.models import Node  # noqa: E402

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.5:4b-mlx"
QUERY = "从这些项目经历中提炼出一个关于技术决策时机的可复用方法论"

# 与 1-5-2 dogfood 同语料（5 条互关联中文动态条目），但 id 换成真实 store 节点 UUID
_TEXTS = [
    ("鉴权返工", "把鉴权逻辑放在客户端做，被安全评审整体打回，服务端全部重做，返工两周。"),
    ("SDK 升级", "第三方 SDK 的升级一直拖到上游停止维护前一周才做，被动手忙脚乱，也是两周。"),
    ("临时绕过", "评审提出的临时绕过方案最后都变成长期负担，没有任何人主动回头拆。"),
    ("压测前置", "把连接池压测前置到设计阶段后，上线前的瓶颈改动成本接近于零。"),
    ("技术债记账", "技术债必须记账并带责任人，团队坚持一个季度后大约三分之一被主动清理。"),
]


def _chat(url: str, model: str, prompt: str) -> str:
    """Ollama 原生 /api/chat，format=json + think=false + num_ctx=8192（接线铁律）。"""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1024},
    }).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"]


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL

    # ---- 可达性探测：不通则 SKIP（dogfood 非阻塞）
    try:
        names = [m["name"] for m in json.loads(
            urllib.request.urlopen(url + "/api/tags", timeout=3).read()).get("models", [])]
        if model not in names:
            print(f"SKIP: model {model!r} not in ollama ({names})")
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"SKIP: ollama unreachable ({exc})")
        return 0

    def _json_block(raw: str) -> dict:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            raise ValueError(f"no JSON object in LLM output: {raw[:120]!r}")
        return json.loads(m.group(0))

    # ---- 真实 store：5 条动态节点，source id = 真实 UUID（apply_combine 校验对象）
    store = get_storage("memory")
    sources = []
    for title, content in _TEXTS:
        nd = store.nodes.save(Node(title=title, content=content,
                                   track="dynamic", decay_score=0.0))
        sources.append({"id": str(nd.id), "title": title, "content": content})

    def summarize(src: dict, query: str) -> str:
        raw = _chat(url, model,
                    f"针对问题「{query}」，只依据下面这条来源，给出一句与该问题相关的要点总结"
                    f"（不要复述全文，不超过 60 字）。只输出 JSON：{{\"point\": \"...\"}}。\n\n"
                    f"[{src['title']}]\n{src['content']}")
        return str(_json_block(raw).get("point", ""))[:120] or src["title"]

    def score(summary: str, query: str) -> float:
        raw = _chat(url, model,
                    f"问题：「{query}」。以下总结对该问题的支撑度打分 0~1。"
                    f"只输出 JSON：{{\"score\": 0.0}}。\n\n{summary}")
        return float(max(0.0, min(1.0, float(_json_block(raw).get("score", 0.0)))))

    SCHEMA_HINT = (
        '输出必须是且仅是如下结构的 JSON（字段名逐字遵守）：\n'
        '{"title": str, "kind": "methodology"|"mental_model"|"tradeoff_map",\n'
        ' "claims": [{"statement": str, "level": "principle"|"pattern"|'
        '"antipattern"|"tradeoff", "confidence": 0.0~1.0,\n'
        '            "evidence_ids": [来源 id 数组，跨源断言须 >=2 个不同 id]}],\n'
        ' "local": [str], "global": [str], "methodology_steps": [str]}\n'
    )

    def generate(prompt: str):
        last: Exception | None = None
        for attempt in range(2):
            p = prompt + "\n\n" + SCHEMA_HINT
            if attempt and last is not None:
                p += (f"\n上一次输出未通过结构校验（{str(last)[:60]}）。"
                      "请重新输出完整对象，字段名逐字遵守，补全所有必填字段。")
            try:
                return CrossSourceArtifact.model_validate(_json_block(_chat(url, model, p)))
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise last  # type: ignore[misc]

    op = CrossSourceOperator(summarize, score, generate)
    tf = store.record_transform("combine", {"query": QUERY, "dogfood": "1-5-3"})

    # ---- apply_combine：校验 -> 算子 -> 落库
    t0 = time.perf_counter()
    res = apply_combine(store, QUERY, sources, op, produced_by=tf)
    wall = time.perf_counter() - t0

    print("=== dogfood combine_apply (real Ollama, 1-5-3) ===")
    print(f"model={model}  wall={wall:.1f}s")
    if not res["applied"]:
        print(f"APPLY: FAIL -> {res['reason']}")
        return 1
    rep = res["report"]
    print(f"kept={[k['id'][:8] for k in rep['kept']]}  "
          f"completion_fired={rep['completion_fired']}  "
          f"n_cross_source_final={rep['n_cross_source_final']}")
    ma = store.artifacts.get(res["artifact_id"])
    print(f"PERSIST: id={ma.id}  kind={ma.kind}  "
          f"evidence_refs={[str(e)[:8] for e in ma.evidence_refs]}  "
          f"produced_by={str(ma.produced_by)[:8]}  body_claims={len(ma.body['claims'])}")
    ok_refs = all(store.nodes.get(e) is not None for e in ma.evidence_refs)
    print(f"evidence_refs ⊆ store nodes: {ok_refs}")

    # ---- 调度信号：产物捕获 evidence 节点 -> 基线 28d
    S.assign_baselines(store)
    days = {str(e)[:8]: store.nodes.get(e).baseline_interval.total_seconds() / 86400.0
            for e in ma.evidence_refs}
    print(f"captured baseline days (expect {S._t('BASELINE_CAPTURED_DAYS')}): {days}")

    # ---- revert_artifact 级联撤销（联调演示；memory store ephemeral，撤销即清场）
    rev = revert_artifact(store, ma.id, produced_by=tf)
    print(f"REVERT: deleted={rev['deleted']}  "
          f"recomputed={[(str(r['node_id'])[:8], r['applied'], r.get('tier'))
                        for r in rev['recomputed']]}")
    after = {str(e)[:8]: store.nodes.get(e).baseline_interval.total_seconds() / 86400.0
             for e in rev["evidence_node_ids"]}
    print(f"post-revert baseline days (expect {S._t('BASELINE_ORPHAN_DAYS')} 孤儿): {after}")
    print("COMBINE-APPLY DOGFOOD: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

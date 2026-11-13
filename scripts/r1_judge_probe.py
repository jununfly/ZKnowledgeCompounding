#!/usr/bin/env python
"""R1 judge 复测探针（忠实度 judge 探针）：9B GGUF + Ollama 铁律下自动忠实度判定是否可行。

背景：spike-13b 对 9B 的否决（~6min/条 + 不产 JSON）是在 9b-mlx @ 原生 256K ctx
下测的——与 R13 同源伪影。本探针用 qwen3.5:9b GGUF + 铁律全套
（原生 /api/chat + format:json、think=false、num_ctx=8192、num_predict=2048）
复测 zkc/faithfulness.py 现成 judge seam（零改动）。

判据（忠实度 judge 结论已落盘）：
  4 条合成 claim（2 supported / 1 unsupported / 1 contradicted）对一篇真实语料
  —— JSON 全部可解析（4/4）且判定与预期一致（≥3/4）且延迟 ≤60s/条
  → 「judge 可选启用」实证成立（默认仍 HITL，启用开关另行拍板）。

用法：python scripts/r1_judge_probe.py [--model qwen3.5:9b]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc.faithfulness import (  # noqa: E402
    JUDGE_SYSTEM,
    aggregate,
    build_judge_prompt,
    parse_judgment,
)
from zkc.llm import DEFAULT_OLLAMA_URL, ollama_chat  # noqa: E402
from zkc.repository.connection import connect  # noqa: E402

SOURCE_PREFIX = "29526b8b"  # Meta-Harness（真实语料，1313 字）

# 4 条合成 claim：expected ∈ {supported, unsupported, contradicted}
CLAIMS = [
    ("Meta-Harness 是斯坦福 IRIS 实验室 Yoonho Lee 团队提出的开源框架，"
     "核心想法是让 AI 自己优化自己的工作流程。", "supported"),
    ("实验发现只给摘要的方法（如 TTT-Discover、Best-of-N）在 TerminalBench-2 上"
     "表现明显更差，AI 平均要阅读 82 份历史文件才能找到真正的失败模式。", "supported"),
    ("Meta-Harness 在 TerminalBench-2 上的最终性能达到 75%，远超所有已报告的方法。",
     "unsupported"),
    ("Meta-Harness 在 TerminalBench-2 上的表现不如其他已报告的 Claude Haiku 4.5 套件。",
     "contradicted"),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="R1 judge 复测（9B GGUF + 铁律）")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--num-predict", type=int, default=2048)
    args = ap.parse_args(argv)

    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "select id::text, title, content from node where id::text like %s",
        (SOURCE_PREFIX + "%",),
    )
    nid, title, content = cur.fetchone()
    sources = [{"id": "s1", "title": title, "content": content}]
    print(f"源文档: {title}（{len(content)} 字）; judge 模型: {args.model}")

    rows = []
    for claim, expected in CLAIMS:
        prompt = JUDGE_SYSTEM + "\n\n" + build_judge_prompt(claim, sources)
        t0 = time.time()
        try:
            raw = ollama_chat(
                DEFAULT_OLLAMA_URL, args.model, prompt,
                json_mode=True, num_predict=args.num_predict, timeout=300,
            )
            wall = time.time() - t0
            j = parse_judgment(raw)
            verdict = aggregate(j.atomic_facts) or j.overall
            ok = verdict == expected
            rows.append(dict(expected=expected, verdict=verdict, ok=ok,
                             wall_s=round(wall, 1), n_facts=len(j.atomic_facts),
                             json_ok=True))
            print(f"  [{'✓' if ok else '✗'}] expect={expected} got={verdict} "
                  f"{wall:.1f}s facts={len(j.atomic_facts)}")
        except Exception as e:  # noqa: BLE001 — 探针要记录全部失败形态
            wall = time.time() - t0
            rows.append(dict(expected=expected, verdict=None, ok=False,
                             wall_s=round(wall, 1), json_ok=False, error=str(e)[:120]))
            print(f"  [✗] expect={expected} 解析失败 {wall:.1f}s: {str(e)[:120]}")

    n_json = sum(r["json_ok"] for r in rows)
    n_ok = sum(r["ok"] for r in rows)
    max_wall = max(r["wall_s"] for r in rows)
    passed = n_json == len(CLAIMS) and n_ok >= 3 and max_wall <= 60
    summary = dict(
        model=args.model, n_claims=len(CLAIMS), json_ok=n_json,
        verdict_correct=n_ok, max_wall_s=max_wall,
        passed=passed,
        detail=rows,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"判定: {'合格 → judge 可选启用实证成立（默认仍 HITL）' if passed else '不合格 → 维持 MVP HITL 结论'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

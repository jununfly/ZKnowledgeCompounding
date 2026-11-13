#!/usr/bin/env python
"""ZKC · 词法路由冷启动语料导出（交付物）。

从真实 PG 读取已定轨节点的 (title, content, track)，按与增量回灌
（`resolve_classify` 的 `title + " " + content`）**完全一致**的文本格式，
生成 `data/lexical_corpus.json`，使 LexicalRouter 冷启动即有真实标注样本。

治理铁律：
- 仅导出**真实已定轨**节点（track ∈ {static, dynamic}）。未定轨（unrouted）一律跳过，
  绝不伪造 vague 标签或编造样本 —— corpus-derived 必须是真实标注，不可灌入假数据。
- 本脚本只负责「导出真实语料」；门槛推导（corpus-derived）由 LexicalRouter.fit()
  自动完成，且**绝不写回** tuning 的 CALIBRATED（见 tuning.ROUTING_LEXICAL_*）。
- 升 CALIBRATED 须走 tuning.calibrate() 门禁（≥14d 埋点 + ≥3 饱和日），不在此脚本 scope。

用法：
    python scripts/export_lexical_corpus.py [--path data/lexical_corpus.json]
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from zkc.repository.connection import get_dsn  # noqa: E402
from zkc import routing  # noqa: E402


def build_examples(rows: list[dict]) -> list[tuple[str, str]]:
    """把 PG 行投影成 (text, label)；与 resolve_classify 回灌格式严格一致。

    text = title + (" " + content if content else "")
    只保留真实已定轨（static/dynamic）；unrouted/其它一律丢弃（不编造 vague）。
    """
    examples: list[tuple[str, str]] = []
    for row in rows:
        track = (row.get("track") or "").strip().lower()
        if track not in ("static", "dynamic"):
            continue
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        text = title + (f" {content}" if content else "")
        if not text:
            continue
        examples.append((text, track))
    return examples


def main() -> int:
    ap = argparse.ArgumentParser(description="导出真实词法路由冷启动语料")
    ap.add_argument(
        "--path",
        default=os.path.join(ROOT, "data", "lexical_corpus.json"),
        help="输出语料路径（默认 data/lexical_corpus.json）",
    )
    args = ap.parse_args()

    import psycopg  # 懒加载：无 DB 环境不强制依赖
    from psycopg.rows import dict_row

    dsn = get_dsn()
    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        cur = conn.cursor()
        cur.execute("SELECT title, content, track FROM node")
        rows = cur.fetchall()
    finally:
        conn.close()

    examples = build_examples(rows)
    routing.save_lexical_corpus(args.path, examples)

    # 真实样本统计 + 诚实预测 fit 后的状态（不写回 tuning）
    counts: dict[str, int] = {}
    for _, label in examples:
        counts[label] = counts.get(label, 0) + 1

    router = routing.LexicalRouter()  # 默认 seed=0.5，未显式指定
    router.fit(examples)

    print(f"语料已写出：{args.path}")
    print(f"  总行数（真实已定轨）：{len(examples)}")
    for label in ("static", "dynamic"):
        n = counts.get(label, 0)
        flag = "✓≥3" if n >= 3 else "✗<3（质心缺失）"
        print(f"  {label}: {n}  {flag}")
    print(f"  fitted(有任一质心): {router.fitted}")
    print(f"  gate_source: {router.gate_source}  gate={router.gate:.4f}")
    if router.gate_source == "seed":
        print("  说明：static/dynamic 未同时 ≥3 → 自动推导门槛回退 seed（corpus-derived 未激活）。")
        print("        需 zj 真实积累 ≥3 个 static 样本后，fit() 才会推导出 corpus-derived 门槛。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

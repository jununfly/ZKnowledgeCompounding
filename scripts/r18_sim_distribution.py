#!/usr/bin/env python
"""R18 / D4：4096 列余弦相似度分布（阈值重校准的可核实依据）。

复用 r18_recall_eval.py 的语料加载与编码函数，产出两类真实分布：
  1. node ↔ node：60 条 4096 维向量两两余弦，对应 discover_higher_dim 的近邻尺度；
  2. query ↔ node：32 条中文 query 对全库余弦，作为召回尺度的交叉参照。

只读：不写库、不改 node；结果只落到 --out-dir 指定的证据文件。
结论供人对照，**绝不自动写回 tuning.REGISTRY 或伪装成 CALIBRATED**。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import r18_recall_eval as ev  # noqa: E402
from zkc.repository.connection import connect  # noqa: E402

MODEL = "qwen3-embedding:latest"
COLUMN = "embedding_4096"


def summarize(values: list[float]) -> dict:
    s = sorted(values)
    if not s:
        return {"n": 0}

    def q(p: float) -> float:
        idx = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
        return round(s[idx], 4)

    return {
        "n": len(s), "min": round(s[0], 4), "p05": q(0.05), "p25": q(0.25),
        "p50": q(0.50), "p75": q(0.75), "p90": q(0.90), "p95": q(0.95),
        "p99": q(0.99), "max": round(s[-1], 4),
        "mean": round(sum(s) / len(s), 4),
    }


def percentile_of(values: list[float], threshold: float) -> float:
    """threshold 在分布中处于第几百分位（即有多少比例低于它）。"""
    if not values:
        return 0.0
    return round(100.0 * sum(v < threshold for v in values) / len(values), 2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="4096 列余弦相似度分布")
    ap.add_argument("--dsn", default=None)
    ap.add_argument("--out-dir", default=str(_HERE.parent / "docs" / "evidence"))
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args(argv)

    queries = json.loads(ev.DEFAULT_QUERIES.read_text())["queries"]
    conn = connect(args.dsn)
    corpus = ev.load_corpus(conn, column=COLUMN)
    queries = ev.resolve_targets(queries, corpus)

    # 1) node ↔ node（discover_higher_dim 的真实比较尺度）
    nn = []
    for i, a in enumerate(corpus):
        for b in corpus[i + 1:]:
            nn.append(ev.cosine(a["stored_vec"], b["stored_vec"]))
    nn_stats = summarize(nn)

    # 2) query ↔ node（中文召回尺度）
    qvecs = ev.ollama_embed([q["query"] for q in queries], args.model, batch=8)
    qn, positives, negatives = [], [], []
    for item, qv in zip(queries, qvecs):
        for c in corpus:
            sim = ev.cosine(qv, c["stored_vec"])
            qn.append(sim)
            (positives if c["id"] == item["target"] else negatives).append(sim)

    thresholds = [0.50, 0.60, 0.65, 0.70, 0.75, 0.80]
    candidates = []
    for t in thresholds:
        tp = sum(v >= t for v in positives)
        fp = sum(v >= t for v in negatives)
        nn_kept = sum(v >= t for v in nn)
        candidates.append({
            "threshold": t,
            "node_node_pairs_at_or_above": nn_kept,
            "node_node_pair_ratio": round(nn_kept / len(nn), 4) if nn else 0.0,
            "query_positives_at_or_above": tp,
            "query_negatives_at_or_above": fp,
            "query_precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
            "query_recall": round(tp / len(positives), 4) if positives else None,
            "threshold_percentile_in_node_node": percentile_of(nn, t),
        })

    result = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "column": COLUMN,
        "model": args.model,
        "corpus_size": len(corpus),
        "n_queries": len(queries),
        "node_node": nn_stats,
        "query_node": summarize(qn),
        "query_positive": summarize(positives),
        "query_negative": summarize(negatives),
        "threshold_candidates": candidates,
        "current_placeholder_threshold": 0.7,
        "note": (
            "node↔node 分布对应 discover_higher_dim 的近邻尺度；query↔node 仅为召回交叉参照。"
            "本脚本只读，不写 tuning.REGISTRY，不把任何 source 标成 CALIBRATED。"
        ),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "r18-4096-sim-distribution.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    lines = [
        "# R18 4096 列余弦相似度分布（D4 阈值重校准依据）",
        "",
        f"- 采集时刻：{result['as_of']}",
        f"- 命令：`python scripts/r18_sim_distribution.py`",
        f"- 列 / 模型：`{COLUMN}` / `{args.model}`；语料 {len(corpus)} 条，query {len(queries)} 条",
        f"- 数据来源：真实 PG（`node.{COLUMN}` 已回填列）+ 本地 Ollama `/api/embed`；脚本只读，不写库。",
        "",
        "## node ↔ node（`discover_higher_dim` 的真实比较尺度）",
        "",
        "| n | min | p05 | p25 | p50 | p75 | p90 | p95 | p99 | max | mean |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        "| " + " | ".join(str(nn_stats[k]) for k in
                         ("n", "min", "p05", "p25", "p50", "p75", "p90",
                          "p95", "p99", "max", "mean")) + " |",
        "",
        "## 候选阈值在真实分布上的表现",
        "",
        "| 阈值 | node-node 命中对数 | 占比 | 阈值所处百分位 | query 正例≥阈值 | query 负例≥阈值 | precision | recall |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in candidates:
        lines.append(
            f"| {c['threshold']:.2f} | {c['node_node_pairs_at_or_above']} | "
            f"{c['node_node_pair_ratio']} | {c['threshold_percentile_in_node_node']}% | "
            f"{c['query_positives_at_or_above']} | {c['query_negatives_at_or_above']} | "
            f"{c['query_precision']} | {c['query_recall']} |"
        )
    lines += [
        "",
        "## 口径限制（诚实声明）",
        "",
        "- node↔node 是「任意两条语料」的相似度，不等于「语义上应被聚合」的正例标注；"
        "上表的 precision / recall 只针对 query↔node 召回任务，不能直接当作聚合质量的标注率。",
        "- 现有 `CONTEXT_HIGHER_DIM_SIM_THRESHOLD=0.7` 的 source 是 `PLACEHOLDER`。"
        "本分布只提供重校准依据，**不自动写回 tuning，也不把 source 升级为 CALIBRATED**"
        "（校准门禁需 ≥14 天埋点 + ≥3 饱和日）。",
        "",
    ]
    (out_dir / "r18-4096-sim-distribution.md").write_text("\n".join(lines),
                                                          encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {out_dir / 'r18-4096-sim-distribution.md'}")
    print(f"node↔node: {nn_stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

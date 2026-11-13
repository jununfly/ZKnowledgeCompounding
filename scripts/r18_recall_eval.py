#!/usr/bin/env python
"""R18 中文检索召回质量评测（R18 实测）。

对 zkc_dev 真实语料（导入的 61 条 AI-Coding 文档）测 embedding 候选召回质量。
评测集：scripts/r18_eval_queries.json（32 条人工改写中文 query，禁止照抄标题）。

判据（R18 中文召回实测结论已落盘）：
  Recall@10 >= 0.85 且 MRR >= 0.5 → 合格（R18 关停，实测数为证据）；
  不合格 → 同查询集跑 qwen3-embedding 4096d 对比，仅当 4096 达标且显著优于 768
  才开加列路径。

两种模式：
  默认（生产模式）：query 向量 vs 库内**已存** node.embedding（/browse 真实数据流）。
  --reembed-docs    用指定模型重编全部文档向量（模拟「加列 4096」后的对比基线）。

用法：
  python scripts/r18_recall_eval.py                          # nomic 768d 生产模式
  python scripts/r18_recall_eval.py --models qwen3-embedding --reembed-docs

只读评测：不写库、不改 node。退出码恒 0（度量探针，判定由人/roadmap 对照执行）。
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc.repository.connection import connect  # noqa: E402

OLLAMA_URL = "http://localhost:11434"
DEFAULT_QUERIES = Path(__file__).resolve().parent / "r18_eval_queries.json"

# 本模块专用 no-proxy opener（localhost 绕过 Clash，encoder.py 同款教训）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ollama_embed(texts: list[str], model: str, batch: int = 8) -> list[list[float]]:
    """原生 /api/embed 批量编码，不做维度校验（评测需支持 768/4096 两种模型）。

    分批请求：61 篇长文（最长 20K+ 字）单请求会超时。
    """
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        body = json.dumps({"model": model, "input": chunk}).encode()
        req = urllib.request.Request(
            OLLAMA_URL.rstrip("/") + "/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with _OPENER.open(req, timeout=600) as resp:
            data = json.loads(resp.read())
        vecs = data.get("embeddings")
        if not isinstance(vecs, list) or len(vecs) != len(chunk):
            raise RuntimeError(f"embed 返回条数不符: {model} batch@{i}")
        out.extend(list(map(float, v)) for v in vecs)
    return out


def load_corpus(conn, column: str = "embedding") -> list[dict]:
    """拉取全部带指定 embedding 列的节点（生产数据流：比较对象是**已存**列向量）。"""
    if column not in ("embedding", "embedding_4096"):
        raise SystemExit(f"invalid column: {column}")
    cur = conn.cursor()
    cur.execute(
        f"select id::text, title, coalesce(content,''), {column}::text "
        f"from node where {column} is not null"
    )
    rows = cur.fetchall()
    out = []
    for nid, title, content, emb in rows:
        vec = [float(x) for x in emb.strip("[]").split(",")]
        out.append({"id": nid, "title": title, "content": content, "stored_vec": vec})
    return out


def parse_vec(s: str) -> list[float]:
    return [float(x) for x in s.strip("[]").split(",")]


def resolve_targets(queries: list[dict], corpus: list[dict]) -> list[dict]:
    """把 8 位 id 前缀解析成全 id，要求唯一命中。"""
    resolved = []
    for item in queries:
        pref = item["target_id"]
        hits = [c for c in corpus if c["id"].startswith(pref)]
        if len(hits) != 1:
            raise SystemExit(f"target 前缀 {pref} 命中 {len(hits)} 条（要求唯一）")
        resolved.append({**item, "target": hits[0]["id"]})
    return resolved


def leakage_check(queries: list[dict], corpus: list[dict]) -> list[str]:
    """查 query 与目标标题的最长公共子串，>6 字符视为疑似照抄，返回警告列表。"""
    title_by_id = {c["id"]: c["title"] for c in corpus}
    warns = []
    for item in queries:
        t = title_by_id[item["target"]]
        m = difflib.SequenceMatcher(None, item["query"], t).find_longest_match(
            0, len(item["query"]), 0, len(t)
        )
        if m.size > 6:
            warns.append(
                f"疑似照抄: [{item['target_id']}] query 与标题公共子串 {m.size} 字: "
                f"「{item['query'][m.a:m.a + m.size]}」"
            )
    return warns


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def run_eval(
    queries: list[dict],
    corpus: list[dict],
    model: str,
    doc_vecs: dict[str, list[float]],
) -> dict:
    """编码 query → 全库余弦排序 → 指标。"""
    qvecs = ollama_embed([q["query"] for q in queries], model)
    rows = []
    hits1 = hits5 = hits10 = 0
    rr_sum = 0.0
    ranks = []
    for item, qv in zip(queries, qvecs):
        sims = [(c["id"], cosine(qv, doc_vecs[c["id"]])) for c in corpus]
        sims.sort(key=lambda x: -x[1])
        rank = next(i + 1 for i, (nid, _) in enumerate(sims) if nid == item["target"])
        top10 = sims[:10]
        rows.append(
            {
                "target_id": item["target_id"],
                "target_title": next(
                    c["title"] for c in corpus if c["id"] == item["target"]
                ),
                "rank": rank,
                "target_sim": next(s for nid, s in sims if nid == item["target"]),
                "top1_title": next(c["title"] for c in corpus if c["id"] == top10[0][0]),
            }
        )
        ranks.append(rank)
        if rank <= 1:
            hits1 += 1
        if rank <= 5:
            hits5 += 1
        if rank <= 10:
            hits10 += 1
        rr_sum += 1.0 / rank
    n = len(queries)
    return {
        "model": model,
        "corpus_size": len(corpus),
        "n_queries": n,
        "recall@1": hits1 / n,
        "recall@5": hits5 / n,
        "recall@10": hits10 / n,
        "mrr": rr_sum / n,
        "median_rank": sorted(ranks)[n // 2],
        "per_query": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="R18 中文召回评测")
    ap.add_argument("--queries", default=str(DEFAULT_QUERIES))
    ap.add_argument("--dsn", default=None)
    ap.add_argument(
        "--models", default="nomic-embed-text",
        help="逗号分隔的评测模型（默认生产模型 nomic-embed-text）",
    )
    ap.add_argument(
        "--reembed-docs", action="store_true",
        help="文档向量也用被测模型现算（模拟加列后的对比基线）；默认用库内已存向量",
    )
    ap.add_argument(
        "--column", default="embedding", choices=["embedding", "embedding_4096"],
        help="生产模式读取的向量列（双列共存后可对 embedding_4096 复测）",
    )
    args = ap.parse_args(argv)

    queries = json.loads(Path(args.queries).read_text())["queries"]
    conn = connect(args.dsn)
    corpus = load_corpus(conn, column=args.column)
    print(f"语料: {len(corpus)} 条带 embedding 节点; 评测集: {len(queries)} 条 query")

    queries = resolve_targets(queries, corpus)
    warns = leakage_check(queries, corpus)
    for w in warns:
        print(f"  [泄漏警告] {w}")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    results = {}
    for model in models:
        if args.reembed_docs:
            print(f"[{model}] 重编 {len(corpus)} 条文档向量 ...")
            vecs = ollama_embed([c["content"] for c in corpus], model)
            doc_vecs = {c["id"]: v for c, v in zip(corpus, vecs)}
        else:
            doc_vecs = {c["id"]: c["stored_vec"] for c in corpus}
        print(f"[{model}] 编码 {len(queries)} 条 query 并排序 ...")
        r = run_eval(queries, corpus, model, doc_vecs)
        results[model] = r
        print(
            f"\n=== {model} ===\n"
            f"  Recall@1={r['recall@1']:.3f}  Recall@5={r['recall@5']:.3f}  "
            f"Recall@10={r['recall@10']:.3f}\n"
            f"  MRR={r['mrr']:.3f}  median_rank={r['median_rank']}\n"
        )
        misses = [row for row in r["per_query"] if row["rank"] > 10]
        if misses:
            print(f"  未进 Top10 的 query（{len(misses)} 条）:")
            for row in misses:
                print(
                    f"    [{row['target_id']}] rank={row['rank']} 目标=「{row['target_title']}」"
                    f" sim={row['target_sim']:.3f} top1=「{row['top1_title']}」"
                )
        print()

    ok = {
        m: (r["recall@10"] >= 0.85 and r["mrr"] >= 0.5) for m, r in results.items()
    }
    for m, passed in ok.items():
        print(f"判定 [{m}]: {'合格（Recall@10>=0.85 且 MRR>=0.5）' if passed else '不合格'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

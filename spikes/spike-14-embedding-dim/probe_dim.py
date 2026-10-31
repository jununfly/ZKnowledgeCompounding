"""Spike 14 · embedding 编码器定维探测（关闭 R16）

ZKC 决策背景：架构 §5 原写 `vector(1024)` 是 spike 01 验证 DDL 可执行性的占位，
与真实编码器不符。换编码器 = 重建索引，所以必须在 P1 迁移前定死。

本脚本只回答三件事（不重复 spike 02/03 已做过的分流质量评测）：
  1. 每个候选模型的**真实向量维度**（决定 `vector(N)` 的 N）
  2. 单条与批量的**延迟**（决定捕获/复审链路的响应预算）
  3. 向量是否**已归一化**（决定用 cosine 还是需自行 L2 归一化）

用法：python probe_dim.py
"""
from __future__ import annotations

import json
import math
import statistics
import time
import urllib.request

# 关键：本机 Clash 代理会让 localhost 无限挂起，必须绕过（见实施计划 §8.3）
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(opener)

OLLAMA = "http://localhost:11434"
MODELS = ["nomic-embed-text:latest", "qwen3-embedding:latest"]

PROBE_TEXT = "下周三前把 ZKC 的 review_interval 三层规则回填到架构文档。"
BATCH = [f"动态条目样本 {i}：关于项目 A 的临时决策与待办。" for i in range(32)]


def embed(model: str, texts: list[str], timeout: int = 300):
    payload = json.dumps({"model": model, "input": list(texts)}).encode()
    req = urllib.request.Request(
        OLLAMA + "/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["embeddings"], time.time() - t0


def main() -> int:
    results = {}
    for model in MODELS:
        try:
            vecs, t_single = embed(model, [PROBE_TEXT])
            dim = len(vecs[0])
            norm = math.sqrt(sum(v * v for v in vecs[0]))

            # 预热后再测批量（首次调用含模型加载时间，不具代表性）
            vecs, t_warm = embed(model, [PROBE_TEXT])
            _, t_batch = embed(model, BATCH)
            per_item = t_batch / len(BATCH)

            results[model] = {
                "dim": dim,
                "l2_norm": round(norm, 4),
                "cold_s": round(t_single, 3),
                "warm_single_s": round(t_warm, 3),
                "batch32_s": round(t_batch, 3),
                "per_item_ms": round(per_item * 1000, 1),
            }
            print(f"[{model}] dim={dim} norm={norm:.4f} "
                  f"cold={t_single:.2f}s warm={t_warm:.3f}s "
                  f"batch32={t_batch:.2f}s ({per_item * 1000:.1f}ms/条)")
        except Exception as exc:  # 模型未拉取 / Ollama 未启动
            results[model] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"[{model}] FAILED: {exc}")

    with open("probe_result.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\nwrote probe_result.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

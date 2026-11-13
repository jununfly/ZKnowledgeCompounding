#!/usr/bin/env python
"""R13 常驻实测探针（R13 相关切片）：qwen3.5:9b GGUF + num_ctx 8192 的真实常驻。

回答 spike-10 遗留 open 项：「9B GGUF 6.55GB + num_ctx 8192 常驻」未实测，
旧结论「9B 在 16GB 不可用于迭代」基于 mlx 8.9GB 权重 + 原生 256K 加载
（常驻 ~15GB），限了 num_ctx 后是否松动待判。

测量口径（每模型一轮，可多模型对比）：
  ① ollama ps SIZE —— Ollama 自报加载内存（权重+KV），主指标；
  ② ollama 进程树 RSS 差值 —— 系统侧旁证（Metal 显存映射不完全反映在 RSS，
     仅作参考）；
  ③ eval rate —— tokens/s（可用性旁证，非本节点主判据）。

用法：
  python scripts/r13_9b_resident_probe.py --model qwen3.5:9b --num-ctx 8192
  python scripts/r13_9b_resident_probe.py --model qwen3.5:9b-mlx --num-ctx 8192

前置：ollama ps 为空（先卸载其他模型）；探针结束自动卸载（keep_alive=0）。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OLLAMA_URL = "http://localhost:11434"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ollama_ps() -> list[dict]:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            rows.append({"name": parts[0], "size": parts[2], "processor": " ".join(parts[3:])})
    return rows


def rss_sum_mb() -> float:
    """系统空闲内存（MB）——vm_stat free+inactive 页（沙箱内可用；ps 被拦）。

    加载前后 (free+inactive) 下降量 ≈ 模型吸收的系统内存（含 Metal wired 映射），
    作 ollama ps SIZE 的系统侧旁证。
    """
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    page = 16384  # Apple Silicon 页大小（vm_stat 首行标注，固定 16KB）
    free = inactive = 0
    for line in out.splitlines():
        if line.startswith("Pages free:"):
            free = int(line.split(":")[1].strip().rstrip("."))
        elif line.startswith("Pages inactive:"):
            inactive = int(line.split(":")[1].strip().rstrip("."))
    return (free + inactive) * page / 1048576


def generate(model: str, prompt: str, *, num_ctx: int, num_predict: int,
             keep_alive: str, timeout: float = 600) -> dict:
    body = json.dumps({
        "model": model, "prompt": prompt, "think": False,
        "stream": False, "keep_alive": keep_alive,
        "options": {"num_ctx": num_ctx, "num_predict": num_predict},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL.rstrip("/") + "/api/generate", data=body,
        headers={"Content-Type": "application/json"},
    )
    with _OPENER.open(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def unload(model: str) -> None:
    generate(model, "", num_ctx=512, num_predict=0, keep_alive="0", timeout=120)


def probe(model: str, num_ctx: int, *, prompt: str = "用一句话解释什么是知识复利。") -> dict:
    rsrc_free_before = rss_sum_mb()
    ps_before = ollama_ps()
    t0 = time.time()
    r1 = generate(model, prompt, num_ctx=num_ctx, num_predict=32, keep_alive="5m")
    load_wall = time.time() - t0
    time.sleep(2)  # 等 ollama ps 与 runner 稳定
    ps_rows = [p for p in ollama_ps() if p["name"] == model]
    rsrc_free_after = rss_sum_mb()

    # 第二次生成： warmed-up eval rate（不受加载抖动影响）
    t1 = time.time()
    r2 = generate(model, prompt + "再换一种说法。", num_ctx=num_ctx,
                  num_predict=64, keep_alive="5m")
    warm_wall = time.time() - t1

    unload(model)
    time.sleep(1)
    unloaded = all(p["name"] != model for p in ollama_ps())

    ev = r2.get("eval_count") or r2.get("eval_count", 0)
    dur = r2.get("eval_duration") or 0
    return {
        "model": model,
        "num_ctx": num_ctx,
        "ollama_ps_size": ps_rows[0]["size"] if ps_rows else None,
        "ollama_ps_processor": ps_rows[0]["processor"] if ps_rows else None,
        "rsrc_free_before_mb": round(rsrc_free_before),
        "rsrc_free_after_mb": round(rsrc_free_after),
        "mem_absorbed_mb": round(rsrc_free_before - rsrc_free_after),
        "first_gen_wall_s": round(load_wall, 2),
        "warm_gen_wall_s": round(warm_wall, 2),
        "eval_rate_tok_s": round(ev / (dur / 1e9), 1) if dur else None,
        "prompt_eval_rate_tok_s": round(
            (r2.get("prompt_eval_count") or 0) / ((r2.get("prompt_eval_duration") or 1) / 1e9), 1
        ) if r2.get("prompt_eval_duration") else None,
        "unloaded": unloaded,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="R13 9B 常驻实测（ollama ps SIZE 主指标）")
    ap.add_argument("--model", required=True)
    ap.add_argument("--num-ctx", type=int, default=8192)
    args = ap.parse_args(argv)

    loaded = [p["name"] for p in ollama_ps()]
    if loaded:
        print(f"! 有模型已加载，先卸载避免污染基线: {loaded}", file=sys.stderr)
        for m in loaded:
            unload(m)
        time.sleep(2)

    r = probe(args.model, args.num_ctx)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

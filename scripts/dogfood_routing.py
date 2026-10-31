#!/usr/bin/env python3
"""ZKC · 路由引擎真实 LLM dogfood（roadmap 1-3-3 / 残留#1 验证器）。

用途：在本机起 Ollama 后手动执行，验证 DecisionRouter(OllamaClient) 真实链路。
沙箱/无 Ollama 环境执行 → 打印 SKIP 并以 0 退出（非失败，捕获不因此阻塞）。

用法：
    python3 scripts/dogfood_routing.py [ollama_url] [model]

前置（本机）：
    ollama serve                      # 或已随 App 运行
    ollama pull qwen2.5-coder:1.5b    # 默认模型，可用第二参数替换
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc.routing import (  # noqa: E402
    DEFAULT_LLM_MODEL,
    DEFAULT_OLLAMA_URL,
    DecisionRouter,
    OllamaClient,
    route_text,
)

SAMPLES = [
    "2026-10-31 与房东签了续租合同，租金每月 6800 元",   # 预期 static
    "明天上午 10 点要去银行办抵押手续，别忘了带身份证",   # 预期 dynamic
    "嗯那个事情再说吧",                                   # 预期 vague
]


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OLLAMA_URL
    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_LLM_MODEL

    client = OllamaClient(model=model, url=url)
    if not client.health():
        print(f"SKIP: Ollama 不可达（{url}）。本机执行：ollama serve && ollama pull {model}")
        return 0

    dr = DecisionRouter(client)
    print(f"OK: Ollama 可达，model={model}\n")
    for text in SAMPLES:
        res = route_text(text, dr, lexical_router=None)  # 无词法 → llm-only 降级路径
        print(f"文本: {text}")
        print(f"  → track={res.track} conf={res.confidence:.2f} "
              f"llm=({res.llm_track},{res.llm_conf:.2f}) source={res.source} "
              f"aborted={res.aborted}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

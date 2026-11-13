"""ZKC · 真实 LLM 接线（蒸馏结构化接线）：Ollama 原生 /api/chat 客户端（stdlib urllib，零依赖）。

本模块是蒸馏算子（zkc.distill）到本地 Ollama 的生产接线层。三条实测铁律
（dogfood 复现定位 + spike-10 rerun.py 记录，见蒸馏设计决策）：
  ① **/v1 端点 + response_format {"type":"json_object"} 对 qwen3.5-mlx 永久挂死**
     （单次小调用 >900s 无响应；同请求去掉 response_format 13s 返回，
     原生 /api/chat + format:"json" 0.6s 返回）。因此本模块只走原生 /api/chat；
     Instructor Mode.JSON_SCHEMA / OPENAI_TOOLS 会发 response_format，一并禁用
     （Instructor Mode.JSON 走提示层所以 spike 未踩，但为一致性统一不引 Instructor）。
  ② **每次调用必须显式钉死 think=False + num_ctx=8192**：Qwen3.5 默认按原生 256K
     context 加载 → 16GB 机器 residency ~15GB → 推理爬行。
  ③ **num_predict 必须显式给足**：默认截断会把产物 JSON 腰斩（缺必填字段）。

JSON 合规 = prompt 约束（distill.DISTILL_SCHEMA_HINT）+ distill 层校验重试。
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable, Optional

from . import tuning

# 蒸馏 seam：与 zkc.distill.LLM 同型（prompt -> 原始文本）。
LLM = Callable[[str], str]

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_DISTILL_MODEL = "qwen3.5:4b-mlx"  # 实现计划 §2 蒸馏默认档；4B 实证稳定
DEFAULT_NUM_CTX = 8192                    # 铁律②：钉死，防 256K 默认加载爬行


def ollama_chat(
    url: str,
    model: str,
    prompt: str,
    *,
    timeout: float = 300.0,
    num_ctx: int = DEFAULT_NUM_CTX,
    num_predict: Optional[int] = None,
    temperature: float = 0.2,
    json_mode: bool = True,
) -> str:
    """调用 Ollama 原生 /api/chat，返回 message.content 原文。

    铁律①②③内置为默认行为；json_mode=False 时去掉 format:"json"（非结构化用途）。
    网络错误/超时抛 OSError（调用方决定降级策略，distill 层由重试循环兜底）。
    """
    np = int(num_predict if num_predict is not None
             else tuning.get("DISTILL_NUM_PREDICT"))
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,  # 铁律②
        "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": np},
    }
    if json_mode:
        body["format"] = "json"  # 铁律①：原生 format 字段，绝不走 /v1 response_format
    req = urllib.request.Request(
        url.rstrip("/") + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return str(data.get("message", {}).get("content", ""))


def ollama_reachable(url: str = DEFAULT_OLLAMA_URL, timeout: float = 3.0) -> bool:
    """GET /api/tags 探活（与 routing.OllamaClient.health 同语义，独立实现避免耦合）。"""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def make_distill_llm(
    url: str = DEFAULT_OLLAMA_URL,
    model: str = DEFAULT_DISTILL_MODEL,
    *,
    timeout: float = 300.0,
) -> LLM:
    """返回可注入 distill_node 的真实 LLM callable（prompt -> 原始文本）。

    产物为 JSON 文本（format:"json" 保证），由 distill._parse_json_output 消费。
    附带 ``model_name`` 属性，供 score 表记录（expiry.apply_distill 经
    ``getattr(llm, "model_name", None)`` 读取）。
    """
    def _call(prompt: str) -> str:
        return ollama_chat(url, model, prompt, timeout=timeout)

    _call.model_name = model  # type: ignore[attr-defined]
    return _call

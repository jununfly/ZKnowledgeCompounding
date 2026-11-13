"""ZKC · embedding 编码器（P5.1，spike-14 选型落地）。

定死编码器 = nomic-embed-text 768d（tuning: EMBEDDING_MODEL / EMBEDDING_DIM，
spike 14 实测：冷 0.65s / warm 12ms / 已 L2 归一化）。

用途硬约束（R16 / 架构 §5）：**仅限检索召回与反向连接候选，严禁用于安全判定**。
调用方（zkc.search）把它当候选召回器，结果交人工确认。

接线口径（spike-14 同款）：
  - 原生 /api/embed（批量 input 数组，返回已归一化向量）；
  - 本机 Clash 代理会让 localhost 无限挂起 → 用 no-proxy opener（不装全局，
    仅本模块请求绕过代理，不影响其他出网代码）。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Optional

from . import tuning

DEFAULT_OLLAMA_URL = "http://localhost:11434"

# encoder seam：list[text] -> list[vector]。测试注入 fake，生产用 make_encoder。
Encoder = Callable[[list[str]], list[list[float]]]

# 本模块专用 no-proxy opener：localhost 必须绕过 Clash（spike-14 / §8.3 教训），
# 且不 install_opener —— 避免污染其他模块的全局 urllib 行为。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class EncoderError(RuntimeError):
    """编码失败（网络/超时/维度不符）。调用方据此降级为纯结构化检索。"""


def encode_texts(
    texts: list[str],
    *,
    url: str = DEFAULT_OLLAMA_URL,
    model: Optional[str] = None,
    timeout: float = 60.0,
    dim: Optional[int] = None,
) -> list[list[float]]:
    """批量编码：list[text] -> list[vector]（校验维度与指定 dim 一致）。

    dim 缺省 = tuning.EMBEDDING_DIM（nomic 768）；4096 候选召回列传
    tuning.EMBEDDING_4096_DIM 覆写（双列共存，见 make_encoder_4096）。
    """
    if not texts:
        return []
    mdl = model if model is not None else tuning.get("EMBEDDING_MODEL")
    expected_dim = dim if dim is not None else int(tuning.get("EMBEDDING_DIM"))
    body = json.dumps({"model": mdl, "input": list(texts)}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/embed",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise EncoderError(f"embed 调用失败: {e}") from e
    vecs = data.get("embeddings")
    if not isinstance(vecs, list) or len(vecs) != len(texts):
        raise EncoderError(f"embed 返回条数不符: 期望 {len(texts)}，收到 {type(vecs)}")
    for v in vecs:
        if not isinstance(v, list) or len(v) != expected_dim:
            got = len(v) if isinstance(v, list) else None
            raise EncoderError(
                f"embed 维度不符: 期望 {expected_dim}（{mdl}），收到 {got}"
            )
    return [list(map(float, v)) for v in vecs]


def make_encoder(
    url: str = DEFAULT_OLLAMA_URL,
    model: Optional[str] = None,
    *,
    timeout: float = 60.0,
    dim: Optional[int] = None,
) -> Encoder:
    """返回可注入 search 层的 encoder callable（带 model_name 属性供观测）。"""

    def _encode(texts: list[str]) -> list[list[float]]:
        return encode_texts(texts, url=url, model=model, timeout=timeout, dim=dim)

    _encode.model_name = model if model is not None else tuning.get("EMBEDDING_MODEL")
    return _encode


def make_encoder_4096(
    url: str = DEFAULT_OLLAMA_URL, *, timeout: float = 60.0
) -> Encoder:
    """4096 候选召回列专用编码器（qwen3-embedding，双列共存）。

    模型/维度均取 tuning.EMBEDDING_4096_*，与 nomic 768 编码器并存、互不覆盖。
    """

    def _encode(texts: list[str]) -> list[list[float]]:
        return encode_texts(
            texts,
            url=url,
            model=tuning.get("EMBEDDING_4096_MODEL"),
            timeout=timeout,
            dim=int(tuning.get("EMBEDDING_4096_DIM")),
        )

    _encode.model_name = tuning.get("EMBEDDING_4096_MODEL")
    return _encode

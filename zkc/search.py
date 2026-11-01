"""ZKC · 复利产出检索编排（P5.1 / T6.1，生产落地）。

双路检索（R18 缓解，decide 已落盘 1-6-1）：
  ① 结构化为主：track/decay 区间/q 子串/排序，纯过滤零新依赖；
  ② embedding 候选召回为辅：q 经 encoder（nomic 768d，仅限召回用途，
     严禁安全判定——R16）→ kNN，结果作为候选追加、交人工确认。

降级语义：encoder 未注入或调用失败 → 仅结构化结果，``degraded=True`` 绝不抛异常——
检索是浏览入口，可用性优先于完整性（R18 本就是「候选召回不准」而非「错误答案」风险）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .encoder import Encoder, EncoderError
from .repository.models import Node

STRUCTURED = "structured"
EMBEDDING = "embedding"


@dataclass
class SearchHit:
    node: Node
    source: str            # structured | embedding
    sim: Optional[float]   # embedding 命中的余弦相似；结构化命中为 None


def search(
    store,
    *,
    q: Optional[str] = None,
    track: Optional[str] = None,
    decay_min: Optional[float] = None,
    decay_max: Optional[float] = None,
    include_archived: bool = False,
    order: str = "created_desc",
    limit: int = 50,
    encoder: Optional[Encoder] = None,
    k: int = 10,
) -> dict:
    """双路检索：结构化命中在前（按 order），embedding 候选追加在后（按 sim 降序）。

    返回 dict（SSR/JSON 两用）：
      hits / structured_count / embedding_count / degraded / degrade_reason
    """
    structured = store.nodes.search(
        track=track, q=q, decay_min=decay_min, decay_max=decay_max,
        include_archived=include_archived, order=order, limit=limit,
    )
    hits = [SearchHit(node=n, source=STRUCTURED, sim=None) for n in structured]
    seen = {n.id for n in structured}
    emb_count = 0
    degraded = False
    degrade_reason = None

    if q and encoder is not None:
        try:
            vecs = encoder([q])
            candidates = store.nodes.search_by_embedding(
                vecs[0], k=k, include_archived=include_archived
            )
        except EncoderError as e:
            degraded = True
            degrade_reason = str(e)
            candidates = []
        for node, sim in candidates:
            if node.id in seen:
                continue
            seen.add(node.id)
            hits.append(SearchHit(node=node, source=EMBEDDING, sim=sim))
            emb_count += 1

    return {
        "hits": hits,
        "structured_count": len(structured),
        "embedding_count": emb_count,
        "degraded": degraded,
        "degrade_reason": degrade_reason,
    }

"""ZKC · embedding 回填算子（全轨 / 幂等 / 可注入 encoder）。

背景：capture profile 只加源节点（ADR-0004），新摄入节点默认没有向量；历史回填
脚本 `backfill_embedding_4096.py` 又只扫 dynamic 且用 `and n.content` 跳过空正文
节点，导致 `/browse` 语义召回长期留缺口。本模块把「补齐」收敛成一个与传输层
无关、可测试、可调度的领域算子：

- 全轨：默认 static / dynamic / unrouted 都扫；已归档节点跳过（已移出召回，不补向量）；
- 空正文兜底：text = title + ("\\n" + content if content else "")，绝不跳过；
- 幂等：只写缺失列，第二遍零写入；
- 去重：相同 text 的每个列只编码一次（重复节点天然共享向量）；
- 原子：先全部编码成功，再统一写列；任一编码失败 → 零写入，不留半成品；
- 轻量写：走 `NodeRepository.set_embedding_column`，不写双时态历史。

边界：本算子**不在 capture 链路里自动触发**。在 capture 时编码会把 encoder
依赖引入 transport seam 并扩大 ADR-0004 的 capture 写入面，属需单独拍板的
架构变更；当前由 `zkc embed` 子命令（可挂调度）显式运行。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, Sequence

Encoder = Callable[[list[str]], list[list[float]]]

ALL_TRACKS = ("static", "dynamic", "unrouted")
ALL_COLUMNS = ("embedding", "embedding_4096")


def embedding_text(node) -> str:
    """编码用文本：正文为空时只用标题兜底（修旧脚本永久漏补的口径）。"""
    return node.title + ("\n" + node.content if node.content else "")


def make_default_encoders() -> Dict[str, Encoder]:
    """生产 encoder：按 tuning 参数配对的 768 / 4096 双列编码器（懒加载）。"""
    from . import tuning
    from .encoder import encode_texts

    model768, dim768 = tuning.get("EMBEDDING_MODEL"), int(tuning.get("EMBEDDING_DIM"))
    model4096 = tuning.get("EMBEDDING_4096_MODEL")
    dim4096 = int(tuning.get("EMBEDDING_4096_DIM"))
    return {
        "embedding": lambda texts: encode_texts(
            texts, model=model768, dim=dim768, timeout=600),
        "embedding_4096": lambda texts: encode_texts(
            texts, model=model4096, dim=dim4096, timeout=600),
    }


def backfill_embeddings(
    store,
    *,
    encoders: Dict[str, Encoder],
    tracks: Sequence[str] = ALL_TRACKS,
    columns: Sequence[str] = ALL_COLUMNS,
    dry_run: bool = False,
) -> dict:
    """扫描并补齐缺失的 embedding 列，返回统计；编码失败时零写入并向上抛错。

    encoders 按列名注入（测试可给 fake，生产用 `make_default_encoders()`）。
    tracks / columns 可收窄，供 R18 老脚本保留「dynamic + 4096」原语义。
    """
    unknown = [c for c in columns if c not in ALL_COLUMNS]
    if unknown:
        raise ValueError(f"未知 embedding 列: {unknown!r}")
    missing_encoder = [c for c in columns if c not in encoders]
    if missing_encoder:
        raise ValueError(f"缺少 encoder: {missing_encoder!r}")

    nodes = []
    for track in tracks:
        nodes.extend(store.nodes.list_by_track(track))

    gaps = []
    eligible = [n for n in nodes if getattr(n, "archived_at", None) is None]
    for n in eligible:
        missing = [c for c in columns if getattr(n, c, None) is None]
        if missing:
            gaps.append((n, missing))

    # 按 text 聚合所需列：重复节点 + 不同缺口组合都只编一次 (text, column)
    needed: dict[str, set] = defaultdict(set)
    for n, missing in gaps:
        needed[embedding_text(n)].update(missing)

    result = {
        "scanned": len(nodes),
        "archived_skipped": len(nodes) - len(eligible),
        "gap_nodes": len(gaps),
        "gap_columns": sum(len(m) for _, m in gaps),
        "unique_texts": len(needed),
        "tracks": list(tracks),
        "columns": list(columns),
        "dry_run": dry_run,
        "encoded": 0,
        "columns_written": 0,
        "written": [],
    }
    if dry_run or not gaps:
        return result

    # 阶段一：全部编码成功才进入阶段二（否则零写入）
    vectors: dict[tuple[str, str], list[float]] = {}
    for text, cols in needed.items():
        for c in columns:  # 固定列序，结果可复现
            if c in cols:
                vectors[(text, c)] = encoders[c]([text])[0]
                result["encoded"] += 1

    # 阶段二：统一轻量写（不写 history、不 bump tx_from）
    for n, missing in gaps:
        text = embedding_text(n)
        for c in missing:
            store.nodes.set_embedding_column(n.id, c, vectors[(text, c)])
            result["written"].append({"node_id": str(n.id), "column": c})
            result["columns_written"] += 1
    return result


__all__ = [
    "ALL_TRACKS", "ALL_COLUMNS", "Encoder", "embedding_text",
    "make_default_encoders", "backfill_embeddings",
]

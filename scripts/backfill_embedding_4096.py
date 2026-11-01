#!/usr/bin/env python
"""R18 加列路径回填（1-8-4-1）：给 zkc_dev 的 node.embedding_4096 补齐 qwen3 向量。

走 repository seam（NodeRepository.set_embedding_column 轻量路径），不直连 SQL。
幂等：只回填该列为空且有 content 的动态节点。4096 长文编码慢（~7.5min/61 条），
自动分批（batch=4）+ 进度打印。

用法：
    python scripts/backfill_embedding_4096.py            # 回填 zkc_dev
    python scripts/backfill_embedding_4096.py --dry-run  # 只看缺多少条
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc import tuning
from zkc.repository import get_storage


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="回填 node.embedding_4096（qwen3 4096d）")
    ap.add_argument("--batch", type=int, default=4, help="每批编码条数（默认 4）")
    ap.add_argument("--dry-run", action="store_true", help="只统计缺口，不回填")
    args = ap.parse_args(argv)

    store = get_storage()
    nodes = [
        n for n in store.nodes.list_by_track("dynamic")
        if n.embedding_4096 is None and n.content
    ]
    print(f"缺 embedding_4096 的动态节点: {len(nodes)} 条")
    if args.dry_run or not nodes:
        return 0

    from zkc.encoder import EncoderError, encode_texts

    model = tuning.get("EMBEDDING_4096_MODEL")
    dim = int(tuning.get("EMBEDDING_4096_DIM"))
    done = 0
    for i in range(0, len(nodes), args.batch):
        chunk = nodes[i:i + args.batch]
        texts = [n.title + ("\n" + n.content if n.content else "") for n in chunk]
        try:
            vecs = encode_texts(texts, model=model, dim=dim, timeout=600)
        except EncoderError as e:
            print(f"  ! 回填中止（Ollama 不可达?）: {e}")
            return 1
        for n, v in zip(chunk, vecs):
            store.nodes.set_embedding_column(n.id, "embedding_4096", v)
            done += 1
        print(f"  [{done}/{len(nodes)}] {chunk[-1].title[:40]}")
    print(f"回填完成: {done} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

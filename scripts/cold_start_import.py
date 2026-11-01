#!/usr/bin/env python3
"""ZKC 冷启动导入（1-7-2）：把一批真实动态型素材批量灌入本机 ZKC。

用法：
    python scripts/cold_start_import.py 素材文件.md           # 导入并种下调度基线
    python scripts/cold_start_import.py 素材.json --dry-run   # 只解析预览，不落库
    python scripts/cold_start_import.py 素材.md --mode route  # 走真实双信号分流（需 Ollama）

输入格式（按扩展名自动识别）：
- .json：[{"title": "...", "content": "..."}] 或 ["单行素材", ...]
- .md / .txt / 其他：两种块式解析，谁命中用谁——
  a) markdown 标题式：每个 "## 标题" 开一段，标题下到下一个 "##" 之间是正文；
  b) 空行分块式：空行分隔的块，块首行 = 标题，其余 = 正文。

行为：
- 默认 --mode direct：素材已声明为动态型，track 直接落 dynamic（冷启动语义）。
  --mode route 则走 ingest_with_routing 双信号分流（vague 会进人工定轨队列）。
- 默认计算 embedding（Ollama nomic，供 /browse 语义召回）；不可用则降级跳过，不阻塞。
- 导入后调 scheduling.assign_baselines 给动态轨种 review_interval + last_reviewed_at，
  复审闭环从此启动。
- 幂等：title 与库中现有节点完全一致则跳过，重复跑不会翻倍。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zkc.repository import get_storage  # noqa: E402
from zkc.repository.models import Node  # noqa: E402
from zkc import ingest, scheduling  # noqa: E402


def parse_entries(path: str) -> list[dict]:
    """按扩展名解析素材文件 -> [{"title", "content"}]。"""
    if path == "-":
        raw = sys.stdin.read()
        suffix = ".txt"
    else:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f"素材文件不存在: {p}")
        raw = p.read_text(encoding="utf-8")
        suffix = p.suffix.lower()

    if suffix == ".json":
        data = json.loads(raw)
        entries: list[dict] = []
        for item in data:
            if isinstance(item, dict):
                entries.append({
                    "title": str(item.get("title", "")).strip(),
                    "content": (str(item.get("content")).strip() or None)
                    if item.get("content") else None,
                })
            else:
                text = str(item).strip()
                entries.append({"title": text.split("\n", 1)[0], "content": text})
        return [e for e in entries if e["title"]]

    return _parse_text_blocks(raw)


def _parse_text_blocks(raw: str) -> list[dict]:
    """文本块式解析：优先 markdown 标题式；无 "## " 则退空行分块式。"""
    md_parts = re.split(r"(?m)^##\s+", raw)
    if len(md_parts) > 1:
        entries = []
        for part in md_parts[1:]:
            lines = part.strip().split("\n", 1)
            title = lines[0].strip()
            content = lines[1].strip() if len(lines) > 1 else None
            if title:
                entries.append({"title": title, "content": content or None})
        return entries

    entries = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n", 1)
        title = lines[0].strip()
        content = lines[1].strip() if len(lines) > 1 else None
        if title:
            entries.append({"title": title, "content": content or None})
    return entries


def import_entries(entries: list[dict], *, store, mode: str) -> dict:
    """逐条导入，title 幂等去重。返回统计。"""
    stats = {"imported": 0, "skipped": 0, "classify_queued": 0}
    routers = None
    for e in entries:
        dup = store.nodes.search(q=e["title"], limit=1)
        if any(n.title == e["title"] for n in dup):
            stats["skipped"] += 1
            continue
        if mode == "route":
            from zkc.web.app import build_routers

            if routers is None:
                routers = build_routers()
            node, res = ingest.ingest_with_routing(
                title=e["title"],
                content=e["content"],
                decision_router=routers[0],
                lexical_router=routers[1],
                llm_available=True,
                store=store,
            )
            if res.track == "vague":
                stats["classify_queued"] += 1
        else:
            node = ingest.ingest_node(
                title=e["title"], content=e["content"], track="dynamic", store=store,
            )
        stats["imported"] += 1
        print(f"  + [{node.track}] {e['title']}")
    return stats


def fill_embeddings(store) -> int:
    """给缺 embedding 的节点补向量（/browse 语义召回用）。失败降级返回 0。"""
    try:
        from zkc.encoder import EncoderError, encode_texts
    except Exception as e:  # pragma: no cover - 依赖缺失
        print(f"  ! encoder 不可用，跳过 embedding: {e}")
        return 0
    nodes = [n for n in store.nodes.list_by_track("dynamic") if n.embedding is None]
    if not nodes:
        return 0
    texts = [n.title + ("\n" + n.content if n.content else "") for n in nodes]
    try:
        vecs = encode_texts(texts)
    except EncoderError as e:
        print(f"  ! embedding 降级（Ollama 不可达?）: {e}")
        return 0
    for n, v in zip(nodes, vecs):
        n.embedding = v
        store.nodes.save(n)
    return len(nodes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ZKC 冷启动批量导入（1-7-2）")
    ap.add_argument("source", help="素材文件（.json/.md/.txt，或 - 读 stdin）")
    ap.add_argument("--mode", choices=["direct", "route"], default="direct",
                    help="direct=直接落 dynamic（默认）；route=走双信号分流")
    ap.add_argument("--no-embed", action="store_true", help="跳过 embedding 计算")
    ap.add_argument("--dry-run", action="store_true", help="只解析预览，不落库")
    args = ap.parse_args(argv)

    entries = parse_entries(args.source)
    print(f"解析到 {len(entries)} 条素材")
    for e in entries[:5]:
        print(f"  ? {e['title']}")
    if len(entries) < 60:
        print(f"  ! 注意：目标为 >=60 条，当前 {len(entries)} 条")
    if args.dry_run:
        return 0

    store = get_storage()
    stats = import_entries(entries, store=store, mode=args.mode)
    print(f"导入 {stats['imported']} 条（跳过重复 {stats['skipped']}，"
          f"待人工定轨 {stats['classify_queued']}）")

    if not args.no_embed:
        n = fill_embeddings(store)
        print(f"embedding 补齐 {n} 条")

    baseline = scheduling.assign_baselines(store)
    print(f"调度基线: {len(baseline)} 条动态节点已种 interval/last_reviewed_at")

    due = ingest.list_due_for_review(store=store)
    total_dynamic = len(store.nodes.list_by_track("dynamic"))
    print(f"当前动态轨 {total_dynamic} 条，今日待复审 {len(due)} 条")
    print("下一步：打开 http://localhost:8000/review 开始带标注复审（锚 A）+ 每日收口（锚 B）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""ZKC 过程权威边界门禁（自包含，CI 可直接执行）。

判定语义与 zj-roadmap-driven 的 ``authority-check`` 对齐：拒绝 durable 代码 /
长期文档直接引用过程产物、用 markdown link 引用过程产物，或把「roadmap 节点
已完成」直接写成 proof / evidence。**判定规则一条都不放宽**，只把过程态对象
从扫描范围里识别出去（对齐上游 issue #239 / PR #240 的修复）：

1. 过程态目录整类剪枝：``.git`` / ``.workbuddy`` / ``__pycache__`` /
   ``node_modules`` / ``tmp``。**不硬编码任何过程产物目录名**——哪些文件是
   过程态按内容签名判定，与所在路径无关（解耦：项目不再知道旧目录名）。
2. 单文件 roadmap carrier 按**结构签名**识别（title / version / nodes /
   metadata 齐备且每个节点带 status），普通 ``nodes.json`` 不能借机逃逸。
3. ``render`` / ``section`` 产出的 Markdown 视图按开头完整的
   ``zj-roadmap-authority/v1`` 权威信封识别。
4. 被签名识别为过程态的文件，其相对路径动态加入禁止引用清单；durable
   源码引用其中任一条即报泄漏。清单为空时（如过程产物已全部移除）判定
   规则不变，只是没有可命中的目标。

本脚本**不 import 用户级 skill** —— CI runner 上没有 ``~/.workbuddy/skills``，
任何依赖该路径的接法在 CI 里都不可执行。旧版 6 条枚举式白名单已删除：每新增
一天过程日志、一条节点 notes 都要人工加条目，结构性判据可复刻且无需维护清单。
治理结论见 docs/zj-adr/0008-process-authority-boundary.md。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys


MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
ROADMAP_COMPLETION_CLAIM_RE = re.compile(
    r"(?:\b(?:proof|evidence)\s*:\s*roadmap\s+node\s+\d+(?:-\d+)*\s+"
    r"(?:is\s+)?(?:completed?|done)\b|"
    r"根据\s*roadmap\s*节点\s*\d+(?:-\d+)*\s*(?:已)?完成)",
    re.IGNORECASE,
)
DURABLE_SUFFIXES = frozenset({
    ".c", ".cpp", ".cs", ".go", ".h", ".hpp", ".java", ".js", ".json",
    ".jsx", ".kt", ".md", ".php", ".py", ".rb", ".rs", ".sh", ".swift",
    ".toml", ".ts", ".tsx", ".yaml", ".yml",
})
# 目录名按 path 段比较：这些树不承载长期事实，剪枝也让 walk 不进 .git/objects。
EXCLUDED_DIR_PARTS = frozenset({
    ".git",
    ".workbuddy",  # append-only agent memory / logs
    "__pycache__",
    "node_modules",
    "tmp",
})
# 与上游 roadmap.py 的常量逐字一致（自包含，不 import）。
ROADMAP_AUTHORITY_ENVELOPE = """<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->"""
PROCESS_STATE_HEAD_LIMIT = 512
# carrier 结构签名刻意收窄：普通 nodes.json 不能靠长出 nodes 键就逃过门禁。
CARRIER_REQUIRED_KEYS = frozenset({"title", "version", "nodes", "metadata"})
COMPLETION_TARGET = "roadmap completion claim"


@dataclass(frozen=True)
class Leak:
    source: str
    line: int
    target: str


@dataclass(frozen=True)
class ScanStats:
    process_targets: int
    scanned: int
    skipped: tuple[str, ...]


def _is_roadmap_carrier(text: str) -> bool:
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return False
    if not isinstance(data, dict) or not CARRIER_REQUIRED_KEYS.issubset(data):
        return False
    nodes = data["nodes"]
    if not isinstance(nodes, (dict, list)) or not isinstance(data["metadata"], dict):
        return False
    values = nodes.values() if isinstance(nodes, dict) else nodes
    return all(isinstance(node, dict) and "status" in node for node in values)


def _is_process_state_file(source: Path, text: str) -> bool:
    suffix = source.suffix.lower()
    if suffix == ".md":
        return ROADMAP_AUTHORITY_ENVELOPE in text[:PROCESS_STATE_HEAD_LIMIT]
    if suffix == ".json":
        return _is_roadmap_carrier(text)
    return False


def _iter_sources(root: Path):
    """遍历候选文件，进入目录前只剪掉通用过程态树（与具体目录名无关）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        relative_dir = current.relative_to(root)
        dirnames[:] = [
            name for name in dirnames if name not in EXCLUDED_DIR_PARTS
        ]
        for name in filenames:
            source = current / name
            if source.is_file():
                yield source, relative_dir / name


def find_leaks(root: Path) -> tuple[list[Leak], frozenset[str], ScanStats]:
    """返回 (泄漏清单, 过程产物相对路径集合, 扫描统计)。

    过程态产物按内容签名识别，与所在路径无关：第一遍收集被签名识别的
    文件相对路径作禁止引用清单，第二遍在 durable 源码中查引用。清单为空
    时（过程产物已全部移除）判定规则不变，只是没有可命中的目标。
    """
    root = root.resolve()
    candidates = [
        (source, relative_path, source.read_text(encoding="utf-8", errors="replace"))
        for source, relative_path in _iter_sources(root)
        if source.suffix.lower() in DURABLE_SUFFIXES
    ]
    process_targets = frozenset(
        relative_path.as_posix()
        for source, relative_path, text in candidates
        if _is_process_state_file(source, text)
    )

    leaks: list[Leak] = []
    skipped: list[str] = []
    scanned = 0
    for source, relative_path, text in candidates:
        relative_source = relative_path.as_posix()
        if _is_process_state_file(source, text):
            skipped.append(relative_source)
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            matched: set[str] = set()
            if ROADMAP_COMPLETION_CLAIM_RE.search(line):
                matched.add(COMPLETION_TARGET)
            for target in process_targets:
                if target in line:
                    matched.add(target)
            if source.suffix.lower() == ".md":
                for raw in MARKDOWN_LINK_RE.findall(line):
                    raw_target = raw.strip().strip("<>").split("#", 1)[0]
                    resolved = (source.parent / raw_target).resolve()
                    relative = (
                        resolved.relative_to(root).as_posix()
                        if resolved.is_relative_to(root) else ""
                    )
                    if relative in process_targets:
                        matched.add(relative)
            for target in sorted(matched):
                leaks.append(Leak(relative_source, lineno, target))

    stats = ScanStats(len(process_targets), scanned, tuple(sorted(skipped)))
    return leaks, process_targets, stats


def evaluate(root: Path) -> tuple[list[str], int]:
    """返回 (逐行输出, unresolved 泄漏数)。"""
    leaks, _, stats = find_leaks(root)
    output: list[str] = [
        f"ZKC authority-check root={root.resolve()}",
        f"scope: {stats.process_targets} process target(s); "
        f"pruned dirs: {', '.join(sorted(EXCLUDED_DIR_PARTS))}; "
        f"scanned {stats.scanned} durable source(s); "
        f"skipped {len(stats.skipped)} process-state file(s)",
    ]
    if stats.skipped:
        # 逐条打印被跳过的文件，替代旧白名单的 STALE 防线：不静默吞掉。
        output.append("skipped: " + ", ".join(stats.skipped))
    for leak in leaks:
        output.append(
            f"E_PROCESS_AUTHORITY_LEAK {leak.source}:{leak.line}: "
            f"cites transient process artifact {leak.target}"
        )
    output.append(f"summary: {len(leaks)} unresolved leaks")
    return output, len(leaks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject durable code/docs citing transient process artifacts."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1]),
        help="project root (defaults to this repository)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"E_AUTHORITY_CHECK_ROOT: not a directory: {root}", file=sys.stderr)
        return 2

    output, unresolved = evaluate(root)
    for line in output:
        print(line)
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())

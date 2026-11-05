#!/usr/bin/env python
"""ZKC · rec-avoid 不变式 CI 谓词（ADR-0005 / E6）。

三条机械断言，纯标准库、只读、可脱离 PG / Ollama 在干净 runner 上跑：
  P1 claim 落库仍受 `meta_claim.evidence_refs uuid[] NOT NULL` 约束；
  P2 任何 feature 不得提供关闭 decay / attention 的全局开关；
  P3 归档节点必须退出整个调度回路（D2：due 实现过滤 archived_at +
     refresh_decay 跳过归档），防未来新后端 / 重构把过滤删掉。

只判「不变式有没有被破坏」，不判产品行为正确性；缺陷逐条打印
`E_INVARIANT_* path:line`，任何一条都非零退出。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]

_TABLE_BLOCK = re.compile(
    r"create\s+table\s+(?:public\.)?meta_claim\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_PROVENANCE_FIELD = re.compile(
    r"evidence_refs\s+uuid\[\]\s+not\s+null", re.IGNORECASE
)
# 只拦「全局开关」命名，不误伤 DECAY_FUNCTION / SURFACE_THRESHOLD / ATTENTION_BUDGET_* 等正常参数。
_KILL_SWITCH = re.compile(
    r"\b(?:decay_enabled|attention_enabled|disable_decay|disable_attention|"
    r"decay_off|attention_off|zkc_disable_decay|zkc_disable_attention)\b",
    re.IGNORECASE,
)


def _slice_function(text: str, name: str) -> str | None:
    """截取 def <name> 到下一个同级 def / class / 装饰器之间的源码（够 P3 判定用）。"""
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines)
         if re.search(rf"def\s+{re.escape(name)}\s*\(", line)),
        None,
    )
    if start is None:
        return None
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= base_indent and line.lstrip().startswith(("def ", "class ", "@")):
            end = j
            break
    return "\n".join(lines[start:end])


def _check_archive_exit(root: Path, lines: list[str]) -> int:
    """P3：归档节点必须退出整个调度回路（D2 防回归闸）。

    扫 repository/*.py 里每个 list_due_for_review 实现，要求函数体含 archived_at；
    扫 decay.py 的 refresh_decay，要求既含 archived_at 又含 continue（跳过归档）。
    目标文件不存在时跳过该文件，便于窄 fixture 只造被检查的部分。
    """
    violations = 0
    checked = 0
    repo_dir = root / "src" / "zkc" / "repository"
    candidates = sorted(repo_dir.glob("*.py")) if repo_dir.is_dir() else []
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if "def list_due_for_review" not in text:
            continue
        checked += 1
        body = _slice_function(text, "list_due_for_review") or ""
        if "archived_at" not in body:
            violations += 1
            rel = path.relative_to(root).as_posix()
            lines.append(
                f"E_INVARIANT_ARCHIVE_EXIT {rel}: "
                "list_due_for_review 未排除 archived_at 节点"
            )

    decay_path = root / "src" / "zkc" / "decay.py"
    if decay_path.is_file():
        text = decay_path.read_text(encoding="utf-8")
        if "def refresh_decay" in text:
            checked += 1
            body = _slice_function(text, "refresh_decay") or ""
            if "archived_at" not in body or "continue" not in body:
                violations += 1
                lines.append(
                    "E_INVARIANT_ARCHIVE_EXIT src/zkc/decay.py: "
                    "refresh_decay 未跳过 archived_at 节点（归档未退出调度回路）"
                )

    if violations == 0:
        lines.append(
            f"[P3] archived nodes exit scheduling loop: OK "
            f"(checked {checked} implementations)"
        )
    return violations


def _check_provenance(root: Path, lines: list[str]) -> int:
    sql_files = sorted((root / "migrations").glob("*.up.sql"))
    for path in sql_files:
        text = path.read_text(encoding="utf-8")
        for match in _TABLE_BLOCK.finditer(text):
            lineno = text[: match.start()].count("\n") + 1
            rel = path.relative_to(root).as_posix()
            if _PROVENANCE_FIELD.search(match.group(1)):
                lines.append(
                    f"[P1] meta_claim.evidence_refs NOT NULL: OK ({rel}:{lineno})"
                )
                return 0
            lines.append(
                f"E_INVARIANT_CLAIM_PROVENANCE {rel}:{lineno}: "
                "meta_claim.evidence_refs 缺少 uuid[] NOT NULL 约束"
            )
            return 1
    lines.append(
        "E_INVARIANT_CLAIM_PROVENANCE migrations/: 未找到 meta_claim 建表语句"
    )
    return 1


def _check_kill_switches(root: Path, lines: list[str]) -> int:
    src = root / "src"
    py_files = sorted(p for p in src.rglob("*.py") if "__pycache__" not in p.parts)
    violations = 0
    for path in py_files:
        rel = path.relative_to(root).as_posix()
        for lineno, raw in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            code = raw.split("#", 1)[0]  # 注释里提到禁令不算实现
            hit = _KILL_SWITCH.search(code)
            if hit:
                violations += 1
                lines.append(
                    f"E_INVARIANT_GLOBAL_SWITCH {rel}:{lineno}: {hit.group(0)}"
                )
    if violations == 0:
        lines.append(
            f"[P2] no global decay/attention kill-switch: OK "
            f"(scanned {len(py_files)} source files)"
        )
    return violations


def evaluate(root: Path) -> tuple[list[str], int]:
    """返回 (逐行输出, 不变式违规数)。"""
    lines = [f"ZKC invariant-check root={root}"]
    violations = _check_provenance(root, lines)
    violations += _check_kill_switches(root, lines)
    violations += _check_archive_exit(root, lines)
    lines.append(f"summary: {violations} invariant violations")
    return lines, violations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ADR-0005 rec-avoid 不变式谓词")
    ap.add_argument("root", nargs="?", default=str(DEFAULT_ROOT),
                    help="项目根（默认脚本所在仓库根）")
    args = ap.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    lines, violations = evaluate(root)
    print("\n".join(lines))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""ZKC · 把 zj-zkc-daily skill 从仓库 canonical 同步到用户级运行副本（skill 纳管）。

2026-11-05 zj 拍板：本仓库 `skills/zj-zkc-daily/SKILL.md` 是 **唯一真相源**，
`~/.workbuddy/skills/zj-zkc-daily/SKILL.md` 只是运行副本。此脚本是两者的唯一接线。

安全边界（刻意收窄，避免碰 home 下的目录）：
  - **绝不删除任何目录**（不做「自动删除重装」），只覆盖单个 SKILL.md 文件；
  - 副本内容与 canonical 有分歧时**默认拒绝覆盖**，须显式 --force；
  - --force 覆盖前把旧副本存为 `SKILL.md.bak`（同目录，单文件备份）；
  - --dry-run / --check 只读，不写任何文件。

用法：
    python scripts/install_harness_skill.py --dry-run     # 预览将做什么
    python scripts/install_harness_skill.py --check       # 只查漂移（drift → exit 1）
    python scripts/install_harness_skill.py               # 首次安装 / 一致则跳过
    python scripts/install_harness_skill.py --force       # canonical 更新后强制同步
退出码：0 成功（含 unchanged / dry-run） / 1 漂移或拒绝覆盖 / 2 参数或路径错误。
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL = ROOT / "skills" / "zj-zkc-daily" / "SKILL.md"
DEFAULT_TARGET = Path.home() / ".workbuddy" / "skills" / "zj-zkc-daily" / "SKILL.md"


def plan_sync(canonical=CANONICAL, target=DEFAULT_TARGET) -> dict:
    """只读计划：比较 canonical 与目标副本，返回 drift/action。"""
    canonical = Path(canonical)
    target = Path(target)
    if not canonical.is_file():
        raise ValueError(f"找不到 canonical: {canonical}")
    if target.resolve() == canonical.resolve():
        raise ValueError("目标不能就是 canonical 自身（会自覆盖）")

    source_text = canonical.read_text(encoding="utf-8")
    exists = target.is_file()
    target_text = target.read_text(encoding="utf-8") if exists else None
    drift = (not exists) or (target_text != source_text)
    action = "create" if not exists else ("update" if drift else "none")
    return {
        "canonical": str(canonical),
        "target": str(target),
        "exists": exists,
        "drift": drift,
        "action": action,
        "source_text": source_text,
        "target_text": target_text,
    }


def sync(canonical=CANONICAL, target=DEFAULT_TARGET, *,
         dry_run: bool = False, force: bool = False, backup: bool = True) -> dict:
    """执行同步。返回 {'action', 'backup', 'drift', ...}；不删目录、不批量操作。"""
    p = plan_sync(canonical, target)
    base = {k: p[k] for k in ("canonical", "target", "exists", "drift")}

    if p["action"] == "none":
        return {**base, "action": "unchanged", "backup": None}
    if dry_run:
        return {**base, "action": "would-create" if not p["exists"] else "would-update",
                "backup": None}
    if p["exists"] and not force:
        return {**base, "action": "refused", "backup": None}

    target = Path(target)
    bak = None
    if p["exists"] and backup:
        bak = target.with_name(target.name + ".bak")
        bak.write_text(p["target_text"] or "", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(p["source_text"], encoding="utf-8")
    return {**base,
            "action": "created" if not p["exists"] else "updated",
            "backup": str(bak) if bak else None}


def main(argv=None, out=None) -> int:
    emit = out if out is not None else print
    parser = argparse.ArgumentParser(
        prog="install_harness_skill.py",
        description="同步 zj-zkc-daily skill：仓库 canonical → 用户级运行副本",
    )
    parser.add_argument("--canonical", default=str(CANONICAL), help="仓库内唯一真相源")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="用户级运行副本")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不写")
    parser.add_argument("--check", action="store_true", help="只查漂移，不写")
    parser.add_argument("--force", action="store_true", help="允许覆盖有分歧的副本")
    parser.add_argument("--no-backup", action="store_true", help="覆盖时不留 .bak（不推荐）")
    try:
        args, unknown = parser.parse_known_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if unknown:
        emit(f"未知选项: {' '.join(unknown)}")
        return 2

    try:
        p = plan_sync(args.canonical, args.target)
    except ValueError as exc:
        emit(f"✗ {exc}")
        return 2

    emit(f"canonical = {p['canonical']}")
    emit(f"target    = {p['target']}")
    emit(f"drift     = {p['drift']}  (副本存在={p['exists']})")

    if args.check:
        emit("✓ 副本与 canonical 一致" if not p["drift"] else "✗ 副本与 canonical 有分歧或缺失")
        return 0 if not p["drift"] else 1

    r = sync(args.canonical, args.target,
             dry_run=args.dry_run, force=args.force, backup=not args.no_backup)
    emit(f"action    = {r['action']}")
    if r["backup"]:
        emit(f"旧副本备份 = {r['backup']}")
    if r["action"] == "refused":
        emit("副本被手工改过；确认后用 --force 覆盖，或先人工比对。")
        return 1
    if r["action"] in ("created", "updated"):
        emit("完成。WorkBuddy 侧如需重装 skill，按既有「删除重装」约定人工处理；"
             "本脚本不删除 home 下目录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

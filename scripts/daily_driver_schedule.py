"""ZKC · Windows schtasks 注册渲染器（ADR-0007 跨平台条款补齐）。

ADR-0007 承诺「macOS launchd plist + Windows schtasks(.bat 包装)」，但此前实物只有
macOS 的 install_daily_driver.sh；Windows 侧只有运行包装 daily_e1_driver.bat，
第 20 行还是一句 REM 占位示例（且用了 %CD%，不是仓库根）。

本模块只负责**渲染并（可选）执行 schtasks 命令**，不改 zkc CLI 的
daily/meter/decide 语义，也不改 E1 判据：
  - 对齐 macOS 安装脚本：自动解析 python / 项目根、--dry-run 只预览不注册、
    覆盖式安装（/f）保证幂等、默认 23:50。
  - 任务动作指向现有 daily_e1_driver.bat 包装（一个路径），避免 schtasks /tr
    里「python + 脚本」多参数引号嵌套这个经典坑。
  - 渲染逻辑是纯函数，故本机 macOS 也能用单测覆盖命令契约；真实注册行为
    必须在 Windows 上执行，本模块不会伪造该验证。

用法（Windows，在仓库根或任意 cwd）：
    scripts\\install_daily_driver.bat --dry-run
    scripts\\install_daily_driver.bat                 # 注册每日 23:50
    scripts\\install_daily_driver.bat --uninstall
    scripts\\install_daily_driver.bat --time 07:15 --task-name "ZKC Daily E1"
退出码：0 成功 / 1 schtasks 自身失败 / 2 参数错误 / 3 找不到 schtasks（非 Windows）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRAPPER = ROOT / "scripts" / "daily_e1_driver.bat"
DEFAULT_TASK_NAME = "ZKC Daily E1"
DEFAULT_TIME = "23:50"  # 与 scripts/launchd/com.zkc.daily-e1.plist 保持一致
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def build_task_action(wrapper: str) -> str:
    """构造 schtasks /tr 的动作字符串：路径整体加双引号以容忍空格。"""
    path = str(wrapper)
    if not path.strip():
        raise ValueError("驱动包装路径为空")
    if "__" in path or "%CD%" in path or "%~dp0" in path:
        raise ValueError(f"驱动包装路径仍含占位符: {path}")
    return f'"{path}"'


def build_register_command(
    wrapper: str,
    task_name: str = DEFAULT_TASK_NAME,
    at: str = DEFAULT_TIME,
) -> list[str]:
    if not _TIME_RE.match(at):
        raise ValueError(f"时间须为 HH:MM（00:00-23:59），收到: {at}")
    if not task_name.strip():
        raise ValueError("任务名不能为空")
    return [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", build_task_action(wrapper),
        "/sc", "daily",
        "/st", at,
        "/f",  # 覆盖同名任务，重复安装不报错（对齐 macOS 先卸后装）
    ]


def build_unregister_command(task_name: str = DEFAULT_TASK_NAME) -> list[str]:
    if not task_name.strip():
        raise ValueError("任务名不能为空")
    return ["schtasks", "/delete", "/tn", task_name, "/f"]


def resolve_paths() -> dict[str, str]:
    """解析真实路径（薄壳用 venv python 调进来，故 sys.executable 即真实解释器）。"""
    return {
        "python": sys.executable,
        "project_root": str(ROOT),
        "wrapper": str(WRAPPER),
        "log": str(ROOT / "logs" / "e1_daily.log"),
    }


def format_command(cmd: list[str]) -> str:
    """人类可读预览（实际执行传 list，由 Windows 命令行层负责转义）。

    /tr 的值本身已带外层双引号，这里原样展示，避免 list2cmdline 再转义成
    `\\"path\\"` 让人误以为路径里有反斜杠引号。
    """
    parts = []
    for tok in cmd:
        if tok.startswith('"') and tok.endswith('"'):
            parts.append(tok)
        elif any(ch.isspace() for ch in tok):
            parts.append(f'"{tok}"')
        else:
            parts.append(tok)
    return " ".join(parts)


def main(argv=None, runner=None, out=None) -> int:
    """runner 可注入（测试替身/非 Windows 冒烟）；out 注入输出收集器。"""
    emit = out if out is not None else print
    parser = argparse.ArgumentParser(
        prog="install_daily_driver.bat",
        description="注册/卸载 ZKC 每日 E1 驱动的 Windows 计划任务",
    )
    parser.add_argument("--dry-run", action="store_true", help="只预览命令，不注册")
    parser.add_argument("--uninstall", action="store_true", help="删除同名计划任务")
    parser.add_argument("--time", default=DEFAULT_TIME, help="每日触发时间 HH:MM，默认 23:50")
    parser.add_argument("--task-name", default=DEFAULT_TASK_NAME, help="计划任务名")
    try:
        args, unknown = parser.parse_known_args(argv)
    except SystemExit as exc:  # --help 等
        return int(exc.code or 0)
    if unknown:
        emit(f"未知选项: {' '.join(unknown)}")
        return 2

    paths = resolve_paths()
    try:
        if args.uninstall:
            cmd = build_unregister_command(args.task_name)
        else:
            cmd = build_register_command(paths["wrapper"], args.task_name, args.time)
    except ValueError as exc:
        emit(f"✗ 参数错误: {exc}")
        return 2

    emit("解析到：")
    emit(f"  PYTHON        = {paths['python']}")
    emit(f"  PROJECT_ROOT  = {paths['project_root']}")
    emit(f"  驱动包装      = {paths['wrapper']}")
    emit(f"  任务名 / 时间 = {args.task_name} / {args.time if not args.uninstall else '(卸载)'}")
    emit("")
    emit("将执行：" if args.dry_run else "执行：")
    emit(f"  {format_command(cmd)}")
    emit("")

    if args.dry_run:
        emit("（--dry-run，未注册 / 未删除任何计划任务）")
        return 0

    run = runner if runner is not None else subprocess.run
    try:
        proc = run(cmd, check=False)
    except (FileNotFoundError, OSError) as exc:
        emit(f"✗ 无法执行 schtasks（仅 Windows 可用）: {exc}")
        emit("  可用 --dry-run 预览命令，并在 Windows 上执行真实注册。")
        return 3

    rc = int(getattr(proc, "returncode", 0) or 0)
    if rc != 0:
        emit(f"✗ schtasks 返回 {rc}；检查是否在 Windows、任务名权限与时间格式。")
        return rc

    if args.uninstall:
        emit(f"✓ 已删除计划任务 {args.task_name}")
    else:
        emit(f"✓ 已注册每日 {args.time} 自动跑 真值收口 + E1 仪表。")
        emit("  仅自动化收口 + 仪表；复审标注(decide)仍须人工，不在此任务内。")
        emit(f"  日志：{paths['log']}（JSONL）")
        emit("  卸载：scripts\\install_daily_driver.bat --uninstall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

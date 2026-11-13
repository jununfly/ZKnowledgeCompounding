#!/usr/bin/env bash
# ZKC 每日 E1 驱动 · macOS launchd 安装脚本（Risk A2 解决：消除 plist 里的 python/路径占位符摩擦）。
#
# 用法：
#   scripts/install_daily_driver.sh [PYTHON] [--dry-run]
#     PYTHON     可选：显式 python 解释器绝对路径（须含 zkc 依赖的 venv python）。
#                省略时按优先级自动探测：<仓库>/.venv/bin/python → <仓库>/venv/bin/python → python3。
#     --dry-run  只打印将写入的 plist 与解析到的路径，不安装、不 load。
#
# 行为：
#   1) 解析真实 PYTHON 与 PROJECT_ROOT（仓库根 = 脚本所在目录的父目录）；
#   2) 读取 scripts/launchd/com.zkc.daily-e1.plist 模板，替换 __PYTHON__ / __PROJECT_ROOT__；
#   3) 写入 ~/Library/LaunchAgents/com.zkc.daily-e1.plist 并 launchctl load（或 bootstrap）。
#
# 卸载：launchctl unload ~/Library/LaunchAgents/com.zkc.daily-e1.plist && rm 该文件
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$SCRIPT_DIR/launchd/com.zkc.daily-e1.plist"
DEST="$HOME/Library/LaunchAgents/com.zkc.daily-e1.plist"
DRY_RUN=0
PYTHON=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --*) echo "未知选项: $arg" >&2; exit 2 ;;
    *) PYTHON="$arg" ;;
  esac
done

# 若未显式给 PYTHON，按优先级探测
if [ -z "$PYTHON" ]; then
  if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/.venv/bin/python"
  elif [ -x "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/venv/bin/python"
  else
    PYTHON="$(command -v python3 || command -v python)"
  fi
fi

if [ ! -x "$PYTHON" ]; then
  echo "✗ 解析到的 python 不可执行: $PYTHON" >&2
  exit 1
fi
if [ ! -f "$TEMPLATE" ]; then
  echo "✗ 找不到 plist 模板: $TEMPLATE" >&2
  exit 1
fi

# 渲染：替换占位符（用 | 作分隔符避免路径斜杠冲突）
RENDERED="$(sed -e "s|__PYTHON__|$PYTHON|g" -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" "$TEMPLATE")"

echo "解析到："
echo "  PYTHON        = $PYTHON"
echo "  PROJECT_ROOT  = $PROJECT_ROOT"
echo "  模板          = $TEMPLATE"
echo "  目标 plist    = $DEST"
echo

if [ "$DRY_RUN" -eq 1 ]; then
  echo "========== 将写入的 plist（--dry-run，未安装）=========="
  echo "$RENDERED"
  echo "======================================================="
  exit 0
fi

mkdir -p "$(dirname "$DEST")"
printf '%s\n' "$RENDERED" > "$DEST"
echo "✓ 已写入 $DEST"

# 先卸后装，避免重复 Label 报错；优先 bootstrap（macOS 13+），回退 load
launchctl unload "$DEST" 2>/dev/null || true
if launchctl bootstrap "gui/$(id -u)" "$DEST" 2>/dev/null; then
  echo "✓ launchctl bootstrap 成功"
elif launchctl load "$DEST" 2>/dev/null; then
  echo "✓ launchctl load 成功（bootstrap 不可用，已回退）"
else
  echo "⚠ launchctl 注册失败（可能需要 GUI session 或权限）。plist 已就位，可手动："
  echo "    launchctl load $DEST"
fi
echo
echo "完成。每日 23:50 自动跑 真值收口 + E1 仪表。"
echo "日志： $PROJECT_ROOT/logs/e1_daily.log（JSONL）"
echo "卸载： launchctl unload $DEST && rm $DEST"

#!/usr/bin/env bash
# ZKC 每日 E1 驱动 · macOS launchd 安装脚本（Risk A2 解决：消除 plist 里的 python/路径占位符摩擦）。
#
# 用法：
#   scripts/install_daily_driver.sh [PYTHON] [--dry-run] [--embed]
#     PYTHON     可选：显式 python 解释器绝对路径（须含 zkc 依赖的 venv python）。
#                省略时按优先级自动探测：<仓库>/.venv/bin/python → <仓库>/venv/bin/python → python3。
#     --dry-run  只打印将写入的 plist 与解析到的路径，不安装、不 load。
#     --embed    安装「每日补向量」并列条目（com.zkc.daily-embed，23:55），
#                而不是默认的 E1 驱动条目；两个条目互不覆盖、可同时安装。
#
# 行为：
#   1) 解析真实 PYTHON 与 PROJECT_ROOT（仓库根 = 脚本所在目录的父目录）；
#   2) 按 --embed 选择对应 plist 模板，替换 __PYTHON__ / __PROJECT_ROOT__；
#   3) 写入 ~/Library/LaunchAgents/<label>.plist 并 launchctl load（或 bootstrap）。
#
# 卸载（按条目分别执行）：
#   launchctl unload ~/Library/LaunchAgents/com.zkc.daily-e1.plist && rm 该文件
#   launchctl unload ~/Library/LaunchAgents/com.zkc.daily-embed.plist && rm 该文件
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DRY_RUN=0
TASK_KIND="e1"
PYTHON=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --embed) TASK_KIND="embed" ;;
    --*) echo "未知选项: $arg" >&2; exit 2 ;;
    *) PYTHON="$arg" ;;
  esac
done

# 两个条目各自独立：不同 Label / 模板 / 目标 plist，互不覆盖
if [ "$TASK_KIND" = "embed" ]; then
  TEMPLATE="$SCRIPT_DIR/launchd/com.zkc.daily-embed.plist"
  DEST="$HOME/Library/LaunchAgents/com.zkc.daily-embed.plist"
else
  TEMPLATE="$SCRIPT_DIR/launchd/com.zkc.daily-e1.plist"
  DEST="$HOME/Library/LaunchAgents/com.zkc.daily-e1.plist"
fi

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
if [ "$TASK_KIND" = "embed" ]; then
  LABEL="com.zkc.daily-embed"
else
  LABEL="com.zkc.daily-e1"
fi
launchctl unload "$DEST" 2>/dev/null || true
REGISTERED=0
if launchctl bootstrap "gui/$(id -u)" "$DEST" 2>/dev/null; then
  REGISTERED=1
  echo "✓ launchctl bootstrap 命令返回成功"
elif launchctl load "$DEST" 2>/dev/null; then
  REGISTERED=1
  echo "✓ launchctl load 命令返回成功（bootstrap 不可用，已回退）"
else
  echo "⚠ launchctl 注册命令失败（可能需要 GUI session 或权限）。"
fi

# 命令退出码 0 不等于服务真的进了 domain（沙箱内 load 会静默落到错误 domain）。
# 必须回查 gui domain，否则会把「plist 写了但没生效」误报成「已挂上」。
if ! launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  echo
  echo "✗ 校验失败：${LABEL} 不在 gui/$(id -u) domain，任务当前未真正生效。"
  echo "  plist 已写入 ${DEST}（用户下次登录时 LaunchAgents 会自动加载）。"
  echo "  若要立即生效，请在 GUI 会话（非沙箱终端）执行："
  echo "    launchctl bootstrap gui/$(id -u) ${DEST}"
  echo "  注册命令返回码：${REGISTERED}（1=命令成功但服务未加载，属环境限制，非脚本逻辑错误）"
  exit 1
fi
echo "✓ 已回查确认 ${LABEL} 在 gui/$(id -u) domain 中加载"
echo
if [ "$TASK_KIND" = "embed" ]; then
  echo "完成。每日 23:55 自动跑 zkc embed（补向量，独立于 E1 驱动）。"
  echo "日志： $PROJECT_ROOT/logs/daily_embed.out / daily_embed.err"
  echo "E1 驱动仍是两件机械事，未被本条目改动（ADR-0007）。"
else
  echo "完成。每日 23:50 自动跑 真值收口 + E1 仪表。"
  echo "日志： $PROJECT_ROOT/logs/e1_daily.log（JSONL）"
  echo "补向量为并列条目：scripts/install_daily_driver.sh --embed（23:55）。"
fi
echo "卸载： launchctl unload $DEST && rm $DEST"

@echo off
REM ZKC 每日 E1 驱动（Windows 包装）。仅自动化"真值收口 + 跑仪表"；复审标注仍须人工。
REM 前提：python 含 zkc 依赖；DATABASE_URL 等环境变量与 make serve 同库。
setlocal
set SCRIPT_DIR=%~dp0
REM 优先用仓库 venv，否则回退 PATH 上的 python
if exist "%SCRIPT_DIR%..\.venv\Scripts\python.exe" (
  set "PY=%SCRIPT_DIR%..\.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%..\venv\Scripts\python.exe" (
  set "PY=%SCRIPT_DIR%..\venv\Scripts\python.exe"
) else (
  set "PY=python"
)
set ZKC_BASE=http://127.0.0.1:8000
set ZKC_STORAGE=pg
set ZKC_MODE=direct
"%PY%" "%SCRIPT_DIR%daily_e1_driver.py"
exit /b %ERRORLEVEL%

REM ---- 注册/卸载每日计划任务（在仓库根执行一次）----
REM 注册脚本：scripts\install_daily_driver.bat（对齐 macOS install_daily_driver.sh）
REM   scripts\install_daily_driver.bat --dry-run    预览命令，不注册
REM   scripts\install_daily_driver.bat             注册每日 23:50
REM   scripts\install_daily_driver.bat --uninstall 卸载
REM 本包装由计划任务直接调用；真实 python/项目根由安装脚本按脚本位置解析，勿用调用方 cwd 拼路径。
REM 日志：<仓库>\logs\e1_daily.log（JSONL）。

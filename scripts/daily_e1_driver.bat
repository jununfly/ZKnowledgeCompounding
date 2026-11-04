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
"%PY%" "%SCRIPT_DIR%daily_e1_driver.py"
exit /b %ERRORLEVEL%

REM ---- 注册为每日计划任务（管理员 CMD 执行一次）----
REM schtasks /create /tn "ZKC Daily E1" /tr "\"%PY%\" \"%CD%\scripts\daily_e1_driver.py\"" /sc daily /st 23:50
REM 日志：<仓库>\logs\e1_daily.log（JSONL）。

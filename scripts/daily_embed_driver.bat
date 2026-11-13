@echo off
REM ZKC 每日补向量（Windows 计划任务包装）—— 与 daily_e1_driver.bat 并列的独立条目。
REM ADR-0007 的「两件机械事」不变：本包装只跑 zkc embed，不写真值收口、不碰标注埋点。
REM 前提：python 含 zkc 依赖（make setup 已 editable 安装）；PG 可达。
REM 注册：scripts\install_daily_driver.bat --embed --dry-run / --embed
setlocal
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%..\.venv\Scripts\python.exe" (
  set "PY=%SCRIPT_DIR%..\.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%..\venv\Scripts\python.exe" (
  set "PY=%SCRIPT_DIR%..\venv\Scripts\python.exe"
) else (
  set "PY=python"
)
set ZKC_STORAGE=pg
"%PY%" -m zkc.cli embed
exit /b %ERRORLEVEL%

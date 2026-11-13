@echo off
REM ZKC 每日 E1 驱动 · Windows schtasks 安装脚本（对齐 macOS install_daily_driver.sh）。
REM 只注册「真值收口 + E1 仪表」；复审标注(decide)仍须人工（ADR-0007 fork 1）。
REM
REM 用法（在仓库根或任意 cwd 均可，路径由 Python 侧按脚本位置解析）：
REM   scripts\install_daily_driver.bat --dry-run       预览将执行的 schtasks 命令，不注册
REM   scripts\install_daily_driver.bat                 注册每日 23:50
REM   scripts\install_daily_driver.bat --uninstall     删除计划任务
REM   scripts\install_daily_driver.bat --time 07:15    改触发时间
REM   scripts\install_daily_driver.bat --embed --dry-run 预览并列的每日补向量任务
REM   scripts\install_daily_driver.bat --embed         注册每日 23:55 的 zkc embed
REM   scripts\install_daily_driver.bat --embed --uninstall 删除补向量任务
REM
REM 退出码：0 成功 / 1 schtasks 失败 / 2 参数错误 / 3 找不到 schtasks（非 Windows）。
setlocal
set "SCRIPT_DIR=%~dp0"
REM 优先用仓库 venv，否则回退 PATH 上的 python（与 daily_e1_driver.bat 一致）
if exist "%SCRIPT_DIR%..\.venv\Scripts\python.exe" (
  set "PY=%SCRIPT_DIR%..\.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%..\venv\Scripts\python.exe" (
  set "PY=%SCRIPT_DIR%..\venv\Scripts\python.exe"
) else (
  set "PY=python"
)
"%PY%" "%SCRIPT_DIR%daily_driver_schedule.py" %*
exit /b %ERRORLEVEL%

"""1-21 TDD · Windows schtasks 注册脚本（对齐 macOS install_daily_driver.sh）。

背景：ADR-0007 写「跨平台调度：macOS launchd plist + Windows schtasks(.bat 包装)」，
但实物只有 macOS 安装脚本；`daily_e1_driver.bat:20` 仅是一句 REM 注释形式的
schtasks 示例，且用了 `%CD%` 错误路径 —— Windows 侧没有任何注册脚本。

测试 seam：`scripts/daily_driver_schedule.py` 的纯渲染函数 + 可注入 runner 的 main。
本机是 macOS，无法实机跑 schtasks，因此断言的是「命令契约 + dry-run 绝不注册」，
真实注册表行为留待 Windows 侧复核（不伪造验证证据）。

Seam：build_task_action / build_register_command / build_unregister_command / main。
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import daily_driver_schedule as sched  # noqa: E402


class ScheduleRenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.wrapper = str(ROOT / "scripts" / "daily_e1_driver.bat")
        self.path_with_space = r"C:\Users\zj\My Projects\ZKC\scripts\daily_e1_driver.bat"

    def test_task_action_quotes_path_with_spaces(self) -> None:
        """/tr 动作路径必须自带外层双引号，否则带空格路径会被 schtasks 截断。"""
        action = sched.build_task_action(self.path_with_space)
        self.assertTrue(action.startswith('"'))
        self.assertTrue(action.endswith('"'))
        self.assertIn("daily_e1_driver.bat", action)
        self.assertNotIn("__PROJECT_ROOT__", action)
        self.assertNotIn("%CD%", action)

    def test_register_command_contract(self) -> None:
        """注册命令对齐 macOS 契约：/tn + /sc daily + /st 23:50 + /f 幂等覆盖。"""
        cmd = sched.build_register_command(self.wrapper)
        self.assertEqual(cmd[0], "schtasks")
        self.assertIn("/create", cmd)
        self.assertEqual(cmd[cmd.index("/tn") + 1], sched.DEFAULT_TASK_NAME)
        self.assertEqual(cmd[cmd.index("/sc") + 1], "daily")
        self.assertEqual(cmd[cmd.index("/st") + 1], sched.DEFAULT_TIME)
        self.assertIn("/f", cmd, "缺 /f 时重复安装会报『任务已存在』，破坏幂等")
        self.assertEqual(cmd[cmd.index("/tr") + 1], sched.build_task_action(self.wrapper))
        self.assertNotIn("daily_e1_driver.py", " ".join(cmd),
                         "任务动作应指向 .bat 包装，避免 /tr 多参数引号嵌套")

    def test_custom_time_and_task_name(self) -> None:
        cmd = sched.build_register_command(
            self.wrapper, task_name="ZKC Custom", at="07:15")
        self.assertEqual(cmd[cmd.index("/tn") + 1], "ZKC Custom")
        self.assertEqual(cmd[cmd.index("/st") + 1], "07:15")

    def test_unregister_command_contract(self) -> None:
        cmd = sched.build_unregister_command()
        self.assertEqual(cmd[0], "schtasks")
        self.assertIn("/delete", cmd)
        self.assertEqual(cmd[cmd.index("/tn") + 1], sched.DEFAULT_TASK_NAME)
        self.assertIn("/f", cmd)
        self.assertNotIn("/create", cmd)

    def test_invalid_time_rejected(self) -> None:
        with self.assertRaises(ValueError):
            sched.build_register_command(self.wrapper, at="25:99")
        with self.assertRaises(ValueError):
            sched.build_register_command(self.wrapper, at="23-50")


class ScheduleMainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.silent = lambda _s: None

    def test_dry_run_never_calls_schtasks(self) -> None:
        """--dry-run 只预览，绝不注册（macOS 侧也可安全执行）。"""
        runner = mock.Mock()
        rc = sched.main(["--dry-run"], runner=runner, out=self.silent)
        self.assertEqual(rc, 0)
        runner.assert_not_called()

    def test_dry_run_summary_has_resolved_paths(self) -> None:
        out = []
        runner = mock.Mock()
        rc = sched.main(["--dry-run"], runner=runner, out=out.append)
        text = "".join(out)
        self.assertEqual(rc, 0)
        self.assertIn("PROJECT_ROOT", text)
        self.assertIn("schtasks", text)
        self.assertIn("/create", text)
        self.assertNotIn("__PYTHON__", text)
        self.assertNotIn("__PROJECT_ROOT__", text)
        self.assertNotIn("%CD%", text)

    def test_register_calls_schtasks_once_with_rendered_command(self) -> None:
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        rc = sched.main([], runner=runner, out=self.silent)
        self.assertEqual(rc, 0)
        self.assertEqual(runner.call_count, 1)
        cmd = runner.call_args.args[0]
        self.assertEqual(cmd[0], "schtasks")
        self.assertIn("/create", cmd)

    def test_register_propagates_schtasks_failure(self) -> None:
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 1))
        self.assertEqual(sched.main([], runner=runner, out=self.silent), 1)

    def test_missing_schtasks_is_explicit_not_crash(self) -> None:
        """非 Windows 环境找不到 schtasks 时给明确退出码，不抛裸异常。"""
        def boom(*args, **kwargs):
            raise FileNotFoundError("schtasks")

        self.assertEqual(sched.main([], runner=boom, out=self.silent), 3)

    def test_uninstall_flag_uses_delete_command(self) -> None:
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        self.assertEqual(sched.main(["--uninstall"], runner=runner, out=self.silent), 0)
        cmd = runner.call_args.args[0]
        self.assertIn("/delete", cmd)
        self.assertNotIn("/create", cmd)

    def test_unknown_option_rejected(self) -> None:
        runner = mock.Mock()
        self.assertEqual(sched.main(["--wat"], runner=runner, out=self.silent), 2)
        runner.assert_not_called()


class BatWrapperContractTest(unittest.TestCase):
    """静态契约：.bat 薄壳与旧包装的接线（本机无法执行 .bat）。"""

    def test_install_bat_is_thin_wrapper_over_python_module(self) -> None:
        text = (ROOT / "scripts" / "install_daily_driver.bat").read_text(encoding="utf-8")
        self.assertIn("daily_driver_schedule.py", text)
        self.assertIn("%*", text, "必须把 --dry-run / --uninstall 等参数透传")
        self.assertIn(".venv\\Scripts\\python.exe", text, "对齐 macOS：venv python 优先")
        self.assertIn("exit /b %ERRORLEVEL%", text)

    def test_old_bat_no_longer_has_placeholder_schtasks_comment(self) -> None:
        text = (ROOT / "scripts" / "daily_e1_driver.bat").read_text(encoding="utf-8")
        self.assertNotIn("REM schtasks /create", text,
                         "旧的 REM 占位示例应被真实注册脚本指引取代")
        self.assertNotIn("%CD%", text, "%CD% 是调用方 cwd，不是仓库根，路径会错")
        self.assertIn("install_daily_driver.bat", text)
        self.assertIn("ZKC_MODE=direct", text, "对齐 macOS plist 的 direct 默认")


if __name__ == "__main__":
    unittest.main()

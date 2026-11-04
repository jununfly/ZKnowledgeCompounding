"""1-21 TDD · zj-zkc-daily skill 纳管同步脚本（zj 拍板：repo canonical + 安装脚本）。

背景：该 skill 原本只在 `~/.workbuddy/skills/zj-zkc-daily/SKILL.md`，不在 git、无备份。
1-21 决定把 canonical 迁进 ZKC 仓库 `skills/`，运行副本由安装脚本同步生成。

安全边界（必须被测试守住）：
  - 目标默认是 home 下的用户级副本；脚本**绝不删除目录**，只覆盖单个 SKILL.md；
  - 内容有分歧时默认拒绝覆盖，--force 才覆盖，且覆盖前留 .bak 备份；
  - --dry-run / --check 绝不写任何文件；
  - 目标不能就是 canonical 自身（防自覆盖）。

Seam：plan_sync / sync / main（canonical、target、home 目录均可注入，测试只用临时目录）。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import install_harness_skill as installer  # noqa: E402


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.silent = lambda _s: None
        self.base = Path(self.tmp.name)
        self.canonical = self.base / "repo" / "skills" / "zj-zkc-daily" / "SKILL.md"
        self.canonical.parent.mkdir(parents=True)
        self.canonical.write_text("# canonical v1\n", encoding="utf-8")
        self.target = self.base / "home" / ".workbuddy" / "skills" / "zj-zkc-daily" / "SKILL.md"
        self.bak = self.target.with_suffix(".md.bak")

    def test_repo_canonical_exists_and_keeps_hitl_guard(self) -> None:
        """仓库内 canonical 必须存在且保留 human-in-the-loop 硬约束（防同步丢约束）。"""
        text = (ROOT / "skills" / "zj-zkc-daily" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("human-in-the-loop", text)
        self.assertIn("绝不", text)
        self.assertIn("install_harness_skill.py", text)
        self.assertIn("ADR-0007", text)

    def test_plan_detects_missing_target(self) -> None:
        p = installer.plan_sync(self.canonical, self.target)
        self.assertFalse(p["exists"])
        self.assertTrue(p["drift"])
        self.assertEqual(p["action"], "create")

    def test_creates_target_when_missing(self) -> None:
        r = installer.sync(self.canonical, self.target)
        self.assertEqual(r["action"], "created")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# canonical v1\n")
        self.assertTrue(self.target.parent.is_dir())

    def test_unchanged_when_identical(self) -> None:
        installer.sync(self.canonical, self.target)
        r = installer.sync(self.canonical, self.target)
        self.assertEqual(r["action"], "unchanged")
        self.assertIsNone(r["backup"])

    def test_refuses_overwrite_of_divergent_target_by_default(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_text("# hand-edited local copy\n", encoding="utf-8")
        r = installer.sync(self.canonical, self.target)
        self.assertEqual(r["action"], "refused")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# hand-edited local copy\n")
        self.assertFalse(self.bak.exists())

    def test_force_overwrites_with_backup(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_text("# hand-edited local copy\n", encoding="utf-8")
        r = installer.sync(self.canonical, self.target, force=True)
        self.assertEqual(r["action"], "updated")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# canonical v1\n")
        self.assertEqual(self.bak.read_text(encoding="utf-8"), "# hand-edited local copy\n")
        self.assertEqual(r["backup"], str(self.bak))

    def test_dry_run_never_writes(self) -> None:
        r = installer.sync(self.canonical, self.target, dry_run=True)
        self.assertIn(r["action"], ("would-create", "would-update"))
        self.assertFalse(self.target.exists())

        self.target.parent.mkdir(parents=True)
        self.target.write_text("# local\n", encoding="utf-8")
        installer.sync(self.canonical, self.target, dry_run=True, force=True)
        self.assertEqual(self.target.read_text(encoding="utf-8"), "# local\n")

    def test_check_is_read_only(self) -> None:
        self.assertEqual(installer.main(
            ["--check", "--canonical", str(self.canonical), "--target", str(self.target)], out=self.silent), 1)
        self.assertFalse(self.target.exists())
        installer.sync(self.canonical, self.target)
        self.assertEqual(installer.main(
            ["--check", "--canonical", str(self.canonical), "--target", str(self.target)], out=self.silent), 0)

    def test_main_dry_run_exit_zero_and_no_write(self) -> None:
        self.assertEqual(installer.main(
            ["--dry-run", "--canonical", str(self.canonical), "--target", str(self.target)], out=self.silent), 0)
        self.assertFalse(self.target.exists())

    def test_main_refusal_exit_one(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_text("# local\n", encoding="utf-8")
        self.assertEqual(installer.main(
            ["--canonical", str(self.canonical), "--target", str(self.target)], out=self.silent), 1)

    def test_target_equal_canonical_rejected(self) -> None:
        with self.assertRaises(ValueError):
            installer.plan_sync(self.canonical, self.canonical)
        self.assertEqual(installer.main(
            ["--canonical", str(self.canonical), "--target", str(self.canonical)],
             out=self.silent), 2)

    def test_missing_canonical_rejected(self) -> None:
        missing = self.base / "nope" / "SKILL.md"
        self.assertEqual(installer.main(
            ["--canonical", str(missing), "--target", str(self.target)], out=self.silent), 2)

    def test_no_recursive_delete_helper(self) -> None:
        """安全边界：模块不得提供/调用目录删除（不碰 home 下的目录）。"""
        import inspect
        src = inspect.getsource(installer)
        self.assertNotIn("rmtree", src)
        self.assertNotIn("shutil.rmtree", src)


if __name__ == "__main__":
    unittest.main()

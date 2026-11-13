"""过程权威边界门禁（scripts/zkc_authority_check.py）的回归测试。

测试一律在临时 fixture 里动态构造「过程产物相对路径」，避免测试源码自身
成为被扫描对象时携带触发串（治理记录行为不能自引入新泄漏）。

判定语义与上游 zj-roadmap-driven 的 authority-check 对齐：只剪掉过程态目录 /
carrier / 带权威信封的视图，判定规则一条都不放宽。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "zkc_authority_check.py"
PLAN_NAME = "probe.md"

# 与上游 roadmap.py 的 ROADMAP_AUTHORITY_ENVELOPE 逐字一致（自包含，不 import skill）。
ENVELOPE = """<!-- zj-roadmap-authority/v1
role: process-state
durable-citation: forbidden
promote-via: ADR|design|contract|runtime-evidence
-->"""
# 单文件 carrier 的最小结构签名：title / version / nodes / metadata 齐备，
# 且每个节点都带 status。
CARRIER = {
    "title": "fixture roadmap",
    "version": 1,
    "metadata": {},
    "nodes": {"1": {"status": "pending"}},
}
CARRIER_PATH = "roadmap.json"
VIEW_PATH = "ROADMAP.md"
PRUNED_DIRS = (
    ".git",
    ".workbuddy/memory",
    "node_modules/pkg",
    "tmp",
    "__pycache__",
)


def plan_target(name: str = PLAN_NAME) -> str:
    """动态拼出 fixture 里的过程产物相对路径。"""
    return (Path("docs") / "plans" / name).as_posix()


def make_project(root: Path, files: dict[str, str] | None = None) -> None:
    plans = root / "docs" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    (plans / PLAN_NAME).write_text("# transient process artifact\n", encoding="utf-8")
    for relative, body in (files or {}).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")


def citation(body: str | None = None) -> str:
    """一行会触发门禁的引用，正文可替换。"""
    return (body or "see ") + "`" + plan_target() + "`\n"


def run_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def carrier_with(note: str) -> str:
    data = dict(CARRIER)
    data["description"] = note
    return json.dumps(data, ensure_ascii=False) + "\n"


class AuthorityCheckTests(unittest.TestCase):
    def test_clean_project_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, {"docs/guide.md": "# guide\nno citation here\n"})
            result = run_check(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 unresolved", result.stdout)
        self.assertIn("pruned dirs", result.stdout)

    def test_direct_citation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, {"docs/guide.md": citation()})
            result = run_check(root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("E_PROCESS_AUTHORITY_LEAK", result.stdout + result.stderr)
        self.assertIn("docs/guide.md:1", result.stdout + result.stderr)

    def test_markdown_link_citation_fails(self) -> None:
        """复刻原门禁的 markdown link 判定，不能被 wrapper 削弱。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            link = "[decisions](" + plan_target().replace("docs/", "", 1) + ")"
            make_project(root, {"docs/guide.md": link + "\n"})
            result = run_check(root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("E_PROCESS_AUTHORITY_LEAK", result.stdout + result.stderr)

    def test_roadmap_completion_claim_fails(self) -> None:
        """「节点完成即证据」同样属于过程权威泄漏，判定规则必须复刻。"""
        claim = "proof: roadmap " + "node 1-1 is completed"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, {"docs/guide.md": claim + "\n"})
            result = run_check(root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("E_PROCESS_AUTHORITY_LEAK", result.stdout + result.stderr)

    def test_process_state_directories_are_pruned(self) -> None:
        """过程态目录整类不扫：每新增一天日志都不该产生新的假阳性。"""
        for directory in PRUNED_DIRS:
            with self.subTest(directory=directory):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    make_project(root, {f"{directory}/log.md": citation("- ")})
                    result = run_check(root)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("0 unresolved", result.stdout)

    def test_pruning_does_not_weaken_the_gate(self) -> None:
        """放宽扫描范围不得削弱判定：真泄漏仍 fail，且过程日志不被报成泄漏。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(
                root,
                {
                    ".workbuddy/memory/2026-11-05.md": citation("- "),
                    "docs/guide.md": citation("see "),
                },
            )
            result = run_check(root)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertIn("E_PROCESS_AUTHORITY_LEAK docs/guide.md:1", output)
        self.assertNotIn("E_PROCESS_AUTHORITY_LEAK .workbuddy", output)

    def test_roadmap_carrier_is_skipped(self) -> None:
        """carrier 自述编排来源属于过程态，靠结构签名识别，不靠白名单枚举。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, {CARRIER_PATH: carrier_with(plan_target())})
            result = run_check(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 unresolved", result.stdout)
        self.assertIn(CARRIER_PATH, result.stdout)

    def test_authority_envelope_view_is_skipped(self) -> None:
        """render / section 产出的视图带权威信封，属过程态。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = ENVELOPE + "\n\n" + citation("- ")
            make_project(root, {VIEW_PATH: body})
            result = run_check(root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 unresolved", result.stdout)
        self.assertIn(VIEW_PATH, result.stdout)

    def test_partial_envelope_does_not_opt_out(self) -> None:
        """只写一行标记、没有完整信封的普通文档不得借机逃过门禁。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "<!-- zj-roadmap-authority/v1\n" + citation("- ")
            make_project(root, {VIEW_PATH: body})
            result = run_check(root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("E_PROCESS_AUTHORITY_LEAK", result.stdout + result.stderr)

    def test_generic_nodes_json_cannot_opt_out(self) -> None:
        """普通 nodes.json 不能靠长出 nodes/status 结构就逃过门禁。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = json.dumps(
                {"nodes": {"1": {"status": "pending"}}, "note": plan_target()},
                ensure_ascii=False,
            ) + "\n"
            make_project(root, {"docs/nodes.json": body})
            result = run_check(root)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("E_PROCESS_AUTHORITY_LEAK docs/nodes.json:1", result.stdout)

    def test_skipped_process_state_files_are_reported(self) -> None:
        """跳过必须逐条可审计，不能静默吞掉（替代原 STALE 防线）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(
                root,
                {
                    CARRIER_PATH: carrier_with(plan_target()),
                    VIEW_PATH: ENVELOPE + "\n\n" + citation("- "),
                },
            )
            result = run_check(root)
        output = result.stdout
        self.assertEqual(result.returncode, 0, output + result.stderr)
        self.assertIn("skipped 2 process-state", output)
        self.assertIn(CARRIER_PATH, output)
        self.assertIn(VIEW_PATH, output)

    def test_real_repository_has_no_unresolved_leaks(self) -> None:
        """守门回归：本仓库任何新泄漏都必须让 CI fail。"""
        result = run_check(ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("0 unresolved", result.stdout)


if __name__ == "__main__":
    unittest.main()

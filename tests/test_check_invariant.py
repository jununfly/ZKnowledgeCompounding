"""ADR-0005 rec-avoid 不变式 CI 谓词的 TDD 验收。

两条断言：① claim 落库仍受 meta_claim.evidence_refs NOT NULL 约束；
② 任何 feature 不得提供关闭 decay / attention 的全局开关。
fixture 走临时目录，缺陷态红 / 修复态绿；真实仓库必须 clean。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_invariant.py"

_spec = importlib.util.spec_from_file_location("zkc_check_invariant", SCRIPT)
ci = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(ci)

MIGRATION = """-- baseline
CREATE TABLE public.meta_claim (
    id uuid PRIMARY KEY,
    statement text NOT NULL,
    evidence_refs uuid[] NOT NULL,
    produced_by uuid
);
"""


def _fixture(*, migration=MIGRATION, sources=None):
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    (root / "migrations").mkdir()
    (root / "src" / "zkc").mkdir(parents=True)
    (root / "migrations" / "0001_baseline.up.sql").write_text(migration, encoding="utf-8")
    for name, body in (sources or {"tuning.py": "VALUE = 1\n"}).items():
        (root / "src" / "zkc" / name).write_text(body, encoding="utf-8")
    return tmp, root


class InvariantPredicateTest(unittest.TestCase):
    def test_clean_fixture_passes(self):
        tmp, root = _fixture()
        with tmp:
            lines, violations = ci.evaluate(root)
            self.assertEqual(violations, 0)
            self.assertTrue(any("P1" in line for line in lines))
            self.assertTrue(any("P2" in line for line in lines))

    def test_missing_not_null_is_detected(self):
        bad = MIGRATION.replace("evidence_refs uuid[] NOT NULL", "evidence_refs uuid[]")
        tmp, root = _fixture(migration=bad)
        with tmp:
            _lines, violations = ci.evaluate(root)
            self.assertEqual(violations, 1)

    def test_missing_meta_claim_table_is_detected(self):
        tmp, root = _fixture(migration="CREATE TABLE public.node (id uuid);\n")
        with tmp:
            _lines, violations = ci.evaluate(root)
            self.assertGreaterEqual(violations, 1)

    def test_global_decay_kill_switch_is_detected(self):
        tmp, root = _fixture(sources={"tuning.py": "DECAY_ENABLED = False\n"})
        with tmp:
            lines, violations = ci.evaluate(root)
            self.assertEqual(violations, 1)
            self.assertTrue(any("DECAY_ENABLED" in line for line in lines))

    def test_env_based_attention_kill_switch_is_detected(self):
        tmp, root = _fixture(sources={
            "scheduling.py": 'import os\nATTENTION_ENABLED = os.environ.get("ZKC_DISABLE_ATTENTION") != "1"\n',
        })
        with tmp:
            _lines, violations = ci.evaluate(root)
            self.assertGreaterEqual(violations, 1)

    def test_comment_mentioning_switch_is_not_flagged(self):
        tmp, root = _fixture(sources={
            "tuning.py": "# 禁止引入 DECAY_ENABLED / DISABLE_ATTENTION 全局开关\nVALUE = 1\n",
        })
        with tmp:
            _lines, violations = ci.evaluate(root)
            self.assertEqual(violations, 0)

    def test_normal_decay_parameters_are_not_flagged(self):
        tmp, root = _fixture(sources={
            "decay.py": "DECAY_FUNCTION = 'linear'\nSURFACE_THRESHOLD = 0.6\nATTENTION_BUDGET_PER_DAY = 3.0\n",
        })
        with tmp:
            _lines, violations = ci.evaluate(root)
            self.assertEqual(violations, 0)

    def test_real_repository_is_clean(self):
        lines, violations = ci.evaluate(ROOT)
        self.assertEqual(violations, 0, "\n".join(lines))
        self.assertTrue(any("0001" in line for line in lines))

    def test_cli_exit_code_clean_and_defect(self):
        ok = subprocess.run([sys.executable, str(SCRIPT), str(ROOT)],
                           text=True, capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("0 invariant violations", ok.stdout)

        tmp, root = _fixture(sources={"tuning.py": "DISABLE_DECAY = True\n"})
        with tmp:
            bad = subprocess.run([sys.executable, str(SCRIPT), str(root)],
                                text=True, capture_output=True)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("E_INVARIANT", bad.stdout)

    def test_gate_is_wired_into_ci_and_make(self):
        """守门失联防线：job / Makefile target 被删后本条先红。"""
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("invariant (rec-avoid)", workflow)
        self.assertIn("make invariant", workflow)
        self.assertIn("invariant:", makefile)
        self.assertIn("scripts/check_invariant.py", makefile)


if __name__ == "__main__":
    unittest.main()

"""R8 决策锁 · 编排/路由第三方依赖零引入（guard / characterization 测试）。

R8（LangGraph / Semantic Router 破坏性变更）于 2026-11-06 收口（证据见 docs/risks.md）：架构 §8 已记
「MVP 实装未引入 LangGraph，该上游风险消除」；生产双轨分流为自研
DecisionRouter + LexicalRouter（TF-IDF，embedding-free），零第三方编排/路由依赖，
因此「锁版本」的最强形式是锁死依赖面本身（而非锁一个不存在的版本号）。

本测试把「锁版本清单 + 路由回归测试接入 CI」落成可执行契约：
1. zkc/ 业务代码不得 import langgraph / semantic_router / instructor。
2. requirements.txt 不得声明这三者。
3. tests/test_routing.py 的双信号弃权回归存在，且 CI 经 make test 覆盖。
4. guard 自身对样本文本能检出违规（防止清单/正则失效后假绿）。

若日后真要引入其中任一依赖，本测试变红 —— 这正是设计意图：红 = 重新 open R8，
补齐锁版本清单与路由回归，再评估破坏性变更影响。纯静态扫描，秒级可跑。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZKC = ROOT / "src" / "zkc"
REQ = ROOT / "requirements.txt"
ROUTING_TEST = ROOT / "tests" / "test_routing.py"
CI = ROOT / ".github" / "workflows" / "ci.yml"

FORBIDDEN_MODULES = ("langgraph", "semantic_router", "instructor")
_FORBIDDEN_SET = set(FORBIDDEN_MODULES)
_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
    re.MULTILINE,
)


def _normalize(token: str) -> str:
    """PyPI 包名连字符 / 下划线等价（semantic-router == semantic_router）。"""
    return token.lower().replace("-", "_")


def _requirements_violations(text: str) -> list[str]:
    """按行取首个包名 token（跳过注释与空行），比对禁用清单。"""
    found: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        token = re.split(r"[<>=!~\[;\s]", stripped, maxsplit=1)[0]
        norm = _normalize(token)
        if norm in _FORBIDDEN_SET and norm not in found:
            found.append(norm)
    return found


def _import_violations(text: str) -> list[str]:
    """只认行首 import / from 语句；docstring 里的历史选型留痕不算违规。"""
    found: list[str] = []
    for m in _IMPORT_RE.finditer(text):
        mod = _normalize((m.group(1) or m.group(2)).split(".")[0])
        if mod in _FORBIDDEN_SET and mod not in found:
            found.append(mod)
    return found


class R8OrchestrationGuard(unittest.TestCase):
    def test_guard_detects_sample_violations(self) -> None:
        """guard 自检：样本文本里的违规必须被检出，避免清单/正则失效后假绿。"""
        sample_req = "fastapi\nlanggraph==0.2.0\nsemantic-router>=1.0\ninstructor==1.17.0\n"
        self.assertEqual(
            _requirements_violations(sample_req),
            ["langgraph", "semantic_router", "instructor"],
        )
        sample_py = "from langgraph.graph import StateGraph\nimport instructor\n"
        self.assertEqual(
            _import_violations(sample_py),
            ["langgraph", "instructor"],
        )

    def test_zkc_no_orchestration_imports(self) -> None:
        """zkc/ 业务代码不得 import 编排/路由框架（零依赖不变量）。"""
        violations: list[str] = []
        for path in sorted(ZKC.rglob("*.py")):
            found = _import_violations(path.read_text(encoding="utf-8"))
            for mod in found:
                violations.append(f"{path.relative_to(ROOT)}: {mod}")
        self.assertEqual(
            violations,
            [],
            "R8 锁被破坏：zkc/ 出现编排/路由框架 import，需重新 open R8 并补锁版本清单。\n"
            + "\n".join(violations),
        )

    def test_requirements_excludes_orchestration_deps(self) -> None:
        """依赖面不得声明 langgraph / semantic-router / instructor。"""
        declared = REQ.read_text(encoding="utf-8")
        self.assertEqual(
            _requirements_violations(declared),
            [],
            "R8 锁被破坏：requirements.txt 声明了编排/路由框架，需重新 open R8。",
        )

    def test_routing_regression_is_wired_into_ci(self) -> None:
        """路由回归测试存在，且 CI 的 make test 会跑到它（接线断言）。"""
        self.assertTrue(ROUTING_TEST.exists(), "tests/test_routing.py 必须存在")
        routing_text = ROUTING_TEST.read_text(encoding="utf-8")
        self.assertIn(
            "RouteTextDualSignalTest", routing_text,
            "双信号弃权回归用例缺失（R8 路由回归的核心断言）",
        )
        ci_text = CI.read_text(encoding="utf-8")
        self.assertIn("make test", ci_text, "CI 必须跑 make test 才能覆盖路由回归")
        self.assertIn("unit-no-pg", ci_text, "CI 的无 PG 单测 job 缺失")


if __name__ == "__main__":
    unittest.main()

"""zkc/distill 单测（P3.1 切片1：ZKC 自建蒸馏语义 + provider 无关算子）。

不引入 Ollama/Instructor/LangGraph 重依赖：LLM 调用通过可注入 callable 模拟，
验证蒸馏语义层（每条 claim 须引用≥1 来源）与 seam（可注入 LLM、可单测）。
"""
from __future__ import annotations

import unittest
from uuid import uuid4

from zkc import distill as D
from zkc.distill import (
    Citation, DistillationError, DistillationOperator, DistillationResult,
    MetaClaim, distill_node, validate_result,
)


def _sid() -> tuple:
    return (uuid4(), "材料文本")


class DistillValidationTest(unittest.TestCase):
    def test_validate_accepts_claim_with_citation(self):
        r = DistillationResult(claims=[
            MetaClaim(text="c", topic="t", citations=[Citation(uuid4())]),
        ])
        self.assertIs(validate_result(r), r)  # 返回自身

    def test_validate_rejects_claim_without_citation(self):
        r = DistillationResult(claims=[
            MetaClaim(text="凭空结论", topic="t", citations=[]),
        ])
        with self.assertRaises(DistillationError):
            validate_result(r)

    def test_validate_rejects_empty(self):
        with self.assertRaises(DistillationError):
            validate_result(DistillationResult(claims=[]))


class DistillOperatorTest(unittest.TestCase):
    """provider 无关：注入 fake LLM 即可验证，无需真实 Ollama/Instructor。"""

    def test_operator_links_citation_and_reverse(self):
        sid, _ = _sid()
        fake_llm = lambda prompt: f"结论一 [[{sid}]]"
        op = DistillationOperator(fake_llm)
        res = op.distill(sid, [(sid, "材料文本")])
        self.assertEqual(len(res.claims), 1)
        claim = res.claims[0]
        self.assertEqual(claim.citations[0].source_node_id, sid)
        self.assertEqual(claim.reverse_links, [sid])   # 反向连接

    def test_operator_rejects_unmarked_output(self):
        # LLM 没用 [[uuid]] 标记来源 → 解析无引用 → 语义校验拦截（去繁非凭空）
        sid, _ = _sid()
        fake_llm = lambda prompt: "一段没有引用的结论"
        op = DistillationOperator(fake_llm)
        with self.assertRaises(DistillationError):
            op.distill(sid, [(sid, "材料文本")])

    def test_operator_ignores_unknown_citation(self):
        # 标记了不存在于 source 集合的 uuid → 不计入引用 → 校验拦截
        sid, _ = _sid()
        other = uuid4()
        fake_llm = lambda prompt: f"引用了无关节点 [[{other}]]"
        op = DistillationOperator(fake_llm)
        with self.assertRaises(DistillationError):
            op.distill(sid, [(sid, "材料文本")])

    def test_distill_node_module_entrypoint(self):
        sid, _ = _sid()
        res = distill_node(sid, [(sid, "x")], lambda p: f"ok [[{sid}]]")
        self.assertEqual(res.claims[0].reverse_links, [sid])


if __name__ == "__main__":
    unittest.main()

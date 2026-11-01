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


class DistillStructuredWiringTest(unittest.TestCase):
    """1-5-6 结构化接线：JSON 契约解析 + 手写校验重试（Instructor 等价）。"""

    def test_json_contract_multi_claim(self):
        s1, s2 = uuid4(), uuid4()
        raw = ('{"claims": ['
               '{"text": "结论A", "topic": "时机", "citations": ["%s"]},'
               '{"text": "结论B", "topic": "债务", "citations": ["%s", "%s"]}]}'
               % (s1, s2, s1))
        res = distill_node(s1, [(s1, "a"), (s2, "b")], lambda p: raw)
        self.assertEqual(res.attempts, 1)
        self.assertEqual([c.text for c in res.claims], ["结论A", "结论B"])
        self.assertEqual(res.claims[0].citations[0].source_node_id, s1)
        self.assertEqual(res.claims[1].reverse_links, [s2, s1])

    def test_json_drops_unknown_and_malformed_citations(self):
        s1 = uuid4()
        raw = ('{"claims": [{"text": "结论", "topic": "t", '
               '"citations": ["%s", "not-a-uuid", "%s"]}]}'
               % (s1, uuid4()))
        res = distill_node(s1, [(s1, "a")], lambda p: raw)
        self.assertEqual([c.source_node_id for c in res.claims[0].citations], [s1])

    def test_json_inline_markers_merged(self):
        # citations 数组缺项但文本带 [[uuid]] → 两种标记并入（宽容混用）
        s1, s2 = uuid4(), uuid4()
        raw = ('{"claims": [{"text": "结论 [[%s]]", "topic": "t", '
               '"citations": ["%s"]}]}' % (s2, s1))
        res = distill_node(s1, [(s1, "a"), (s2, "b")], lambda p: raw)
        self.assertEqual(res.claims[0].reverse_links, [s1, s2])

    def test_broken_json_falls_back_to_text_markers(self):
        # LLM 不守 JSON 契约 → 旧文本标记路径仍可用（向后兼容）
        sid, _ = _sid()
        res = distill_node(sid, [(sid, "x")], lambda p: f"结论 [[{sid}]]")
        self.assertEqual(res.claims[0].reverse_links, [sid])
        self.assertEqual(res.attempts, 1)

    def test_retry_after_parse_failure(self):
        # 第一次坏 JSON，第二次好 → attempts=2 且只重试到成功为止
        s1 = uuid4()
        outs = ["这不是JSON", '{"claims": [{"text": "c", "topic": "t", "citations": ["%s"]}]}' % s1]
        res = distill_node(s1, [(s1, "a")], lambda p: outs.pop(0))
        self.assertEqual(res.attempts, 2)

    def test_retry_after_semantic_failure(self):
        # 第一次解析成功但 citations 为空（语义校验失败）→ 也触发重试
        s1 = uuid4()
        bad = '{"claims": [{"text": "c", "topic": "t", "citations": []}]}'
        good = '{"claims": [{"text": "c2", "topic": "t", "citations": ["%s"]}]}' % s1
        outs = [bad, good]
        res = distill_node(s1, [(s1, "a")], lambda p: outs.pop(0))
        self.assertEqual(res.attempts, 2)
        self.assertEqual(res.claims[0].text, "c2")

    def test_retry_exhausted_raises(self):
        sid, _ = _sid()
        with self.assertRaises(DistillationError):
            distill_node(sid, [(sid, "x")], lambda p: "没有引用的输出", max_attempts=2)

    def test_correction_hint_in_retry_prompt(self):
        # 重试 prompt 必须带短修正提示（非膨胀重试，spike-10 先例）
        s1 = uuid4()
        seen = []
        outs = ["坏输出", '{"claims": [{"text": "c", "topic": "t", "citations": ["%s"]}]}' % s1]

        def llm(prompt):
            seen.append(prompt)
            return outs.pop(0)

        distill_node(s1, [(s1, "a")], llm)
        self.assertEqual(len(seen), 2)
        self.assertNotIn("上一次输出未通过校验", seen[0])
        self.assertIn("上一次输出未通过校验", seen[1])
        # schema 提示随首调注入（Instructor Mode.JSON 的提示层等价）
        self.assertIn('"claims"', seen[0])

    def test_json_without_claims_key_falls_back(self):
        # JSON 合法但没有 claims 数组 → 视为解析失败 → 文本 fallback
        sid, _ = _sid()
        res = distill_node(sid, [(sid, "x")], lambda p: '{"answer": "x"} 结论 [[%s]]' % sid)
        self.assertEqual(res.claims[0].reverse_links, [sid])


if __name__ == "__main__":
    unittest.main()

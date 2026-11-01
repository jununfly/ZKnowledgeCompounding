"""P3.5 忠实度闸门单测（zkc/faithfulness.py，Spike 12/13/13b 降级链第 2 级）。

覆盖 Spike 13 §8 验收门槛的可测子集：
- ③ 任何 claim 不得在无「记录的人判」或「带 judge_raw 的显式 auto-pass」下离开 pending；
- ① 强制项（矛盾/空分解）绝不 auto-pass；
- ④ 每个人判落入校准语料（judge vs 人）；
- rubric 红旗仅标注、不放行（Spike 10 盲点显式记账）。

全 stub 注入，不依赖模型 / PG（PG 同构路径由 test_faithfulness_pg.py 覆盖，可选）。
"""
from __future__ import annotations

import random
import unittest
from uuid import uuid4

from zkc import tuning
from zkc.faithfulness import (
    AtomicFact,
    Judgment,
    adjudicate,
    aggregate,
    calibration_corpus,
    gate_new_claims,
    parse_judgment,
    pending_human_queue,
    route_claim,
    rubric_flags,
    verbatim_rate,
)
from zkc.repository import get_storage


def _claim(text="这是一个从来源蒸馏出的结论。", **kw):
    from zkc.repository.models import Claim
    return Claim(statement=text, evidence_refs=[uuid4(), uuid4()], **kw)


def _sources(n=2):
    return [{"id": str(uuid4()), "title": f"来源{i}", "content": "安全评审要求权限判断必须在服务端完成，返工持续了两周。"}
            for i in range(n)]


def _provider(sources=None):
    src = sources if sources is not None else _sources()
    return lambda claim: src


# ---------------------------------------------------------------- 字面 rubric

class RubricTests(unittest.TestCase):
    def test_copied_claim_flags_verbatim(self):
        src = "安全评审要求权限判断必须在服务端完成，返工持续了两周，台账记录了三分之一的清理率。"
        flags = rubric_flags("安全评审要求权限判断必须在服务端完成，返工持续了两周", [src])
        self.assertTrue(any(f.startswith("rubric_verbatim") for f in flags), flags)

    def test_good_abstraction_no_flags(self):
        # spike-10 实证：好抽象 verbatim 0.18 / overlap 0.12，均低于占位阈值
        src = "安全评审要求权限判断必须在服务端完成，返工持续了两周，台账记录了三分之一的清理率。"
        flags = rubric_flags("评审把鉴权职责收敛到了后端侧，这也让联调返工的时间box更可控", [src])
        self.assertEqual(flags, [], flags)

    def test_empty_source_text_is_a_flag_not_crash(self):
        flags = rubric_flags("任意结论", ["  "])
        self.assertEqual(flags, ["rubric_no_source_text"])

    def test_verbatim_rate_bounds(self):
        self.assertEqual(verbatim_rate("", ["x"]), 0.0)
        self.assertEqual(verbatim_rate("没有来源匹配的内容哦", ["完全无关"]), 0.0)


# ---------------------------------------------------------------- judge seam

class AggregateTests(unittest.TestCase):
    def test_derivation_matrix(self):
        F = AtomicFact
        self.assertIsNone(aggregate([]))
        self.assertEqual(aggregate([F(fact="a", verdict="supported")]), "supported")
        self.assertEqual(
            aggregate([F(fact="a", verdict="supported"), F(fact="b", verdict="contradicted")]),
            "contradicted")
        self.assertEqual(
            aggregate([F(fact="a", verdict="supported"), F(fact="b", verdict="unsupported")]),
            "partial")
        self.assertEqual(aggregate([F(fact="a", verdict="unsupported")]), "unsupported")


class ParseJudgmentTests(unittest.TestCase):
    def test_extracts_json_block_from_prose(self):
        raw = '分析如下：\n{"atomic_facts":[{"fact":"x","verdict":"supported"}],"overall":"supported"}'
        j = parse_judgment(raw)
        self.assertEqual(len(j.atomic_facts), 1)

    def test_prose_only_raises(self):
        with self.assertRaises(ValueError):
            parse_judgment("Label: contradicted\nEvidence: [s1]")


def _stub_judge(facts, reason="stub", self_overall="supported"):
    """返回 llm_fn stub：无论 prompt 如何都返回给定分解（验证路由不信自报 overall）。"""
    def fn(prompt, system):
        return Judgment(atomic_facts=list(facts), overall=self_overall, reason=reason)
    return fn


class JudgeClaimTests(unittest.TestCase):
    def test_derived_overall_overrides_self_report(self):
        facts = [AtomicFact(fact="a", verdict="contradicted")]
        j = _stub_judge(facts, self_overall="supported")( "p", "s")
        # judge_claim 内部推导 contradicted，不信 stub 自报的 supported
        from zkc.faithfulness import judge_claim
        out = judge_claim(_stub_judge(facts, self_overall="supported"), "claim", _sources())
        self.assertEqual(out.overall, "contradicted")

    def test_empty_facts_returned_after_retry(self):
        calls = []

        def fn(prompt, system):
            calls.append(prompt)
            return Judgment(atomic_facts=[], overall="supported", reason="empty")

        from zkc.faithfulness import judge_claim
        out = judge_claim(fn, "claim", _sources())
        self.assertEqual(len(calls), 2)      # 重试一次
        self.assertEqual(out.atomic_facts, [])  # 原样返回，路由层负责强制人审


# ---------------------------------------------------------------- 路由

class RouteHumanOnlyTests(unittest.TestCase):
    """降级链第 2 级（本机现状）：judge 不可用 → 全人工，绝不 auto-pass。"""

    def test_all_claims_go_pending_human(self):
        d = route_claim(_claim(), _sources(), judge_fn=None)
        self.assertEqual(d.status, "pending_human")
        self.assertEqual(d.route, "human_only")
        self.assertIsNone(d.judge_model)
        self.assertIn("judge 不可用", d.reason)

    def test_rubric_flag_recorded_but_not_released(self):
        copied = "安全评审要求权限判断必须在服务端完成，返工持续了两周"
        d = route_claim(_claim(copied), _sources(), judge_fn=None)
        self.assertEqual(d.status, "pending_human")  # 红旗不放行
        self.assertTrue(any(f.startswith("rubric_") for f in d.flags))
        # flags 持久化进 judge_raw（jsonb），供队列排序与追溯
        self.assertIn("flags", d.judge_raw)


class RouteWithJudgeTests(unittest.TestCase):
    S = _sources()

    def test_contradicted_forces_human(self):
        facts = [AtomicFact(fact="权限在服务端", verdict="supported"),
                 AtomicFact(fact="返工三周", verdict="contradicted")]
        d = route_claim(_claim(), self.S, judge_fn=_stub_judge(facts), judge_model="stub-1")
        self.assertEqual(d.status, "pending_human")
        self.assertEqual(d.route, "forced_contradicted")
        self.assertEqual(d.judge_raw["overall"], "contradicted")
        self.assertEqual(d.judge_model, "stub-1")

    def test_empty_atomic_forces_human(self):
        d = route_claim(_claim(), self.S, judge_fn=_stub_judge([]))
        self.assertEqual(d.status, "pending_human")
        self.assertEqual(d.route, "forced_empty_atomic")

    def test_unsupported_sampling_hit_or_trace(self):
        facts = [AtomicFact(fact="a", verdict="supported"),
                 AtomicFact(fact="b", verdict="unsupported")]
        hit = route_claim(_claim(), self.S, judge_fn=_stub_judge(facts), rng=random.Random(0))
        # 找一个必中/必未中的种子对：R=0.3，随机数 <0.3 → pending
        statuses = {route_claim(_claim(), self.S, judge_fn=_stub_judge(facts),
                                rng=random.Random(seed)).status
                    for seed in range(30)}
        self.assertTrue(statuses <= {"pending_human", "sampled_pending"}, statuses)
        self.assertTrue("pending_human" in statuses and "sampled_pending" in statuses)
        # sampled_pending 是留痕不是放行：route 仍记录 judge_raw
        miss = next(d for seed in range(30)
                    for d in [route_claim(_claim(), self.S, judge_fn=_stub_judge(facts),
                                          rng=random.Random(seed))]
                    if d.status == "sampled_pending")
        self.assertIsNotNone(miss.judge_raw)

    def test_supported_auto_pass_with_audit(self):
        facts = [AtomicFact(fact="a", verdict="supported")]
        statuses = {route_claim(_claim(), self.S, judge_fn=_stub_judge(facts),
                                rng=random.Random(seed)).status
                    for seed in range(60)}
        self.assertTrue(statuses <= {"pending_human", "auto_passed"}, statuses)
        self.assertIn("auto_passed", statuses)
        auto = next(d for seed in range(60)
                    for d in [route_claim(_claim(), self.S, judge_fn=_stub_judge(facts),
                                          rng=random.Random(seed))]
                    if d.status == "auto_passed")
        # 验收③：auto-pass 必须带 judge_raw 显式留痕
        self.assertIsNotNone(auto.judge_raw)
        self.assertEqual(auto.judge_raw["overall"], "supported")
        self.assertEqual(auto.route, "auto_supported")


# ---------------------------------------------------------------- store 编排

class StoreFlowTests(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")

    def test_gate_new_claims_persists_d9_fields(self):
        c = _claim()
        self.store.claims.save(c)
        decisions = gate_new_claims(self.store, [c], _provider())
        saved = self.store.claims.get(c.id)
        self.assertEqual(saved.faithfulness_status, "pending_human")
        self.assertEqual(saved.faithfulness_route, "human_only")
        self.assertEqual(saved.judge_raw.get("mode"), "human_only")
        self.assertEqual(decisions[0].claim_id, c.id)

    def test_no_silent_release_acceptance_3(self):
        """验收③：gate 后每条 claim ∈ {pending_human, sampled_pending, auto_passed}，
        且 auto_passed 必带 judge_raw；human_only 模式下不可能出现 auto_passed。"""
        claims = [_claim(f"结论{i}") for i in range(5)]
        for c in claims:
            self.store.claims.save(c)
        gate_new_claims(self.store, claims, _provider(), judge_fn=None)
        for c in claims:
            saved = self.store.claims.get(c.id)
            self.assertEqual(saved.faithfulness_status, "pending_human")

    def test_adjudicate_terminal_states(self):
        c = _claim()
        self.store.claims.save(c)
        gate_new_claims(self.store, [c], _provider())
        r = adjudicate(self.store, c.id, "confirm")
        self.assertEqual(r["faithfulness_status"], "human_confirmed")
        saved = self.store.claims.get(c.id)
        self.assertEqual(saved.human_verdict, "confirm")
        self.assertIsNotNone(saved.human_verdict_at)

    def test_adjudicate_reject_and_edit(self):
        for verdict, expected in (("reject", "human_rejected"), ("edit", "human_rejected")):
            c = _claim()
            self.store.claims.save(c)
            gate_new_claims(self.store, [c], _provider())
            r = adjudicate(self.store, c.id, verdict)
            self.assertEqual(r["faithfulness_status"], expected)

    def test_adjudicate_invalid_verdict_and_double_adjudication(self):
        c = _claim()
        self.store.claims.save(c)
        gate_new_claims(self.store, [c], _provider())
        with self.assertRaises(ValueError):
            adjudicate(self.store, c.id, "maybe")
        adjudicate(self.store, c.id, "confirm")
        # 终态不可二次裁决（验收③：无记录人判不得离开 pending，终态锁定）
        with self.assertRaises(ValueError):
            adjudicate(self.store, c.id, "reject")

    def test_sampled_pending_adjudicable(self):
        """审计/人工翻查 sampled_pending 时可补裁决（Spike 13 §3 留痕语义）。"""
        c = _claim()
        c.faithfulness_status = "sampled_pending"
        c.faithfulness_route = "sampled_unsupported"
        self.store.claims.save(c)
        r = adjudicate(self.store, c.id, "reject")
        self.assertEqual(r["faithfulness_status"], "human_rejected")


class QueueAndCorpusTests(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")

    def _gate(self, text, route=None):
        c = _claim(text)
        self.store.claims.save(c)
        gate_new_claims(self.store, [c], _provider())
        if route:
            saved = self.store.claims.get(c.id)  # 取新对象，避免 OCC 版本冲突
            saved.faithfulness_route = route
            self.store.claims.save(saved)
        return c

    def test_pending_queue_forced_first_then_flags(self):
        forced = self._gate("矛盾项", route="forced_contradicted")
        plain = _claim("普通项")
        self.store.claims.save(plain)
        gate_new_claims(self.store, [plain], _provider())
        copied = _claim("安全评审要求权限判断必须在服务端完成，返工持续了两周")
        self.store.claims.save(copied)
        gate_new_claims(self.store, [copied], _provider())
        q = pending_human_queue(self.store)
        ids = [item["id"] for item in q]
        self.assertIn(str(forced.id), ids)
        # forced 排最前
        self.assertEqual(ids[0], str(forced.id))
        # 带红旗的排在无红旗之前
        self.assertLess(ids.index(str(copied.id)), ids.index(str(plain.id)))

    def test_pending_queue_excludes_terminal(self):
        c = self._gate("已裁决项")
        adjudicate(self.store, c.id, "confirm")
        q = pending_human_queue(self.store)
        self.assertNotIn(str(c.id), [item["id"] for item in q])

    def test_calibration_corpus_judge_vs_human(self):
        """验收④：每个人判落校准语料；judge_correct = 判定与人判的一致性。
        judge=contradicted（判 claim 不忠实）+ 人 reject → 判对；
        judge=contradicted + 人 confirm（人推翻 judge）→ 判错（误杀样本）。"""
        facts = [AtomicFact(fact="与来源冲突", verdict="contradicted")]
        for text, verdict in (("甲", "confirm"), ("乙", "reject")):
            c = _claim(text)
            self.store.claims.save(c)
            gate_new_claims(self.store, [c], _provider(),
                            judge_fn=_stub_judge(facts), judge_model="stub-1")
            adjudicate(self.store, c.id, verdict)
        corpus = calibration_corpus(self.store)
        self.assertEqual(len(corpus), 2)
        by_verdict = {r["human_verdict"]: r for r in corpus}
        self.assertEqual(by_verdict["reject"]["judge_correct"], True)
        self.assertEqual(by_verdict["confirm"]["judge_correct"], False)
        # 语料携带 judge 侧信息（对照用）
        for r in corpus:
            self.assertEqual(r["judge_overall"], "contradicted")
            self.assertEqual(r["judge_atomic"], ["contradicted"])

    def test_calibration_corpus_excludes_no_judge_rows(self):
        c = self._gate("无 judge 的裁决")
        adjudicate(self.store, c.id, "confirm")
        self.assertEqual(calibration_corpus(self.store), [])


class TuningKeysTests(unittest.TestCase):
    def test_faith_keys_registered(self):
        for name in ("FAITH_RUBRIC_VERBATIM_MAX", "FAITH_RUBRIC_OVERLAP_MAX",
                     "FAITH_R_UNSUPPORTED", "FAITH_AUDIT_RATE"):
            self.assertIsNotNone(tuning.get(name), name)
        self.assertEqual(tuning.param("FAITH_RUBRIC_VERBATIM_MAX").source, "placeholder")


if __name__ == "__main__":
    unittest.main()

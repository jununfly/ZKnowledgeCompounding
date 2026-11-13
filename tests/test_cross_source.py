"""P3.2 跨源强制算子单测（移植 Spike 11 test_enforcement.py）。

机制层验证（stub 注入，不依赖模型）：
  1. 主生成/补全 prompt 均含跨源硬约束措辞；
  2. 主生成不达标 -> 补全恰好触发 1 次、need 正确、最终达标；
     主生成已达标 -> 补全不触发；
  3. 引用强制对补全 claim 仍生效（幻觉来源 id 被过滤；全崩塌保留主产物）；
  4. RCS 漏斗截断 + 调优默认值（tuning 唯一出口）；
  5. R14 埋点：latency 字段在触发/未触发两形态下正确。
"""
from __future__ import annotations

import unittest

from zkc import tuning
from zkc.cross_source import (
    ArtifactClaim,
    CrossSourceArtifact,
    CrossSourceOperator,
    count_cross_source,
    enforce_citations,
)

SOURCES = [
    {"id": "s1", "title": "A", "content": "鉴权放客户端被安全评审打回，返工两周。"},
    {"id": "s2", "title": "B", "content": "第三方 SDK 拖到停服前一周才升级，被动返工两周。"},
    {"id": "s3", "title": "C", "content": "临时绕过都会变长期负担，不会有人主动拆。"},
    {"id": "s4", "title": "D", "content": "压测前置到设计阶段，连接池瓶颈改动成本近零。"},
    {"id": "s5", "title": "E", "content": "技术债必须记账带责任人，三分之一被清理。"},
]


def stub_summarize(src, query):
    return f"summary-of-{src['id']}"


def stub_score(summary, query):
    return 0.5


def _single_source_artifact() -> CrossSourceArtifact:
    """主生成每来源一条 claim，跨源数 = 0（不达标）。"""
    return CrossSourceArtifact(
        title="t", kind="mental_model",
        claims=[ArtifactClaim(statement=f"claim {i}", level="pattern", confidence=0.5,
                              evidence_ids=[s["id"]]) for i, s in enumerate(SOURCES[:3])],
        local=["lx"], global_insights=["gy"],
    )


def _two_cross_artifact() -> CrossSourceArtifact:
    """主生成已达标（2 条跨源）。"""
    return CrossSourceArtifact(
        title="t", kind="mental_model",
        claims=[
            ArtifactClaim(statement="single", level="pattern", confidence=0.5,
                          evidence_ids=["s1"]),
            ArtifactClaim(statement="cross A", level="pattern", confidence=0.6,
                          evidence_ids=["s1", "s2"]),
            ArtifactClaim(statement="cross B", level="tradeoff", confidence=0.6,
                          evidence_ids=["s2", "s3"]),
        ],
        local=["lx"], global_insights=["gy"],
    )


def gen_single(prompt):
    return _single_source_artifact()


def gen_two(prompt):
    return _two_cross_artifact()


def _cross_claims(extra_fake=False):
    c1 = ArtifactClaim(statement="cross A", level="pattern", confidence=0.6,
                       evidence_ids=["s1", "s2"])
    c2 = ArtifactClaim(statement="cross B", level="tradeoff", confidence=0.6,
                       evidence_ids=["s2", "s3"])
    if extra_fake:
        c3 = ArtifactClaim(statement="cross C fake", level="pattern", confidence=0.6,
                           evidence_ids=["s1", "zzz"])  # zzz 非真实来源 id
        return [c1, c2, c3]
    return [c1, c2]


class PromptLayerTests(unittest.TestCase):
    def test_main_prompt_contains_hard_requirement(self):
        op = CrossSourceOperator(stub_summarize, stub_score, gen_single,
                                 min_cross_source=2)
        p = op._build_prompt("Q", [{"source": SOURCES[0], "summary": "x",
                                    "score": 0.5}], 2)
        self.assertIn("硬约束", p)
        self.assertIn("2 条", p)
        self.assertIn(">=2 个不同来源", p)

    def test_complete_prompt_requests_missing_cross_claims(self):
        op = CrossSourceOperator(stub_summarize, stub_score, gen_single,
                                 min_cross_source=2)
        p = op._build_complete_prompt(
            "Q", [{"source": SOURCES[0], "summary": "x", "score": 0.5}], [], 2, "s1, s2")
        self.assertIn("补充至少 2 条", p)
        self.assertIn(">=2 个不同来源", p)


class CompletionLoopTests(unittest.TestCase):
    def test_completion_fires_when_floor_unmet(self):
        calls = {"n": 0, "need": None}

        def _complete(query, kept, existing, need):
            calls["n"] += 1
            calls["need"] = need
            return {"claims": _cross_claims()}

        op = CrossSourceOperator(stub_summarize, stub_score, gen_single,
                                 complete=_complete, min_cross_source=2)
        out = op.combine("Q", SOURCES)
        self.assertEqual(calls["n"], 1, "补全必须恰好触发 1 次")
        self.assertEqual(calls["need"], 2, "need = 缺口数")
        self.assertTrue(out["report"]["completion_fired"])
        self.assertGreaterEqual(out["report"]["n_cross_source_final"], 2)

    def test_no_completion_when_floor_already_met(self):
        calls = {"n": 0}

        def _complete(query, kept, existing, need):
            calls["n"] += 1
            return {"claims": _cross_claims()}

        op = CrossSourceOperator(stub_summarize, stub_score, gen_two,
                                 complete=_complete, min_cross_source=2)
        out = op.combine("Q", SOURCES)
        self.assertEqual(calls["n"], 0, "已达标时补全不得触发")
        self.assertFalse(out["report"]["completion_fired"])
        self.assertGreaterEqual(out["report"]["n_cross_source_final"], 2)

    def test_completion_hallucinated_citation_dropped(self):
        def _complete(query, kept, existing, need):
            return {"claims": _cross_claims(extra_fake=True)}

        op = CrossSourceOperator(stub_summarize, stub_score, gen_single,
                                 complete=_complete, min_cross_source=2)
        out = op.combine("Q", SOURCES)
        all_ev = [e for c in out["artifact"]["claims"] for e in c["evidence_ids"]]
        self.assertNotIn("zzz", all_ev, "幻觉引用必须被强制过滤")
        self.assertGreaterEqual(out["report"]["n_cross_source_final"], 2)

    def test_completion_collapse_keeps_main_artifact(self):
        def _complete(query, kept, existing, need):
            return {"claims": [ArtifactClaim(statement="x", level="pattern",
                                             confidence=0.5,
                                             evidence_ids=["zzz", "yyy"])]}

        op = CrossSourceOperator(stub_summarize, stub_score, gen_single,
                                 complete=_complete, min_cross_source=2)
        out = op.combine("Q", SOURCES)
        self.assertEqual(out["report"]["n_cross_source_final"], 0)
        self.assertTrue(out["artifact"]["claims"], "补全全崩时保留主生成产物")

    def test_kill_switch_disables_completion(self):
        """R14 降级预案：complete_on_shortfall=False 时即使不达标也不补全。"""
        calls = {"n": 0}

        def _complete(query, kept, existing, need):
            calls["n"] += 1
            return {"claims": _cross_claims()}

        op = CrossSourceOperator(stub_summarize, stub_score, gen_single,
                                 complete=_complete, min_cross_source=2,
                                 complete_on_shortfall=False)
        out = op.combine("Q", SOURCES)
        self.assertEqual(calls["n"], 0)
        self.assertFalse(out["report"]["completion_fired"])


class FunnelAndTuningTests(unittest.TestCase):
    def test_funnel_caps_sources_and_reports_dropped(self):
        seen = []

        def summarize(src, query):
            seen.append(src["id"])
            return f"sum-{src['id']}"

        def score(summary, query):
            # s5 最低分，应被截断掉
            return 0.1 if summary == "sum-s5" else 0.5

        op = CrossSourceOperator(summarize, score, gen_single, max_sources=4,
                                 min_cross_source=2)
        out = op.combine("Q", SOURCES)
        self.assertEqual(len(seen), 5, "每条来源都必须过一次摘要")
        self.assertEqual(len(out["report"]["kept"]), 4)
        self.assertEqual([d["id"] for d in out["report"]["dropped"]], ["s5"])

    def test_defaults_come_from_tuning(self):
        """P1.4 铁律：默认阈值走 tuning 唯一出口。"""
        op = CrossSourceOperator(stub_summarize, stub_score, gen_single)
        self.assertEqual(op.max_sources, tuning.get("COMBINE_MAX_SOURCES"))
        self.assertEqual(op.min_cross_source,
                         tuning.get("CROSS_SOURCE_MIN_ASSERTIONS"))

    def test_citation_enforcement_rejects_all_collapsed(self):
        art = {"claims": [{"statement": "x", "level": "pattern", "confidence": 0.5,
                           "evidence_ids": ["ghost"]}], "local": [], "global": []}
        with self.assertRaises(ValueError):
            enforce_citations(art, {"s1"})

    def test_count_cross_source_requires_distinct_ids(self):
        self.assertEqual(count_cross_source(
            [{"evidence_ids": ["s1", "s1"]}]), 0, "重复 id 不构成跨源")
        self.assertEqual(count_cross_source(
            [{"evidence_ids": ["s1", "s2"]}]), 1)


class LatencyTelemetryTests(unittest.TestCase):
    """R14：补全触发率与额外延迟必须可观测。"""

    def test_latency_fields_when_not_fired(self):
        op = CrossSourceOperator(stub_summarize, stub_score, gen_two,
                                 min_cross_source=2)
        out = op.combine("Q", SOURCES)
        r = out["report"]
        self.assertFalse(r["completion_fired"])
        self.assertIsNone(r["completion_latency_ms"])
        self.assertIsInstance(r["main_latency_ms"], float)
        self.assertGreaterEqual(r["main_latency_ms"], 0.0)

    def test_latency_fields_when_fired(self):
        op = CrossSourceOperator(stub_summarize, stub_score, gen_single,
                                 complete=lambda *a: {"claims": _cross_claims()},
                                 min_cross_source=2)
        out = op.combine("Q", SOURCES)
        r = out["report"]
        self.assertTrue(r["completion_fired"])
        self.assertIsInstance(r["completion_latency_ms"], float)
        self.assertGreaterEqual(r["completion_latency_ms"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

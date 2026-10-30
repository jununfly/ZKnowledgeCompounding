"""Spike 11 unit tests — operator/prompt layer, NO live model.

Verifies the cross-source enforcement mechanism with stubs:
  1. main prompt contains the HARD cross-source requirement (string-level).
  2. when the main generation yields 0 cross-source claims, the completion hook
     fires once with the correct `need`, and the final artifact meets the floor.
  3. citation enforcement still applies to completed claims (hallucinated ids dropped).
  4. verdict.cross_source gate behaves on constructed artifacts (rate + absolute).
  5. when the main generation already meets the floor, completion does NOT fire.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SPIKES = HERE.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


op_mod = _load("s11_op", HERE / "cross_source_op.py")
CrossSourceCombineOperator = op_mod.CrossSourceCombineOperator
artifact_models = op_mod.artifact_models
ModelingArtifact = artifact_models.ModelingArtifact
ArtifactClaim = artifact_models.ArtifactClaim

rubric = _load("s11_rubric", _SPIKES / "spike-10-model-quality" / "quality_rubric.py")
score_artifact = rubric.score_artifact
verdict = rubric.verdict

Art = ModelingArtifact
Claim = ArtifactClaim

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


def _single_source_artifact() -> Art:
    """Main generation that emits one claim per source, ZERO cross-source."""
    return Art(
        title="t", kind="mental_model",
        claims=[Claim(statement=f"claim {i}", level="pattern", confidence=0.5,
                      evidence_ids=[s["id"]]) for i, s in enumerate(SOURCES[:3])],
        local=["lx"], global_insights=["gy"],
    )


def _two_cross_artifact() -> Art:
    """Main generation that ALREADY meets the floor (2 cross-source claims)."""
    return Art(
        title="t", kind="mental_model",
        claims=[
            Claim(statement="single", level="pattern", confidence=0.5, evidence_ids=["s1"]),
            Claim(statement="cross A", level="pattern", confidence=0.6, evidence_ids=["s1", "s2"]),
            Claim(statement="cross B", level="tradeoff", confidence=0.6, evidence_ids=["s2", "s3"]),
        ],
        local=["lx"], global_insights=["gy"],
    )


def gen_single(prompt):
    """generate(prompt) stub: main generation yields ZERO cross-source claims."""
    return _single_source_artifact()


def gen_two(prompt):
    """generate(prompt) stub: main generation ALREADY meets the floor."""
    return _two_cross_artifact()


def _cross_claims(extra_fake=False):
    c1 = Claim(statement="cross A", level="pattern", confidence=0.6, evidence_ids=["s1", "s2"])
    c2 = Claim(statement="cross B", level="tradeoff", confidence=0.6, evidence_ids=["s2", "s3"])
    if extra_fake:
        c3 = Claim(statement="cross C fake", level="pattern", confidence=0.6,
                   evidence_ids=["s1", "zzz"])  # zzz is NOT a real source id
        return [c1, c2, c3]
    return [c1, c2]


class PromptLayerTests(unittest.TestCase):
    def test_main_prompt_contains_hard_requirement(self):
        op = CrossSourceCombineOperator(stub_summarize, stub_score, gen_single,
                                        None, min_cross_source=2)
        p = op._build_prompt("Q", [{"source": SOURCES[0], "summary": "x", "score": 0.5}], 2)
        self.assertIn("硬约束", p)
        self.assertIn("2 条", p)
        self.assertIn(">=2 个不同来源", p)

    def test_complete_prompt_requests_missing_cross_claims(self):
        op = CrossSourceCombineOperator(stub_summarize, stub_score, gen_single,
                                        None, min_cross_source=2)
        p = op._build_complete_prompt("Q", [{"source": SOURCES[0], "summary": "x", "score": 0.5}],
                                      [], 2, "s1, s2")
        self.assertIn("补充至少 2 条", p)
        self.assertIn(">=2 个不同来源", p)


class CompletionLoopTests(unittest.TestCase):
    def test_completion_fires_when_floor_unmet(self):
        calls = {"n": 0, "need": None}

        def _complete(query, kept, existing, need):
            calls["n"] += 1
            calls["need"] = need
            return {"claims": _cross_claims()}

        op = CrossSourceCombineOperator(stub_summarize, stub_score, gen_single,
                                        complete=_complete, min_cross_source=2)
        out = op.combine("Q", SOURCES)
        self.assertEqual(calls["n"], 1, "completion must fire exactly once")
        self.assertEqual(calls["need"], 2, "need should equal the shortfall")
        self.assertTrue(out["report"]["completion_fired"])
        self.assertGreaterEqual(out["report"]["n_cross_source_final"], 2)

    def test_no_completion_when_floor_already_met(self):
        calls = {"n": 0}

        def _complete(query, kept, existing, need):
            calls["n"] += 1
            return {"claims": _cross_claims()}

        op = CrossSourceCombineOperator(stub_summarize, stub_score, gen_two,
                                        complete=_complete, min_cross_source=2)
        out = op.combine("Q", SOURCES)
        self.assertEqual(calls["n"], 0, "completion must NOT fire when floor met")
        self.assertFalse(out["report"]["completion_fired"])
        self.assertGreaterEqual(out["report"]["n_cross_source_final"], 2)

    def test_completion_hallucinated_citation_dropped(self):
        def _complete(query, kept, existing, need):
            return {"claims": _cross_claims(extra_fake=True)}

        op = CrossSourceCombineOperator(stub_summarize, stub_score, gen_single,
                                        complete=_complete, min_cross_source=2)
        out = op.combine("Q", SOURCES)
        art = out["artifact"]
        all_ev = [e for c in art["claims"] for e in c["evidence_ids"]]
        self.assertNotIn("zzz", all_ev, "hallucinated citation must be enforced away")
        self.assertGreaterEqual(out["report"]["n_cross_source_final"], 2)

    def test_completion_collapse_keeps_main_artifact(self):
        # completion returns claims that all collapse under enforcement
        def _complete(query, kept, existing, need):
            return {"claims": [Claim(statement="x", level="pattern", confidence=0.5,
                                     evidence_ids=["zzz", "yyy"])]}

        op = CrossSourceCombineOperator(stub_summarize, stub_score, gen_single,
                                        complete=_complete, min_cross_source=2)
        out = op.combine("Q", SOURCES)
        # main artifact (0 cross) is preserved; no crash
        self.assertEqual(out["report"]["n_cross_source_final"], 0)
        self.assertTrue(out["artifact"]["claims"])


class RubricGateTests(unittest.TestCase):
    def _art(self, cross_count: int) -> dict:
        claims = []
        pool = [["s1", "s2"], ["s2", "s3"], ["s1", "s3"]]
        for i in range(cross_count):
            claims.append({"statement": f"c{i}", "level": "pattern", "confidence": 0.6,
                           "evidence_ids": pool[i % len(pool)]})
        return {"claims": claims, "local": ["l"], "global": ["g"]}

    def test_verdict_passes_with_2_cross(self):
        s = score_artifact(self._art(2), SOURCES)
        self.assertEqual(s["n_cross_source"], 2)
        self.assertTrue(verdict(s, "artifact")["checks"]["cross_source"])

    def test_verdict_fails_with_1_cross(self):
        s = score_artifact(self._art(1), SOURCES)
        self.assertEqual(s["n_cross_source"], 1)
        self.assertFalse(verdict(s, "artifact")["checks"]["cross_source"])

    def test_verdict_fails_with_0_cross(self):
        s = score_artifact({"claims": [{"statement": "x", "level": "pattern",
                                         "confidence": 0.5, "evidence_ids": ["s1"]}],
                            "local": ["l"], "global": ["g"]}, SOURCES)
        self.assertEqual(s["n_cross_source"], 0)
        self.assertFalse(verdict(s, "artifact")["checks"]["cross_source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

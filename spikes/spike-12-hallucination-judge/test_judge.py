"""Spike 12 unit tests — judge mechanism, no model dependency (stub injection).

Mirrors spike 10/11: the LLM call is injectable, so we verify the mechanism itself
(prompt structure, deterministic aggregation, eval math, fallback/retry) without
touching Ollama. A perfect oracle must score 100%; a 'always-supported' cheater must
be exposed by the dangerous-false-negative rate — both prove the eval is meaningful.
"""
from __future__ import annotations

import unittest

import judge
from judge import (
    AtomicFact, Judgment, aggregate, build_prompt, claim_from_prompt,
    evaluate, judge_artifact, judge_claim, oracle_fn, GOLDEN, corpus,
)


class PromptStructureTests(unittest.TestCase):
    def test_prompt_contains_all_source_ids_and_claim(self):
        claim = GOLDEN[0]["claim"]
        p = build_prompt(claim, corpus.SOURCES)
        for s in corpus.SOURCES:
            self.assertIn(s["id"], p)
        self.assertIn(claim, p)

    def test_prompt_has_decompose_and_verify_keywords(self):
        p = build_prompt("x", corpus.SOURCES)
        self.assertIn("原子事实", p)
        for v in ("supported", "unsupported", "contradicted"):
            self.assertIn(v, p)
        self.assertIn("evidence", p)

    def test_claim_from_prompt_roundtrip(self):
        claim = GOLDEN[3]["claim"]
        p = build_prompt(claim, corpus.SOURCES)
        self.assertEqual(claim_from_prompt(p), claim)


class AggregateTests(unittest.TestCase):
    def _a(self, verdict):
        return AtomicFact(fact="f", verdict=verdict)

    def test_all_supported(self):
        self.assertEqual(aggregate([self._a("supported"), self._a("supported")]), "supported")

    def test_mix_supported_unsupported(self):
        self.assertEqual(aggregate([self._a("supported"), self._a("unsupported")]), "partial")

    def test_only_unsupported(self):
        self.assertEqual(aggregate([self._a("unsupported")]), "unsupported")

    def test_any_contradicted_wins(self):
        self.assertEqual(
            aggregate([self._a("supported"), self._a("contradicted")]), "contradicted")
        self.assertEqual(aggregate([self._a("unsupported"), self._a("contradicted")]),
                         "contradicted")

    def test_empty_returns_none(self):
        self.assertIsNone(aggregate([]))


class OracleTests(unittest.TestCase):
    def test_oracle_scores_perfect(self):
        rep = evaluate(oracle_fn)
        self.assertEqual(rep["accuracy"], 1.0)
        self.assertEqual(rep["dangerous_false_negative_rate"], 0.0)
        self.assertEqual(rep["hallucination_catch_rate"], 1.0)
        self.assertEqual(rep["n"], len(GOLDEN))


class AlwaysSupportedCheaterTests(unittest.TestCase):
    """A judge that always says 'supported' must be exposed by the eval."""

    def _cheat(self, prompt, system):
        return Judgment(
            atomic_facts=[AtomicFact(fact=claim_from_prompt(prompt), verdict="supported")],
            reason="cheat")

    def test_cheater_has_zero_catch_and_full_danger(self):
        rep = evaluate(self._cheat)
        # only the 5 genuinely-supported examples are "correct"
        self.assertEqual(rep["accuracy"], round(5 / len(GOLDEN), 3))
        self.assertEqual(rep["hallucination_catch_rate"], 0.0)
        # all 5 contradicted (truth in {unsupported,contradicted}) judged supported
        self.assertEqual(rep["dangerous_false_negative_rate"], 1.0)

    def test_cheater_confusion(self):
        rep = evaluate(self._cheat)
        # every truth row collapses to predicted "supported"
        for truth in ("supported", "partial", "unsupported", "contradicted"):
            self.assertEqual(rep["confusion"][truth]["supported"],
                             sum(1 for e in GOLDEN if e["truth"] == truth))


class EmptyAtomicFallbackTests(unittest.TestCase):
    def test_empty_facts_trusts_overall(self):
        j = judge_claim(lambda p, s: Judgment(atomic_facts=[], overall="supported",
                                              reason="x"),
                        GOLDEN[0]["claim"], corpus.SOURCES)
        self.assertEqual(j.overall, "supported")
        self.assertEqual(j.atomic_facts, [])

    def test_retry_fills_empty_then_derives(self):
        calls = {"n": 0}

        def stub(prompt, system):
            calls["n"] += 1
            if calls["n"] == 1:
                return Judgment(atomic_facts=[], overall="supported")
            return Judgment(atomic_facts=[AtomicFact(fact="f", verdict="contradicted")])

        j = judge_claim(stub, GOLDEN[0]["claim"], corpus.SOURCES, retries=1)
        self.assertEqual(j.overall, "contradicted")  # derived, not the empty fallback
        self.assertEqual(calls["n"], 2)


class ArtifactTests(unittest.TestCase):
    def test_judge_artifact_faithful_rate(self):
        sources_by_id = {s["id"]: s for s in corpus.SOURCES}
        artifact = {
            "claims": [
                {"statement": GOLDEN[0]["claim"], "evidence_ids": ["s1"]},   # supported
                {"statement": GOLDEN[5]["claim"], "evidence_ids": ["s1"]},   # contradicted
            ]
        }
        rep = judge_artifact(oracle_fn, artifact, sources_by_id)
        self.assertEqual(rep["n_claims"], 2)
        self.assertEqual(rep["faithful_rate"], 0.5)
        self.assertEqual(rep["per"][0]["judgment"], "supported")
        self.assertEqual(rep["per"][1]["judgment"], "contradicted")


if __name__ == "__main__":
    unittest.main(verbosity=2)

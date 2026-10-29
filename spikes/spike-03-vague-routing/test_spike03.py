"""Spike 03 tests — both approaches must fix Spike 02's failure modes.

F1: short ambiguous items must NOT be falsely committed to a track (=> vague).
F2: long-vague adversarial sentences must NOT be misclassified as dynamic (=> vague).
Keep: clear static/dynamic items routed to their own track.

Run:  .venv/bin/python -m pytest test_spike03.py -q
       (Ollama-backed tests need the local Ollama server running.)
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spike-02-dual-track-routing"))
from router import DualTrackRouter as TwoWayRouter  # noqa: E402
from router import TfidfEncoder  # noqa: E402

from samples_v3 import (  # noqa: E402
    ROUTES,
    ROUTES_3WAY,
    CALIB_SET,
    CALIB_SET_3WAY,
    eval_3way,
    ADVERSARIAL,
)
from router3 import ThreeWayRouter, evaluate_3way  # noqa: E402
from ollama_embed import OllamaEmbed  # noqa: E402
from decision_router import DecisionRouter  # noqa: E402


# ---------------------------------------------------------------------------
# Baseline: reproduce Spike 02's 2-way failure (must fail on adversarial)
# ---------------------------------------------------------------------------
def build_2way(encoder):
    r = TwoWayRouter(encoder)
    for n, u in ROUTES.items():
        r.add_route(n, u)
    r.build()
    r.calibrate([x for x, _ in CALIB_SET], [y for _, y in CALIB_SET])
    return r


def build_3way(encoder):
    r = ThreeWayRouter(encoder)
    for n, u in ROUTES_3WAY.items():
        r.add_route(n, u)
    r.build()
    r.calibrate([x for x, _ in CALIB_SET_3WAY], [y for _, y in CALIB_SET_3WAY])
    return r


class TestBaselineTwoWay(unittest.TestCase):
    """Document that the 2-way router commits ALL 3 long-vague probes to dynamic."""

    def test_2way_commits_adversarial_to_dynamic(self):
        r = build_2way(TfidfEncoder())
        committed = [t for t in ADVERSARIAL if r.predict(t)[0] == "dynamic"]
        # Spike 02 finding: 3/3 misclassified as dynamic (the failure to fix)
        self.assertEqual(len(committed), 3)


class TestThreeWayTfidf(unittest.TestCase):
    """Approach A on the dependency-free lexical encoder (deterministic)."""

    def setUp(self):
        self.r = build_3way(TfidfEncoder())

    def test_f2_adversarial_not_dynamic(self):
        # Critical safety: long-vague adversarial must NOT be committed to dynamic.
        # "vague" or None(abstain) are both safe sinks.
        for t in ADVERSARIAL:
            self.assertNotEqual(self.r.predict(t)[0], "dynamic", f"adversarial committed to dynamic: {t}")

    def test_f1_no_false_commit_on_vague(self):
        # No ambiguous (vague) item may be pushed onto a real track.
        m = evaluate_3way(self.r, eval_3way())
        self.assertEqual(m["false_commit_on_vague"], 0)

    def test_clear_items_routed_correctly(self):
        m = evaluate_3way(self.r, eval_3way())
        # dangerous (false commit + track confusion) must stay low
        self.assertLessEqual(m["dangerous_total"], 2)
        self.assertGreaterEqual(m["accuracy_on_routed"], 0.85)


class TestThreeWayOllama(unittest.TestCase):
    """Approach A on real semantic encoders (needs local Ollama)."""

    def _run(self, model):
        try:
            r = build_3way(OllamaEmbed(model))
        except Exception as e:  # Ollama not reachable
            self.skipTest(f"Ollama unavailable: {e}")
        # Critical safety properties (Spike 02 failure modes):
        for t in ADVERSARIAL:
            self.assertNotEqual(r.predict(t)[0], "dynamic", f"adversarial committed to dynamic: {t}")
        m = evaluate_3way(r, eval_3way())
        # No ambiguous (vague) item may be pushed onto a real track.
        self.assertEqual(m["false_commit_on_vague"], 0)
        print(f"\n  [Ollama {model}] coverage={m['coverage']:.1%} "
              f"acc_on_routed={m['accuracy_on_routed']:.1%} dangerous_total={m['dangerous_total']}")

    @unittest.expectedFailure  # documented finding: weak encoders are UNSAFE for 3-way
    def test_nomic(self):
        # nomic-embed-text (768d) shows false_commit_on_vague=1 + track_confusion=2:
        # the 3-way design is encoder-strength-dependent and unsafe below ~qwen3-class.
        self._run("nomic-embed-text")

    def test_qwen3(self):
        self._run("qwen3-embedding")


class TestDecisionRouter(unittest.TestCase):
    """Approach B: LLM-as-judge (local Ollama chat, JSON)."""

    def test_unit_confidence_gate_and_parse_fail(self):
        dr = DecisionRouter()
        # low confidence -> forced vague
        dr._chat = lambda t: {"track": "static", "confidence": 0.2, "reason": "x"}
        self.assertEqual(dr.predict("anything")[0], "vague")
        # parse failure -> vague (safe)
        dr._chat = lambda t: {"track": "bogus", "confidence": 0.9, "reason": "x"}
        self.assertEqual(dr.predict("anything")[0], "vague")
        # valid
        dr._chat = lambda t: {"track": "dynamic", "confidence": 0.9, "reason": "x"}
        self.assertEqual(dr.predict("anything")[0], "dynamic")

    def test_f2_adversarial_all_vague_real(self):
        try:
            dr = DecisionRouter()
            # touch the endpoint once to confirm it's up
            dr._chat("ping")
        except Exception as e:
            self.skipTest(f"Ollama chat unavailable: {e}")
        for t in ADVERSARIAL:
            self.assertEqual(dr.predict(t)[0], "vague", f"adversarial not vague: {t}")

    def test_f1_no_false_commit_real(self):
        try:
            dr = DecisionRouter()
            dr._chat("ping")
        except Exception as e:
            self.skipTest(f"Ollama chat unavailable: {e}")
        m = evaluate_3way(dr, eval_3way())
        # The critical safety property: no vague item pushed onto a real track.
        self.assertEqual(m["false_commit_on_vague"], 0)
        print(f"\n  [DecisionRouter] coverage={m['coverage']:.1%} "
              f"acc_on_routed={m['accuracy_on_routed']:.1%} "
              f"track_confusion={m['track_confusion']} safe_undercover={m['safe_undercover']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

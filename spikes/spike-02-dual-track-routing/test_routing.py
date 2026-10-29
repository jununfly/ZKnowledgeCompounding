"""Spike 02 tests: calibrated dual-track routing with abstention.

Written BEFORE the implementation (TDD red step).
Thresholds come from the spike README and are set before seeing results.
"""
import unittest

from samples import ROUTES, EVAL_SET, CALIB_SET
from router import TfidfEncoder, DualTrackRouter, evaluate

MAX_MISROUTE = 0.10      # among non-abstained predictions
MIN_ABSTAIN = 0.05       # must exercise the abstain path at all
MAX_ABSTAIN = 0.45       # must not be so timid that it is useless


def build_router():
    enc = TfidfEncoder()
    r = DualTrackRouter(enc)
    for name, utts in ROUTES.items():
        r.add_route(name, utts)
    r.build()
    return r


class TestEncoder(unittest.TestCase):
    def test_identical_text_scores_one(self):
        enc = TfidfEncoder()
        enc.fit(["注意力机制", "今天开会"])
        v = enc.encode(["注意力机制"])[0]
        self.assertAlmostEqual(sum(x * x for x in v.values()) ** 0.5, 1.0, places=5)

    def test_unrelated_text_scores_low(self):
        enc = TfidfEncoder()
        enc.fit(["知识图谱本体", "本周排期调整"])
        a = enc.encode(["知识图谱本体"])[0]
        b = enc.encode(["本周排期调整"])[0]
        self.assertLess(sum(a.get(k, 0) * b.get(k, 0) for k in set(a) | set(b)), 0.3)


class TestRouting(unittest.TestCase):
    def test_clear_static_routes_to_static(self):
        r = build_router()
        r.calibrate([t for t, _ in CALIB_SET], [y for _, y in CALIB_SET])
        pred, _ = r.predict("Pgvector 的 HNSW 索引在过滤后需要迭代扫描")
        self.assertEqual(pred, "static")

    def test_clear_dynamic_routes_to_dynamic(self):
        r = build_router()
        r.calibrate([t for t, _ in CALIB_SET], [y for _, y in CALIB_SET])
        pred, _ = r.predict("下周一前把方案发给对方确认")
        self.assertEqual(pred, "dynamic")

    def test_abstain_path_exists(self):
        """The router must be able to return None instead of forcing a choice."""
        r = build_router()
        r.calibrate([t for t, _ in CALIB_SET], [y for _, y in CALIB_SET])
        pred, score = r.predict("嗯")
        self.assertIsNone(pred)
        self.assertIsInstance(score, float)

    def test_predict_returns_score_always(self):
        r = build_router()
        r.calibrate([t for t, _ in CALIB_SET], [y for _, y in CALIB_SET])
        for text, _ in EVAL_SET:
            _, score = r.predict(text)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)


class TestAcceptance(unittest.TestCase):
    """Acceptance thresholds, evaluated on the held-out set."""

    def test_misroute_rate_within_threshold(self):
        r = build_router()
        r.calibrate([t for t, _ in CALIB_SET], [y for _, y in CALIB_SET])
        m = evaluate(r, EVAL_SET)
        self.assertLessEqual(m["misroute_rate"], MAX_MISROUTE,
                             msg=f"misroute {m['misroute_rate']:.3f}")

    def test_abstention_within_band(self):
        r = build_router()
        r.calibrate([t for t, _ in CALIB_SET], [y for _, y in CALIB_SET])
        m = evaluate(r, EVAL_SET)
        self.assertGreaterEqual(m["abstain_rate"], MIN_ABSTAIN,
                                msg=f"never abstains ({m['abstain_rate']:.3f})")
        self.assertLessEqual(m["abstain_rate"], MAX_ABSTAIN,
                             msg=f"too timid ({m['abstain_rate']:.3f})")

    def test_ambiguous_items_are_the_ones_abstained(self):
        """Abstention should concentrate on genuinely ambiguous items, not random ones."""
        r = build_router()
        r.calibrate([t for t, _ in CALIB_SET], [y for _, y in CALIB_SET])
        m = evaluate(r, EVAL_SET)
        amb_total = sum(1 for _, y in EVAL_SET if y is None)
        self.assertGreaterEqual(
            m["abstain_on_ambiguous"] / amb_total, 0.5,
            msg=f"only {m['abstain_on_ambiguous']}/{amb_total} ambiguous abstained",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

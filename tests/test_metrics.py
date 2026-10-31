"""ZKC · P5.2 复利度量面板测试。

纯函数层用构造 MetricInputs 验证数学口径（含空库安全）；集成层用内存 fake 验证
load_metric_inputs → build_report 链路；HTTP 层用 TestClient 验证 /metrics 面板与 /metrics/api。
"""
from __future__ import annotations

import unittest

from zkc import metrics as M
from zkc.repository import get_storage
from zkc.repository.models import Claim, Edge, MetricInputs, Node


def _inp(**kw) -> MetricInputs:
    return MetricInputs(**kw)


class MetricsPureTest(unittest.TestCase):
    def test_empty_is_safe(self):
        r = M.build_report(_inp())
        self.assertEqual(r.connection_density, 0.0)
        self.assertEqual(r.reuse_rate, 0.0)
        self.assertEqual(r.methodology_output, 0)
        self.assertEqual(r.decay_controllability, 0.0)
        self.assertEqual(r.compounding_factor, 0.0)

    def test_connection_density(self):
        inp = _inp(
            nodes=[(1, "dynamic", 0.5, False), (2, "dynamic", 0.5, False),
                   (3, "static", 0.5, False)],
            edges=[(1, 2, "derived_from")],
        )
        self.assertAlmostEqual(M.connection_density(inp), 1.0, delta=1e-9)

    def test_connection_density_partial(self):
        inp = _inp(
            nodes=[(1, "dynamic", 0.5, False), (2, "dynamic", 0.5, False)],
            edges=[(1, 2, "reverse_link")],
        )
        # 两条都被反向连接触达 → 2/2 = 1.0
        self.assertAlmostEqual(M.connection_density(inp), 1.0, delta=1e-9)

    def test_reuse_rate(self):
        inp = _inp(claim_evidence=[[1], [2], [3]], citations=[1, 2])
        rate, per = M.reuse_rate(inp)
        self.assertAlmostEqual(rate, 2 / 3, delta=1e-9)
        self.assertAlmostEqual(per, 2 / 3, delta=1e-9)

    def test_methodology_output(self):
        inp = _inp(artifact_evidence=[[1], [2], [3]])
        self.assertEqual(M.methodology_output(inp), 3)

    def test_decay_controllability(self):
        # 3 条动态 + decay>=0.9（到期）；1 被 claim 引用、3 已归档 → 2/3 handled
        inp = _inp(
            nodes=[(1, "dynamic", 0.95, False), (2, "dynamic", 0.95, False),
                   (3, "dynamic", 0.95, True)],
            claim_evidence=[[1]],
        )
        self.assertAlmostEqual(M.decay_controllability(inp), 2 / 3, delta=1e-9)

    def test_compounding_factor_blended(self):
        cf = M.compounding_factor(cd=1.0, rr=2 / 3, mo=3, dc=2 / 3)
        # 等权 0.25 × (1.0 + 0.667 + min(1,3/10)=0.3 + 0.667) = 0.25 × 2.634 ≈ 0.6585
        self.assertAlmostEqual(cf, 0.25 * (1.0 + 2 / 3 + 0.3 + 2 / 3), delta=1e-6)

    def test_rot_threshold_from_tuning(self):
        inp = _inp(nodes=[(1, "dynamic", 0.5, False)], claim_evidence=[[1]])
        # decay 0.5 < ROT 0.9 → 无到期 → decay_controllability 0
        self.assertEqual(M.decay_controllability(inp), 0.0)


class MetricsMemoryTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        a = self.store.nodes.save(Node(title="A", track="dynamic"))
        b = self.store.nodes.save(Node(title="B", track="dynamic"))
        self.store.nodes.save(Node(title="C", track="static"))
        self.store.edges.link(a.id, b.id, "derived_from")
        self.store.claims.save(Claim(statement="A 的结论", evidence_refs=[a.id]))
        self.a, self.b = a, b

    def test_snapshot_shape(self):
        inp = self.store.load_metric_inputs()
        self.assertEqual(len(inp.nodes), 3)
        self.assertEqual(len(inp.edges), 1)
        self.assertEqual(len(inp.claim_evidence), 1)

    def test_report_connection_density_full(self):
        # 两条动态都被 derived_from 触达 → 1.0
        r = M.build_report(self.store.load_metric_inputs())
        self.assertAlmostEqual(r.connection_density, 1.0, delta=1e-9)
        # 无 citation / artifact → 复用率 0、方法论产出 0；无到期(decay=0) → 衰减可控 0
        self.assertEqual(r.reuse_rate, 0.0)
        self.assertEqual(r.methodology_output, 0)
        self.assertEqual(r.decay_controllability, 0.0)

    def test_metrics_report_dict_keys(self):
        d = M.metrics_report(self.store)
        for k in ("connection_density", "reuse_rate", "citations_per_claim",
                  "methodology_output", "decay_controllability", "compounding_factor"):
            self.assertIn(k, d)


class MetricsHttpTest(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from zkc.web.app import create_app

        self.store = get_storage("memory")
        self.store.nodes.save(Node(title="A", track="dynamic"))
        self.app = create_app(
            store=self.store, decision_router=object(), lexical_router=object())
        self.client = TestClient(self.app)

    def test_metrics_page_renders(self):
        r = self.client.get("/metrics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("复利度量面板", r.text)

    def test_metrics_api_returns_report(self):
        r = self.client.get("/metrics/api")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("compounding_factor", body)
        self.assertIn("connection_density", body)
        self.assertIn("notes", body)


if __name__ == "__main__":
    unittest.main()

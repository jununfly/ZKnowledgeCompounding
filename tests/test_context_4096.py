"""D4 反向连接候选召回切 4096 + 阈值重校准的 TDD 验收。

EX1 pg / memory 双实现一致；EX2 相似度分布证据；EX3 阈值按 4096 分布重校准
且 source 不得伪装 CALIBRATED；EX4 R16 硬约束（embedding 只作候选召回 + 人确认）。
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4

from zkc import tuning
from zkc.repository import get_storage
from zkc.repository.models import Node

ROOT = Path(__file__).resolve().parents[1]


class DiscoverColumnTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")

    def test_memory_discover_uses_4096_and_ranks_by_cosine(self):
        seed = self.store.nodes.save(Node(title="seed", embedding_4096=[1.0, 0.0]))
        near = self.store.nodes.save(Node(title="near", embedding_4096=[0.9, 0.1]))
        far = self.store.nodes.save(Node(title="far", embedding_4096=[0.0, 1.0]))
        self.store.nodes.save(Node(title="no-vector", embedding_4096=None))
        got = self.store.discover_higher_dim(seed.id, k=5)
        self.assertEqual([g["title"] for g in got], ["near", "far"])
        self.assertNotIn(str(seed.id), [str(g["id"]) for g in got])
        self.assertGreater(got[0]["sim"], got[1]["sim"])
        self.assertAlmostEqual(got[0]["sim"], 0.9 / (0.9 ** 2 + 0.1 ** 2) ** 0.5, places=4)
        self.assertIn(str(near.id), [str(g["id"]) for g in got])
        self.assertIn(str(far.id), [str(g["id"]) for g in got])

    def test_memory_discover_respects_k_and_missing_seed(self):
        seed = self.store.nodes.save(Node(title="seed", embedding_4096=[1.0, 0.0]))
        for i in range(4):
            self.store.nodes.save(Node(title=f"n{i}", embedding_4096=[1.0, i / 10]))
        self.assertEqual(len(self.store.discover_higher_dim(seed.id, k=2)), 2)
        self.assertEqual(self.store.discover_higher_dim(uuid4(), k=5), [])

    def test_memory_discover_can_select_768_column(self):
        seed = self.store.nodes.save(Node(title="seed", embedding=[1.0, 0.0]))
        self.store.nodes.save(Node(title="peer", embedding=[1.0, 0.0]))
        got = self.store.discover_higher_dim(seed.id, k=5, column="embedding")
        self.assertEqual([g["title"] for g in got], ["peer"])
        self.assertAlmostEqual(got[0]["sim"], 1.0, places=4)

    def test_invalid_column_is_rejected(self):
        seed = self.store.nodes.save(Node(title="seed", embedding_4096=[1.0, 0.0]))
        with self.assertRaises(ValueError):
            self.store.discover_higher_dim(seed.id, column="bogus")

    def test_pg_sql_defaults_to_4096(self):
        source = (ROOT / "src" / "zkc" / "repository" / "pg.py").read_text(encoding="utf-8")
        start = source.index("def discover_higher_dim")
        body = source[start:start + 1200]
        self.assertIn("column", body)
        self.assertIn('"embedding_4096"', body)
        self.assertIn("n.{col}", body)
        self.assertNotIn("n.embedding <=>", body)


class ThresholdRecalibrationTest(unittest.TestCase):
    def test_threshold_recalibrated_but_not_claimed_as_calibrated(self):
        p = tuning.param("CONTEXT_HIGHER_DIM_SIM_THRESHOLD")
        self.assertEqual(p.value, 0.65)
        self.assertNotEqual(p.source, tuning.CALIBRATED)
        self.assertIn("4096", p.note)
        # 运行时 REGISTRY 可能被其它用例的 calibrate() 临时改动，声明本身才是事实源。
        decl = next(line for line in (ROOT / "src/zkc/tuning.py").read_text().splitlines()
                    if 'CONTEXT_HIGHER_DIM_SIM_THRESHOLD", 0.65' in line)
        self.assertIn("SIMULATION", decl)

    def test_distribution_evidence_exists_and_supports_threshold(self):
        data = json.loads(
            (ROOT / "docs" / "evidence" / "r18-4096-sim-distribution.json").read_text()
        )
        self.assertEqual(data["column"], "embedding_4096")
        self.assertEqual(data["node_node"]["n"], 1770)
        row = next(c for c in data["threshold_candidates"] if c["threshold"] == 0.70)
        self.assertGreater(row["threshold_percentile_in_node_node"], 85)
        self.assertLess(row["query_recall"], 0.25)

    def test_calibration_gate_still_requires_human_confirmation(self):
        source = (ROOT / "src" / "zkc" / "context.py").read_text(encoding="utf-8")
        self.assertIn("CALIBRATED", source)
        self.assertIn("人审确认", source)
        # R16：embedding 不得承担安全判定，DecisionRouter 仍是唯一分流闸。
        self.assertIn("DecisionRouter", (ROOT / "src" / "zkc" / "routing.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

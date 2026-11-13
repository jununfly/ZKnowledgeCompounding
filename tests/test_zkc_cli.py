"""zkc CLI（Form B：去服务器化）端到端测试，内存后端。

验证：
  - zkc daily      真值收口无服务也能跑（record_daily_observation_auto）
  - zkc decide --list          列出 due 队列（空库不报错）
  - zkc decide --id+--verdict  注入含 due 节点的 store 验证标注真写入库
  - zkc meter --json          仪表含 E1 三判据

不依赖 PG 或 HTTP 服务；harness 形态（D）复用同一 CLI，故 CLI 行为契约即 D 的前置保证。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zkc.calibration import build_report
from zkc.cli import dispatch, parse_args
from zkc.repository import get_storage
from zkc.repository.models import Node


class ZkcCliTest(unittest.TestCase):
    def _store_with_due(self):
        store = get_storage("memory")
        now = datetime.now(timezone.utc)
        n = Node(
            track="dynamic", title="due-node", decay_score=0.9,
            review_interval=timedelta(days=1),
            last_reviewed_at=now - timedelta(days=10),
            created_at=now,
        )
        store.nodes.save(n)
        return store, n

    def test_daily_closes_without_server(self) -> None:
        """zkc daily：direct 模式真值收口，不依赖 web 服务。"""
        store, _ = self._store_with_due()
        rc = dispatch(parse_args(["daily"]), store=store)
        self.assertEqual(rc, 0)

    def test_decide_list_empty(self) -> None:
        """zkc decide --list：空库列队列不报错。"""
        store = get_storage("memory")
        rc = dispatch(parse_args(["decide", "--list"]), store=store)
        self.assertEqual(rc, 0)

    def test_decide_write_verdict(self) -> None:
        """zkc decide --id+--verdict：human-in-loop 写入，标注真落库。"""
        store, n = self._store_with_due()
        rc = dispatch(
            parse_args(["decide", "--id", str(n.id), "--verdict", "still_valid"]),
            store=store,
        )
        self.assertEqual(rc, 0)
        obs = store.attention.get(datetime.now(timezone.utc).date())
        self.assertIsNotNone(obs)
        self.assertEqual(obs.labeled_completed, 1)
        self.assertEqual(obs.completed, 1)

    def test_meter_reports_criteria(self) -> None:
        """zkc meter：返回 E1 三判据结构完整。"""
        store, _ = self._store_with_due()
        rc = dispatch(parse_args(["meter", "--json"]), store=store)
        self.assertEqual(rc, 0)
        r = build_report("memory", storage=store)
        self.assertIn("criteria", r)
        for k in ("c1_cumulative_active_days", "c2_labeling_rate_gate",
                  "c3_budget_convergence"):
            self.assertIn(k, r["criteria"])

    def test_embed_backfills_all_tracks_and_is_idempotent(self) -> None:
        """zkc embed：全轨 + 空正文兜底 + dry-run 不写 + 第二遍零编码。"""
        store = get_storage("memory")
        empty = store.nodes.save(Node(track="static", title="v1", content=None))
        normal = store.nodes.save(Node(track="dynamic", title="AINMM", content="body"))
        calls: list[str] = []

        def encoder(column, dim):
            def encode(texts):
                calls.extend(f"{column}:{t}" for t in texts)
                return [[0.1] * dim for _ in texts]
            return encode

        enc = {"embedding": encoder("768", 768),
               "embedding_4096": encoder("4096", 4096)}

        self.assertEqual(dispatch(parse_args(["embed", "--dry-run", "--json"]),
                                  store=store, encoders=enc), 0)
        self.assertEqual(calls, [])  # dry-run 不编码、不写
        self.assertIsNone(store.nodes.get(empty.id).embedding)

        self.assertEqual(dispatch(parse_args(["embed", "--json"]),
                                  store=store, encoders=enc), 0)
        for nid in (empty.id, normal.id):
            saved = store.nodes.get(nid)
            self.assertEqual(len(saved.embedding), 768)
            self.assertEqual(len(saved.embedding_4096), 4096)
        first_calls = len(calls)
        self.assertEqual(first_calls, 4)  # 2 texts × 2 columns

        self.assertEqual(dispatch(parse_args(["embed", "--json"]),
                                  store=store, encoders=enc), 0)
        self.assertEqual(len(calls), first_calls)  # 幂等：第二遍零编码零写入


if __name__ == "__main__":
    unittest.main()

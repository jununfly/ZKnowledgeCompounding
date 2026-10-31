"""zkc/scheduling 真实 PG 集成实测（P4.1 / P4.4，spike-09 落地验证）。

在临时 PG 库跑全迁移，验证：
1. assign_baselines 按 L1 阶梯正确赋值（时间锚/self_loop/connected/captured/orphan/human 豁免）。
2. fit_budget 预算不足时按优先级延后低优先条目，写审计且可整体回滚（revert_interval_transform）。
3. adapt_interval 走标注率闸门：样本不足放行；未标注且率不达标 → 改写被拒（applied=False）；
   显式 outcome 绕过闸门。
4. attention_observation 提供的预算估计与闸门口径与纯函数一致。

需 docker + psycopg；ZKC_RUN_PG_TESTS=0 跳过。
"""
from __future__ import annotations

import os
import pathlib
import unittest
from datetime import date, datetime, timedelta
from uuid import uuid4

from zkc import scheduling as S
from zkc.repository import get_storage
from zkc.repository.models import AttentionObservation, Claim, Context, Node

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
ALL_UP_SQL = "\n".join(
    sorted((MIGRATIONS_DIR / p).read_text()
           for p in [f.name for f in MIGRATIONS_DIR.glob("*.up.sql")])
)


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgSchedulingTest(unittest.TestCase):
    TEST_DB = "zkc_scheduling_test"

    @classmethod
    def setUpClass(cls):
        import psycopg

        cls._orig_dsn = os.environ.get("ZKC_PG_DSN")
        base_dsn = cls._orig_dsn or "postgresql://postgres:zkc@localhost:55433/zkc_dev"
        cls._pg = psycopg.connect(base_dsn.replace("/zkc_dev", "/postgres"), autocommit=True)
        cls._pg.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        cls._pg.execute(f'CREATE DATABASE "{cls.TEST_DB}"')
        cls._pg.close()
        cls._test_dsn = base_dsn.replace("/zkc_dev", f"/{cls.TEST_DB}")
        c = psycopg.connect(cls._test_dsn, autocommit=True)
        c.execute(ALL_UP_SQL)
        c.close()
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    @classmethod
    def tearDownClass(cls):
        import psycopg

        c = psycopg.connect(cls._test_dsn.replace(f"/{cls.TEST_DB}", "/postgres"), autocommit=True)
        c.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        c.close()
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()
        self.now = datetime(2026, 6, 1, 12, 0, 0)
        self._seed()

    def _save(self, title, content=None, **kw):
        kw.setdefault("track", "dynamic")
        return self.store.nodes.save(Node(title=title, content=content, decay_score=0.0, **kw))

    def _seed(self):
        self.s1 = self._save("S1", "static anchor", track="static")
        self.proj = self.store.contexts.save(Context(scope="self_loop", title="项目 A"))
        self.topic = self.store.contexts.save(Context(scope="higher_dim", title="主题 B"))
        self.d1 = self._save("D1", "下周三前提交评审材料")     # horizon -> 7
        self.d2 = self._save("D2", "项目 A 的当前阻塞点")      # self_loop -> 3
        self.d3 = self._save("D3", "主题 B 的长期观察")        # higher_dim -> 14
        self.d4 = self._save("D4", "随手记的灵感")            # orphan -> 7
        self.d5 = self._save("D5", "已被提炼过的记录")         # captured -> 28
        self.d6 = self._save("D6", "3 天内跟进反馈")          # horizon -> 3
        self.d7 = self._save("D7", "人工固定节奏", review_interval=timedelta(days=10),
                             interval_source="human")          # immune
        self.store.contexts.add_member(self.proj.id, self.d1.id)
        self.store.contexts.add_member(self.proj.id, self.d2.id)
        self.store.contexts.add_member(self.topic.id, self.d3.id)
        c1 = self.store.claims.save(Claim(
            statement="D5 的结论已被提炼", level="insight", evidence_refs=[self.d5.id]))
        self.store.edges.link(self.s1.id, self.d5.id, "derived_from")

    # ---- L1 ----
    def test_assign_baselines_ladder(self):
        S.assign_baselines(self.store)
        g = self.store.nodes.get
        self.assertEqual(g(self.d1.id).baseline_interval, timedelta(days=7))   # horizon
        self.assertEqual(g(self.d2.id).baseline_interval, timedelta(days=3))   # self_loop
        self.assertEqual(g(self.d3.id).baseline_interval, timedelta(days=14))  # higher_dim
        self.assertEqual(g(self.d4.id).baseline_interval, timedelta(days=7))   # orphan
        self.assertEqual(g(self.d5.id).baseline_interval, timedelta(days=28))  # captured
        self.assertEqual(g(self.d6.id).baseline_interval, timedelta(days=3))   # horizon
        # human 豁免：保持原 10，未改
        self.assertEqual(g(self.d7.id).review_interval, timedelta(days=10))
        self.assertEqual(g(self.d7.id).interval_source, "human")

    # ---- L2 + 回滚 ----
    def test_fit_budget_defers_and_reverts(self):
        S.assign_baselines(self.store)
        # 极小预算 -> 必须延后
        res = S.fit_budget(self.store, budget_per_day=0.01)
        self.assertTrue(res["applied"])
        self.assertIn("transform_id", res)
        tid = res["transform_id"]
        # 至少一个被延后到 > 原基线
        changed = [d for d in res["degraded"]]
        self.assertTrue(changed)
        # 回滚：全部恢复到延前
        n = S.revert_interval_transform(self.store, tid)
        self.assertEqual(n, len(changed))
        # 回滚后 d4 仍是基线 7（未延后）
        self.assertEqual(self.store.nodes.get(self.d4.id).review_interval, timedelta(days=7))

    def test_fit_budget_warmup_passive(self):
        S.assign_baselines(self.store)
        res = S.fit_budget(self.store, budget_per_day=None)
        self.assertFalse(res["applied"])
        self.assertIn("warm-up", res["note"])

    # ---- L3 闸门 + 显式标注绕过 ----
    def _recent_obs_days(self, n=10):
        """返回距今天 n 天内的日期（避开 PG list_recent 的 current_date-30 过滤）。"""
        today = date.today()
        return [today - timedelta(days=k) for k in range(1, n + 1)]

    def test_adapt_interval_warmup_gate_open(self):
        S.assign_baselines(self.store)
        # 无观测 -> 样本不足 -> 闸门放行（gate open），改写发生
        r = S.adapt_interval(self.store, self.d4.id, decay_at_review=0.95)
        self.assertTrue(r["applied"])

    def test_adapt_interval_gate_closed_without_labels(self):
        S.assign_baselines(self.store)
        # 写一批「完成但未标注」观测 -> 率 0% -> 闸门关闭 -> 改写被拒
        # 窗口 7 天、每天 completed=2 -> 窗口内 14 次完成 ≥10 样本，闸门可真正关闭
        for d in self._recent_obs_days(10):
            self.store.attention.record_observation(AttentionObservation(
                day=d, pushed=2, completed=2, queue_remaining=0, labeled_completed=0))
        r = S.adapt_interval(self.store, self.d4.id, decay_at_review=0.95)
        self.assertFalse(r["applied"])
        self.assertIn("label gate closed", r["reason"])

    def test_adapt_interval_explicit_outcome_bypasses_gate(self):
        S.assign_baselines(self.store)
        # 闸门关闭状态下，显式 outcome 仍可改写
        for d in self._recent_obs_days(10):
            self.store.attention.record_observation(AttentionObservation(
                day=d, pushed=2, completed=2, queue_remaining=0, labeled_completed=0))
        before = self.store.nodes.get(self.d4.id).review_interval
        r = S.adapt_interval(self.store, self.d4.id, decay_at_review=0.5,
                             outcome="too_late")
        self.assertTrue(r["applied"])
        after = self.store.nodes.get(self.d4.id).review_interval
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()

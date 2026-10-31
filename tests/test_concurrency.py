"""Pg node 并发写版本链的原子性验证（P1.2 并发加固回归测试）。

主张：两条独立连接对同一 node 做并发 save 更新时，append-only 版本链不会错乱——
不会出现「两事务同时读到旧态、各自快照」导致的重复历史或丢失更新。

机制：PgNodeRepository 在「单事务内」先 `SELECT ... FOR UPDATE` 锁住行，再快照进
node_history，最后 UPDATE 当前行。FOR UPDATE 让后到的事务阻塞到先到者提交，从而串
行化，保证版本顺序与锁获取顺序一致（tx_from 用 DB now()，与锁序严格单调）。

测试手法（确定性复现竞态）：两条线程各持一个 repo，共享一个 threading.Barrier(2)
作为 lock_hook——双方在「加锁前」对齐到同一屏障。这样：
- 有 FOR UPDATE（当前实现）：T2 阻塞在锁上直到 T1 提交，读到 T1 已写版本再快照，
  最终 history = [v0, v1, v2]，断言通过。
- 无 FOR UPDATE（若回退）：两线程同时在屏障后读到旧态各自快照，history 出现重复
  v0 或丢失 v1，断言失败——从而把并发回归变成可执行的红灯。

仅 Pg 实现需要真实多连接；无 docker/psycopg 时整类 skip（不视为失败）。
"""
from __future__ import annotations

import os
import pathlib
import threading
import unittest
from datetime import timedelta

import psycopg

from zkc.repository.models import Node, Track
from zkc.repository.pg import PgNodeRepository

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
ALL_UP_SQL = "\n".join(
    sorted(
        (MIGRATIONS_DIR / p).read_text()
        for p in [f.name for f in MIGRATIONS_DIR.glob("*.up.sql")]
    )
)

DEFAULT_DSN = os.environ.get("ZKC_PG_DSN", "postgresql://postgres:zkc@localhost:55433/zkc_dev")
TEST_DB = "zkc_conc_test"


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 并发测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgNodeConcurrentWriteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_dsn = os.environ.get("ZKC_PG_DSN")
        base = cls._orig_dsn or DEFAULT_DSN
        cls._admin = psycopg.connect(base.replace("/zkc_dev", "/postgres"), autocommit=True)
        cls._admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        cls._admin.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls._admin.close()
        cls._test_dsn = base.replace("/zkc_dev", f"/{TEST_DB}")
        c = psycopg.connect(cls._test_dsn, autocommit=True)
        c.execute(ALL_UP_SQL)
        c.close()
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    @classmethod
    def tearDownClass(cls):
        drop_c = psycopg.connect(
            cls._test_dsn.replace(f"/{TEST_DB}", "/postgres"), autocommit=True
        )
        drop_c.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        drop_c.close()
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn

    def setUp(self):
        c = psycopg.connect(self._test_dsn, autocommit=True)
        c.execute("DELETE FROM public.node_history; DELETE FROM public.node;")
        c.close()

    def test_concurrent_updates_produce_correct_version_chain(self):
        # 两条独立连接 → 两条独立事务，真实并发
        conn1 = psycopg.connect(self._test_dsn)
        conn2 = psycopg.connect(self._test_dsn)
        barrier = threading.Barrier(2, timeout=20)
        # lock_hook 在「加行锁前」对齐两条线程，确保竞态窗口被确定性打开
        repo1 = PgNodeRepository(conn1, lock_hook=lambda: barrier.wait())
        repo2 = PgNodeRepository(conn2, lock_hook=lambda: barrier.wait())

        # 基线 v0（单线程，走 INSERT 路径，不入 history）
        node = Node(title="v0", track=Track.DYNAMIC.value, decay_score=0.0)
        repo1.save(node)
        nid = node.id

        errors: list[str] = []

        def worker(repo: PgNodeRepository, new_title: str) -> None:
            try:
                n = repo.get(nid)
                n.title = new_title
                repo.save(n)
            except Exception as e:  # noqa: BLE001 — 并发异常需捕获后断言
                errors.append(repr(e))

        t1 = threading.Thread(target=worker, args=(repo1, "v1"))
        t2 = threading.Thread(target=worker, args=(repo2, "v2"))
        t1.start()
        t2.start()
        t1.join(30)
        t2.join(30)

        self.assertEqual(errors, [], f"并发写入抛错: {errors}")

        # 初始 v0 不入 history；两次并发更新 → 2 条历史 + 1 当前态 = 3 个版本
        hist = repo1.history(nid)
        self.assertEqual(
            len(hist), 3,
            f"期望 3 个版本（v0 历史 + 一次并发写历史 + 当前态），实际 {len(hist)}: "
            f"{[h.title for h in hist]}",
        )
        # 当前态恒为最后版本（tx_from 最大）且开放；clock_timestamp 反映提交顺序
        self.assertIsNone(hist[-1].tx_to, "当前态应开放（tx_to 为 NULL）")
        txs = [h.tx_from for h in hist]
        self.assertEqual(txs, sorted(txs), f"版本链未按 tx_from 单调有序: {txs}")
        # 无版本丢失：基线 v0 与两次并发写（v1、v2）都出现在链中（last-writer-wins
        # 决定谁是 current，另一个必在历史里，故三者俱全）
        self.assertEqual(
            {h.title for h in hist}, {"v0", "v1", "v2"},
            f"版本链缺失，期望含 v0/v1/v2，实际 {[h.title for h in hist]}",
        )
        # 历史版本均已闭合（tx_to 非空），仅当前态开放
        self.assertTrue(
            all(h.tx_to is not None for h in hist[:-1]), "历史版本应已闭合"
        )
        # 当前态与直接 get 一致
        self.assertEqual(repo1.get(nid).title, hist[-1].title)

        conn1.close()
        conn2.close()

    def test_concurrent_decay_and_interval_do_not_corrupt_chain(self):
        # 第二形态：一条线程改 decay、一条改 interval，并发打到同一 node，
        # 验证两者不互相覆盖事实。c2 决议 A-1a（2026-10-31）：set_interval 改事实
        # → 先快照再改；update_decay 改派生量 decay_score → 不写历史、不 bump tx_from。
        conn1 = psycopg.connect(self._test_dsn)
        conn2 = psycopg.connect(self._test_dsn)
        barrier = threading.Barrier(2, timeout=20)
        repo1 = PgNodeRepository(conn1, lock_hook=lambda: barrier.wait())
        repo2 = PgNodeRepository(conn2, lock_hook=lambda: barrier.wait())

        node = repo1.save(Node(title="base", track=Track.DYNAMIC.value, decay_score=0.0))
        nid = node.id

        errors: list[str] = []

        def w_decay():
            try:
                repo1.update_decay(nid, 0.55)
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        def w_interval():
            try:
                repo2.set_interval(nid, timedelta(days=3), "auto", "c")
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        t1 = threading.Thread(target=w_decay)
        t2 = threading.Thread(target=w_interval)
        t1.start()
        t2.start()
        t1.join(30)
        t2.join(30)

        self.assertEqual(errors, [], f"并发 decay/interval 抛错: {errors}")

        got = repo1.get(nid)
        self.assertEqual(got.decay_score, 0.55)
        self.assertEqual(got.review_interval, timedelta(days=3))

        # 并发更新：set_interval 改事实 → 快照（v0→v1）；update_decay 改派生量 → 不快照。
        # 故历史 = 1 条快照 + 1 当前 = 2 版本；decay/interval 均被保留、互不覆盖。
        hist = repo1.history(nid)
        self.assertEqual(len(hist), 2, f"期望 2 个版本（set_interval 快照 + 当前态），实际 {len(hist)}")
        self.assertEqual(hist[-1].decay_score, 0.55)
        self.assertEqual(hist[-1].review_interval, timedelta(days=3))

        conn1.close()
        conn2.close()


if __name__ == "__main__":
    unittest.main()

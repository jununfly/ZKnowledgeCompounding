"""zkc/ingest 业务层集成测试（P1.2 后续 · Item B：业务代码切到 get_storage()）。

主张：领域操作流程（摄入 → 入队复审 → 写注意力埋点 → 查到期）全部经 repository seam，
不依赖 docker / psql / psycopg。同一份 `run_flow` 在内存 fake 与真实 PG 上都成立。
内存测试无 DB 依赖；Pg 测试需 docker zkc-spike-pg + psycopg，否则整类 skip。
"""
from __future__ import annotations

import os
import pathlib
import unittest
from datetime import datetime, timedelta
from uuid import UUID

from zkc.repository import get_storage
from zkc.ingest import (
    ingest_node,
    list_due_for_review,
    record_attention_day,
    record_review,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
ALL_UP_SQL = "\n".join(
    sorted((MIGRATIONS_DIR / p).read_text() for p in [f.name for f in MIGRATIONS_DIR.glob("*.up.sql")])
)


def run_flow(store) -> None:
    now = datetime.now()

    # 1) 摄入一个动态轨 node（衰减 0，等待后续调度打分）
    n = ingest_node(title="t", content="c", track="dynamic", store=store)
    assert isinstance(n.id, UUID)
    got = store.nodes.get(n.id)
    assert got is not None and got.title == "t" and got.track == "dynamic"

    # 2) 入队一条复审项
    item_id = record_review(node_id=n.id, action="distill", reason="demo", store=store)
    open_items = store.review_queue.list_open()
    assert any(i.id == item_id for i in open_items)

    # 3) 写一条每日注意力观测埋点
    day = (now - timedelta(days=1)).date()
    record_attention_day(
        day=day, pushed=5, completed=3, queue_remaining=2,
        labeled_completed=2, store=store,
    )
    obs = store.attention.get(day)
    assert obs is not None and obs.completed == 3 and obs.labeled_completed == 2

    # 4) 调度器查到期：先衰减到 0.7 并设复审节奏，再制造「已到期」
    store.nodes.update_decay(n.id, 0.7)
    store.nodes.set_interval(n.id, timedelta(days=1), "auto", "demo")
    cur = store.nodes.get(n.id)
    cur.last_reviewed_at = now - timedelta(days=10)
    store.nodes.save(cur)
    due = list_due_for_review(as_of=now, store=store)
    assert n.id in {x.id for x in due}

    # 5) 版本链：该 node 至少有 2 个版本（首存 + 改 last_reviewed_at）
    hist = store.nodes.history(n.id)
    assert len(hist) >= 2


class MemoryBusinessFlowTest(unittest.TestCase):
    def test_flow(self):
        store = get_storage("memory")
        run_flow(store)


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgBusinessFlowTest(unittest.TestCase):
    TEST_DB = "zkc_biz_test"

    @classmethod
    def setUpClass(cls):
        import psycopg

        # 保存原始 DSN，tearDownClass 还原，避免污染其它 Pg 测试共享的全局环境变量
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

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()

    def test_flow(self):
        run_flow(self.store)

    @classmethod
    def tearDownClass(cls):
        import psycopg

        c = psycopg.connect(cls._test_dsn.replace(f"/{cls.TEST_DB}", "/postgres"), autocommit=True)
        c.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        c.close()
        # 还原全局 DSN，防止泄漏到并行/后续 Pg 测试
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn


if __name__ == "__main__":
    unittest.main()

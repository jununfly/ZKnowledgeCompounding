"""S1 · 墓碑软删 repository 行为契约（TDD 红→绿）。

同一份契约跑 memory + pg 双后端（Pg 需 docker zkc-spike-pg，否则跳过）。
S1 只测「墓碑读写 / 版本链 / 候选筛选」，不测可见性谓词（S2）、引用闸门（S4）、
真删 CASCADE（S5）——那些由各自切片的测试覆盖，避免同义反复。
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

from zkc.repository import get_storage
from zkc.repository.models import Node

from zkc import migrate


def run_tombstone_contract(store) -> None:
    now = datetime.now(timezone.utc)

    # 1) 保存节点，deleted_at 默认 None（未墓碑）
    n = store.nodes.save(Node(track="dynamic", title="tomb-target", decay_score=0.5))
    assert isinstance(n.id, object)
    got = store.nodes.get(n.id)
    assert got is not None and got.deleted_at is None, "新节点 deleted_at 应为 None"

    # 2) tombstone：置墓碑时刻 + version_seq 自增 + 进版本链
    v_before = got.version_seq
    hist_before = len(store.nodes.history(n.id))
    store.nodes.tombstone(n.id, now)
    marked = store.nodes.get(n.id)
    assert marked is not None and marked.deleted_at == now, "tombstone 应写 deleted_at=now"
    assert marked.version_seq == v_before + 1, "tombstone 应 bump version_seq"
    hist_after = store.nodes.history(n.id)
    assert len(hist_after) == hist_before + 1, "tombstone 应进版本链（snapshot 一行）"
    assert any(
        h.deleted_at is None and h.tx_to is not None for h in hist_after
    ), "历史版本应保留未墓碑态且被闭合"

    # 3) list_tombstones_before：cutoff 语义（墓碑时刻 <= cutoff）
    before = store.nodes.list_tombstones_before(now - timedelta(seconds=1))
    assert n.id not in {x.id for x in before}, "早于墓碑时刻的 cutoff 不应命中"
    at = store.nodes.list_tombstones_before(now)
    assert n.id in {x.id for x in at}, "等于墓碑时刻的 cutoff 应命中（<=）"
    after = store.nodes.list_tombstones_before(now + timedelta(days=1))
    assert n.id in {x.id for x in after}, "晚于墓碑时刻的 cutoff 应命中"

    # 4) restore：清墓碑 + version_seq 自增 + 再进版本链
    v_marked = marked.version_seq
    store.nodes.restore(n.id)
    restored = store.nodes.get(n.id)
    assert restored is not None and restored.deleted_at is None, "restore 应清 deleted_at"
    assert restored.version_seq == v_marked + 1, "restore 应 bump version_seq"
    assert n.id not in {
        x.id for x in store.nodes.list_tombstones_before(now + timedelta(days=1))
    }, "restore 后不应再出现在墓碑候选"

    # 5) 幂等边界：重复 tombstone / restore 不炸且保持态
    store.nodes.tombstone(n.id, now)
    store.nodes.tombstone(n.id, now + timedelta(hours=1))
    twice = store.nodes.get(n.id)
    assert twice is not None and twice.deleted_at == now, "对已墓碑节点重复 tombstone 应保持原墓碑时刻"
    store.nodes.restore(n.id)
    store.nodes.restore(n.id)
    assert store.nodes.get(n.id).deleted_at is None, "重复 restore 应保持未墓碑"


class MemoryTombstoneTest(unittest.TestCase):
    def test_contract(self):
        run_tombstone_contract(get_storage("memory"))


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgTombstoneTest(unittest.TestCase):
    TEST_DB = "zkc_tombstone_s1_test"

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
        migrate.apply_all(cls.TEST_DB)
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()

    def test_contract(self):
        run_tombstone_contract(self.store)

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


if __name__ == "__main__":
    unittest.main()

"""zkc/repository 的 TDD 测试（P1.2）。

核心主张：seam 可替换 → 同一份「行为契约」同时跑在内存 fake 与真实 Postgres 上，
两份实现行为一致，应用层不感知底层。Memory 测试无 DB 依赖；Pg 测试需 docker 容器
`zkc-spike-pg` 在跑且 psycopg 可装，否则整类 skip（不视为失败）。
"""
from __future__ import annotations

import os
import pathlib
import unittest
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from zkc.repository import get_storage
from zkc.repository.models import (
    AttentionObservation,
    Claim,
    Context,
    Edge,
    Node,
    ReviewItem,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"
# 按 version 升序拼接全部 up 脚本（含 0002 node_history），保证测试库 schema 与磁盘一致
ALL_UP_SQL = "\n".join(
    sorted(
        (MIGRATIONS_DIR / p).read_text()
        for p in [f.name for f in MIGRATIONS_DIR.glob("*.up.sql")]
    )
)


def _emb768() -> list[float]:
    return [float(i) / 768.0 for i in range(768)]


def run_contract(store) -> None:
    """同一份行为契约，两个实现都应满足。返回无断言失败即通过。"""
    now = datetime.now()

    # ---- Node：保存 / 读取 / 按轨列表 ----
    n1 = store.nodes.save(Node(track="dynamic", title="t1", decay_score=0.0, embedding=_emb768()))
    assert isinstance(n1.id, UUID)
    got = store.nodes.get(n1.id)
    assert got is not None and got.title == "t1" and got.track == "dynamic"
    assert got.embedding is not None and len(got.embedding) == 768

    n2 = store.nodes.save(Node(track="static", title="t2"))
    tracks = store.nodes.list_by_track("dynamic")
    assert {x.id for x in tracks} == {n1.id}

    # ---- Node：到期复审判定 ----
    due = store.nodes.save(Node(
        track="dynamic", title="due", decay_score=0.7,
        review_interval=timedelta(days=1), last_reviewed_at=now - timedelta(days=10),
    ))
    not_due = store.nodes.save(Node(
        track="dynamic", title="notdue", decay_score=0.3,
        review_interval=timedelta(days=1), last_reviewed_at=now - timedelta(days=10),
    ))
    no_interval = store.nodes.save(Node(
        track="dynamic", title="noiv", decay_score=0.9, last_reviewed_at=now,
    ))
    due_list = store.nodes.list_due_for_review(now)
    assert due.id in {x.id for x in due_list}
    assert not_due.id not in {x.id for x in due_list}
    assert no_interval.id not in {x.id for x in due_list}

    # ---- Node：decay / interval 写入 ----
    store.nodes.update_decay(n1.id, 0.42)
    assert store.nodes.get(n1.id).decay_score == 0.42
    # c2 决议 A-1a/A-2（2026-10-31）：decay_score 是派生量，update_decay 不写历史快照、
    # 不 bump tx_from（tx_from 始终标记「上次事实变更」）。两后端语义一致。
    hist_after_decay = store.nodes.history(n1.id)
    # n1 此前仅首存一次（v0，无编辑）→ 历史 = [当前态]，update_decay 不应新增版本
    assert len(hist_after_decay) == 1, (
        f"update_decay 不应产生历史快照，收到 {len(hist_after_decay)}"
    )
    assert store.nodes.get(n1.id).tx_from == n1.tx_from, "update_decay 不应 bump tx_from"
    store.nodes.set_interval(due.id, timedelta(days=7), "auto", "test")
    assert store.nodes.get(due.id).review_interval == timedelta(days=7)

    # ---- Node：双时态版本链（append-only）----
    # 首存 v0，再改 title 存 v1 → 旧版进 node_history，当前态为 v1，历史不可变
    v = store.nodes.save(Node(track="dynamic", title="v0", decay_score=0.0))
    assert isinstance(v.id, UUID)
    v.title = "v1"
    store.nodes.save(v)
    got_v = store.nodes.get(v.id)
    assert got_v.title == "v1" and got_v.tx_to is None  # 当前态闭合标志为 NULL
    hist = store.nodes.history(v.id)
    assert len(hist) == 2, f"期望 2 个版本（v0 历史 + v1 当前），收到 {len(hist)}"
    assert hist[0].title == "v0" and hist[-1].title == "v1"
    # 历史版本不可变：v0 仍是 v0
    assert hist[0].tx_to is not None, "历史版本应已被闭合（tx_to 非空）"

    # ---- Claim：保存 / 溯源查询 ----
    tf = store.record_transform("test", {"k": "v"})
    assert isinstance(tf, UUID)
    c1 = store.claims.save(Claim(
        statement="s1", evidence_refs=[n1.id], produced_by=tf,
        faithfulness_status="auto_passed",
    ))
    c2 = store.claims.save(Claim(statement="s2", evidence_refs=[n2.id]))
    by_ev = store.claims.list_by_evidence(n1.id)
    assert {x.id for x in by_ev} == {c1.id}

    # ---- Edge：连接 / 查询 / 删除 ----
    e = store.edges.link(n1.id, n2.id, "supports", weight=0.5, produced_by=tf)
    assert isinstance(e.id, UUID)
    edges = store.edges.list_for_node(n1.id)
    assert len(edges) == 1 and edges[0].kind == "supports"
    store.edges.delete(e.id)
    assert store.edges.list_for_node(n1.id) == []

    # ---- Context：装配 / 成员 / 反向查询 ----
    ctx = store.contexts.save(Context(scope="higher_dim", label="ctx1"))
    store.contexts.add_member(ctx.id, n1.id, weight=2.0)
    store.contexts.add_member(ctx.id, n2.id)
    members = store.contexts.list_members(ctx.id)
    assert set(members) == {n1.id, n2.id}
    ctxs_for_n1 = store.contexts.list_for_node(n1.id)
    assert ctxs_for_n1[0].id == ctx.id

    # ---- ReviewQueue：入队 / 弹出 / 解决 ----
    item = store.review_queue.enqueue(n1.id, "distill", "needs distill")
    assert isinstance(item.id, UUID) and item.resolved is False
    open_items = store.review_queue.pop_open()
    assert item.id in {x.id for x in open_items}
    store.review_queue.resolve(item.id)
    assert store.review_queue.list_open() == []

    # ---- Attention：观测 / 读取 / 最近 ----
    day = (now - timedelta(days=1)).date()
    store.attention.record_observation(AttentionObservation(
        day=day, pushed=5, completed=3, queue_remaining=2, labeled_completed=2,
    ))
    obs = store.attention.get(day)
    assert obs is not None and obs.completed == 3 and obs.labeled_completed == 2


class MemoryRepositoryTest(unittest.TestCase):
    def test_contract(self):
        store = get_storage("memory")
        run_contract(store)


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgRepositoryTest(unittest.TestCase):
    TEST_DB = "zkc_repo_test"

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
        # 在测试库上跑全部迁移（含 0002 node_history）
        cls._test_dsn = base_dsn.replace("/zkc_dev", f"/{cls.TEST_DB}")
        c = psycopg.connect(cls._test_dsn, autocommit=True)
        c.execute(ALL_UP_SQL)
        c.close()
        os.environ["ZKC_PG_DSN"] = cls._test_dsn

    def setUp(self):
        self.store = get_storage("pg")
        self.store.clear_all()

    def test_contract(self):
        run_contract(self.store)

    @classmethod
    def tearDownClass(cls):
        import psycopg

        c = psycopg.connect(cls._test_dsn.replace(f"/{cls.TEST_DB}", "/postgres"), autocommit=True)
        c.execute(f'DROP DATABASE IF EXISTS "{cls.TEST_DB}" WITH (FORCE)')
        c.close()
        # 还原全局 DSN
        if cls._orig_dsn is None:
            os.environ.pop("ZKC_PG_DSN", None)
        else:
            os.environ["ZKC_PG_DSN"] = cls._orig_dsn


if __name__ == "__main__":
    unittest.main()

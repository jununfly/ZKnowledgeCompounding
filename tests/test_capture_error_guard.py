"""快捕获错误守卫回归测试（2026-11-02 实跑 500 根因修复）。

两个根因、两组测试：
1. schema 漂移：0001 对 review_queue.action 的 CHECK 只有
   ('distill','archive','abstain')，P2.2 弃权路径入队 'classify' ——
   memory 后端无校验（单测全绿），PG 实库必现 CheckViolation（观察期
   lexical gate 恒弃权 → 每次捕获必触发）。迁移 0010 放宽约束。
   → PG 测试：真实迁移库上捕获弃权笔记，classify 行必须能落库。
2. 事务投毒：pg 各 repo「成功即 commit」，失败路径无人回滚，一次
   CheckViolation 后共享连接 aborted，后续请求全部 InFailedSqlTransaction。
   修复 = Storage.rollback()（pg 实 / memory no-op）+ web 异常守卫。
   → memory HTTP 测试：注入异常后 /capture 返回 JSON detail，且后续请求正常。
"""
from __future__ import annotations

import os
import unittest

from zkc import migrate
from zkc.ingest import list_pending_classify, CLASSIFY_ACTION
from zkc.repository import get_storage
from zkc.routing import DecisionRouter
from zkc.web.app import create_app

from tests.test_web_capture import FakeClient


class _FailingEnqueue:
    """替换 review_queue.enqueue，模拟存储层抛错（事务投毒源）。"""

    def __init__(self, inner):
        self._inner = inner

    def __call__(self, *a, **kw):
        raise RuntimeError("injected storage failure")


class MemoryErrorGuardHTTPTest(unittest.TestCase):
    """异常守卫：500 必须 JSON（前端按 JSON 解析）且连接不投毒。"""

    def _app(self):
        return create_app(
            store=get_storage("memory"),
            decision_router=DecisionRouter(FakeClient({"track": "dynamic", "confidence": 0.9})),
            lexical_router=None,
        )

    def test_get_page_ok(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("httpx/TestClient 未安装")
        c = TestClient(self._app())
        self.assertEqual(c.get("/").status_code, 200)

    def test_500_is_json_and_connection_reusable(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("httpx/TestClient 未安装")

        store = get_storage("memory")
        # 走弃权路径才会调 review_queue.enqueue（注入点才能被触发）
        app = create_app(
            store=store,
            decision_router=DecisionRouter(FakeClient({"track": "vague", "confidence": 0.1})),
            lexical_router=None,
        )
        c = TestClient(app, raise_server_exceptions=False)
        # 捕获路由用 store 调 ingest → nodes.save 成功 → review_queue.enqueue 抛错。
        inner = store.review_queue.enqueue
        store.review_queue.enqueue = _FailingEnqueue(inner)
        try:
            r = c.post("/capture", data={"note": "触发注入失败"})
            self.assertEqual(r.status_code, 500)
            j = r.json()
            self.assertIn("detail", j)
            self.assertIn("RuntimeError", j["detail"])
        finally:
            store.review_queue.enqueue = inner

        # 守卫回滚后，同一 app 的后续请求不受影响（走弃权路径正常落库）
        r2 = c.post("/capture", data={"note": "明天要开会讨论需求"})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["track"], "unrouted")


@unittest.skipUnless(
    os.environ.get("ZKC_RUN_PG_TESTS", "1") == "1",
    "Pg 集成测试需要 docker zkc-spike-pg + psycopg；设 ZKC_RUN_PG_TESTS=0 跳过",
)
class PgClassifyConstraintTest(unittest.TestCase):
    """回归：真实迁移库上，弃权捕获入队 action='classify' 必须成功（0010）。"""

    TEST_DB = "zkc_capture_guard_test"

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

    def _offline_capture(self, note):
        from zkc.web.app import capture_note

        return capture_note(
            note, store=self.store,
            decision_router=DecisionRouter(FakeClient(None)),
            lexical_router=None, llm_available=False,
        )

    def test_abstain_capture_lands_classify_row(self):
        res = self._offline_capture("没想清楚的事")
        self.assertEqual(res["track"], "unrouted")
        items = list_pending_classify(store=self.store)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].action, CLASSIFY_ACTION)

    def test_violation_then_rollback_then_recover(self):
        # 1) 先正常捕获一条（成功态）
        self._offline_capture("第一条")
        # 2) 人为制造 CheckViolation（约束虽放宽，'bogus' 仍非法）
        from psycopg.errors import CheckViolation

        with self.assertRaises(CheckViolation):
            self.store.review_queue.enqueue(
                self.store.nodes.list_by_track("unrouted")[0].id, "bogus", None)
        # 3) 守卫回滚 → 连接复活，后续捕获照常
        self.store.rollback()
        res = self._offline_capture("回滚后第二条")
        self.assertEqual(res["track"], "unrouted")
        self.assertEqual(len(list_pending_classify(store=self.store)), 2)

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

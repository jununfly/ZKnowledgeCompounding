"""zkc/migrate.py 的集成测试（P1.1）—— 打真实 docker 容器里的 zkc_dev 库。

跑测试前不需要手工准备环境：本文件会自己建库、回滚到空、再升级。
需要 docker 容器 `zkc-spike-pg` 在跑（spike 01 起的那个）。

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from zkc import migrate

DB = "zkc_dev_test"


def _scalar(sql: str) -> str:
    return migrate.psql(DB, sql)


def setUpModule() -> None:  # noqa: N802
    migrate.ensure_database(DB)
    migrate.bootstrap(DB)
    # 从干净状态开始：回滚所有已应用迁移，保证可重复跑
    migrate.cmd_downgrade(DB, to=None)
    migrate.cmd_upgrade(DB, to=None)


def tearDownModule() -> None:  # noqa: N802
    migrate.cmd_downgrade(DB, to=None)
    migrate.psql("postgres", f'DROP DATABASE IF EXISTS "{DB}";')


class TestBaselineApplied(unittest.TestCase):
    def test_migration_recorded(self):
        self.assertIn("0001", migrate.applied(DB))

    def test_verify_sha_matches(self):
        self.assertEqual(migrate.cmd_verify(DB), 0)

    def test_core_tables_exist(self):
        out = _scalar(
            "SELECT string_agg(tablename, ',' ORDER BY tablename) FROM pg_tables "
            "WHERE schemaname='public';"
        )
        tables = set(out.split(","))
        for t in ("node", "meta_claim", "edge", "context", "context_member",
                  "citation", "transform", "modeling_artifact", "review_queue",
                  "interval_adjustment", "attention_observation", "schema_migration"):
            self.assertIn(t, tables, f"缺表 {t}")


class TestDriftFixes(unittest.TestCase):
    """这三处正是本次迁移相对遗留库的修正，各自都要有回归保护。"""

    def test_embedding_is_768_not_1024(self):
        """R16 / spike 14：1024 是占位，768 才是实测编码器维度。"""
        n = _scalar(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid='public.node'::regclass AND attname='embedding';"
        )
        self.assertEqual(n.strip(), "768", f"embedding 维度错了：{n}")

    def test_d9_faithfulness_fields_present(self):
        out = _scalar(
            "SELECT string_agg(column_name, ',' ORDER BY column_name) "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='meta_claim';"
        )
        cols = set(out.split(","))
        for c in ("faithfulness_status", "faithfulness_route", "judge_raw",
                  "judge_model", "human_verdict", "human_verdict_at"):
            self.assertIn(c, cols, f"缺 D9 字段 {c}")

    def test_context_has_no_member_nodes(self):
        """A11 / spike 06：member_nodes 已被 context_member 取代，不得复活。"""
        n = _scalar(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='context' "
            "AND column_name='member_nodes';"
        )
        self.assertEqual(n.strip(), "0")


class TestInvariants(unittest.TestCase):
    """schema 级强制的不变量（不能只靠应用层自觉）。"""

    def test_claim_requires_evidence(self):
        """溯源在存储层强制：无 evidence_refs 的 claim 必须被拒。"""
        with self.assertRaises(RuntimeError):
            migrate.psql(
                DB,
                "INSERT INTO meta_claim (statement) VALUES ('no evidence');",
                single_transaction=True,
            )

    def test_decay_score_bounded(self):
        with self.assertRaises(RuntimeError):
            migrate.psql(
                DB,
                "INSERT INTO node (title, decay_score) VALUES ('bad', 1.5);",
                single_transaction=True,
            )

    def test_labeled_le_completed(self):
        """D8：标注完成数不得大于完成数（防埋点污染）。"""
        with self.assertRaises(RuntimeError):
            migrate.psql(
                DB,
                "INSERT INTO attention_observation (day, pushed, completed, "
                "queue_remaining, labeled_completed) "
                "VALUES ('2026-10-31', 5, 2, 1, 9);",
                single_transaction=True,
            )


class TestReplay(unittest.TestCase):
    """迁移必须能降/升重放——容器状态可被 docker 重启丢掉。"""

    def test_downgrade_removes_everything(self):
        migrate.cmd_downgrade(DB, to=None)
        out = _scalar(
            "SELECT count(*) FROM pg_tables WHERE schemaname='public' "
            "AND tablename NOT LIKE 'schema_migration';"
        )
        self.assertEqual(out.strip(), "0")
        self.assertEqual(migrate.applied(DB), {})
        # 恢复，别影响同模块其它测试
        migrate.cmd_upgrade(DB, to=None)

    def test_upgrade_is_idempotent(self):
        before = migrate.applied(DB)
        migrate.cmd_upgrade(DB, to=None)   # 已应用 -> 应为空操作
        self.assertEqual(migrate.applied(DB), before)


if __name__ == "__main__":
    unittest.main()

"""S3 · 墓碑人环入口红→绿（CLI mark/restore + operator + 审计事件）。

S3 只测「人环操作 + 审计留痕 + 不得自动标记」；真删闸门(S4)/CASCADE(S5)/月扫(S6)
由各自切片测。CLI 经 dispatch(parse_args(...), store=...) 注入，无需真实服务。
"""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from zkc.cli import dispatch, parse_args
from zkc.repository import get_storage
from zkc.repository.models import Node
from zkc.tombstone import mark_tombstone, restore_node, list_audit_events


class TombstoneHumanTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.now = datetime.now(timezone.utc)
        n = self.store.nodes.save(Node(track="dynamic", title="victim", decay_score=0.9))
        self.nid = n.id

    def test_mark_writes_tombstone_and_audit(self):
        res = mark_tombstone(
            self.store, self.nid, operator="zj", at=self.now, reason="no valid content")
        self.assertTrue(res["applied"])
        self.assertEqual(self.store.nodes.get(self.nid).deleted_at, self.now)
        events = list_audit_events(self.store, self.nid)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_kind"], "tombstone")
        self.assertEqual(events[0]["operator"], "zj")
        self.assertEqual(events[0]["title"], "victim")
        self.assertNotIn("content", events[0], "审计事件不得记 content")

    def test_mark_idempotent_no_duplicate_audit(self):
        mark_tombstone(self.store, self.nid, operator="zj", at=self.now)
        res = mark_tombstone(self.store, self.nid, operator="zj", at=self.now)
        self.assertFalse(res["applied"], "重复 mark 应 no-op")
        self.assertEqual(len(list_audit_events(self.store, self.nid)), 1)

    def test_restore_clears_tombstone_and_audits(self):
        mark_tombstone(self.store, self.nid, operator="zj", at=self.now)
        res = restore_node(self.store, self.nid, operator="zj", at=self.now)
        self.assertTrue(res["applied"])
        self.assertIsNone(self.store.nodes.get(self.nid).deleted_at)
        kinds = [e["event_kind"] for e in list_audit_events(self.store, self.nid)]
        self.assertEqual(kinds, ["tombstone", "restore"])

    def test_operator_is_required(self):
        with self.assertRaises(ValueError):
            mark_tombstone(self.store, self.nid, operator="", at=self.now)

    def test_cli_mark_and_restore(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dispatch(parse_args([
                "tombstone", "mark", "--id", str(self.nid),
                "--operator", "zj", "--storage", "memory", "--json"]), store=self.store)
        self.assertEqual(rc, 0)
        self.assertEqual(self.store.nodes.get(self.nid).deleted_at is not None, True)
        with redirect_stdout(buf):
            rc = dispatch(parse_args([
                "tombstone", "restore", "--id", str(self.nid),
                "--operator", "zj", "--storage", "memory", "--json"]), store=self.store)
        self.assertEqual(rc, 0)
        self.assertIsNone(self.store.nodes.get(self.nid).deleted_at)

    def test_cli_requires_operator_for_mark(self):
        rc = dispatch(parse_args([
            "tombstone", "mark", "--id", str(self.nid),
            "--storage", "memory", "--json"]), store=self.store)
        self.assertNotEqual(rc, 0, "mark 缺 --operator 应为非零（人环门禁）")


if __name__ == "__main__":
    unittest.main()

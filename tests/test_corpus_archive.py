"""D2 导入语料隔离的 TDD 验收。

核心缺陷：list_due_for_review 双实现原本不过滤 archived_at，
只调 nodes.archive() 并不能把语料移出复审队列。
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zkc import cli
from zkc.corpus import CORPUS_ACTION, archive_corpus, select_corpus_nodes
from zkc.repository import get_storage
from zkc.repository.models import Node

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DAY = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _corpus_node(title="导入语料"):
    return Node(
        title=title, track="dynamic", decay_score=1.0,
        review_interval=timedelta(days=1), last_reviewed_at=CORPUS_DAY,
        created_at=CORPUS_DAY,
    )


def _due_node(store, title, *, archive=False):
    node = store.nodes.save(_corpus_node(title))
    if archive:
        store.nodes.archive(node.id, datetime.now(timezone.utc))
    return node


class ArchivedDueFilterTest(unittest.TestCase):
    def test_memory_due_excludes_archived(self):
        store = get_storage("memory")
        open_node = _due_node(store, "未归档")
        _due_node(store, "已归档", archive=True)
        due = store.nodes.list_due_for_review(datetime.now(timezone.utc))
        self.assertEqual([n.id for n in due], [open_node.id])

    def test_pg_due_sql_filters_archived(self):
        src = (ROOT / "src" / "zkc" / "repository" / "pg.py").read_text()
        body = src[src.index("def list_due_for_review"):][:700]
        self.assertIn("archived_at IS NULL", body)


class CorpusArchiveTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.now = datetime.now(timezone.utc)

    def test_select_only_matches_imported_corpus_features(self):
        hit = self.store.nodes.save(_corpus_node("AI-Coding 子文档"))
        self.store.nodes.save(Node(title="真实条目", track="dynamic", decay_score=0.9,
                                   review_interval=timedelta(days=3),
                                   last_reviewed_at=self.now - timedelta(days=5)))
        self.store.nodes.save(Node(title="静态事实", track="static", decay_score=1.0,
                                   review_interval=timedelta(days=1),
                                   last_reviewed_at=CORPUS_DAY))
        selected = select_corpus_nodes(self.store)
        self.assertEqual([n.id for n in selected], [hit.id])

    def test_dry_run_does_not_mutate(self):
        node = self.store.nodes.save(_corpus_node())
        res = archive_corpus(self.store, dry_run=True)
        self.assertEqual(res["matched"], 1)
        self.assertEqual(res["archived"], 0)
        self.assertTrue(res["dry_run"])
        self.assertIsNone(self.store.nodes.get(node.id).archived_at)
        self.assertEqual(len(self.store.nodes.list_due_for_review(self.now)), 1)

    def test_archive_moves_corpus_out_of_due(self):
        self.store.nodes.save(_corpus_node())
        before = len(self.store.nodes.list_due_for_review(self.now))
        res = archive_corpus(self.store)
        self.assertEqual(res["matched"], 1)
        self.assertEqual(res["archived"], 1)
        self.assertEqual(len(self.store.nodes.list_due_for_review(self.now)), before - 1)

    def test_archive_never_touches_labeling_anchors(self):
        self.store.nodes.save(_corpus_node())
        item = self.store.review_queue.enqueue(
            self.store.nodes.list_by_track("dynamic")[0].id, "classify", None)
        obs_before = len(self.store.attention.list_recent(30))
        res = archive_corpus(self.store)
        self.assertEqual(res["labeled_touched"], 0)
        self.assertEqual(res["attention_observation_touched"], 0)
        self.assertEqual(res["review_queue_resolved"], 0)
        self.assertEqual(len(self.store.attention.list_recent(30)), obs_before)
        self.assertIn(item.id, [i.id for i in self.store.review_queue.list_open()])

    def test_action_name_is_explicit_bulk_cleanup(self):
        self.assertEqual(CORPUS_ACTION, "bulk corpus cleanup")
        self.assertIn(CORPUS_ACTION, archive_corpus(self.store, dry_run=True)["action"])


class CliArchiveTest(unittest.TestCase):
    def test_dispatch_archive_corpus_json_dry_run(self):
        store = get_storage("memory")
        store.nodes.save(_corpus_node())
        args = cli.parse_args(["archive", "--storage", "memory", "--corpus",
                               "--dry-run", "--json"])
        rc = cli.dispatch(args, store=store)
        self.assertEqual(rc, 0)

    def test_archive_requires_corpus_flag(self):
        args = cli.parse_args(["archive", "--storage", "memory", "--json"])
        self.assertFalse(args.corpus)


if __name__ == "__main__":
    unittest.main()

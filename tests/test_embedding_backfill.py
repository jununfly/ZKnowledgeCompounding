"""embedding 回填算子单测（内存后端 + 可注入 encoder，不依赖 PG / Ollama）。

回归重点：旧脚本 `n.embedding_4096 is None and n.content` 会永久跳过空正文节点；
新算子必须全轨、幂等、空正文用标题兜底、按 text 去重、编码失败零写入。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from zkc.embedding_backfill import backfill_embeddings, embedding_text
from zkc.repository import get_storage
from zkc.repository.models import Node

COLUMNS = ("embedding", "embedding_4096")


def fake_encoders(dims=(768, 4096)):
    """返回 (encoders, calls)：calls[(column, text)] 记调用次数。"""
    calls: dict[tuple[str, str], int] = {}

    def make(column, dim):
        def encode(texts):
            for t in texts:
                key = (column, t)
                calls[key] = calls.get(key, 0) + 1
            return [[0.1] * dim for _ in texts]
        return encode

    return {"embedding": make("embedding", dims[0]),
            "embedding_4096": make("embedding_4096", dims[1])}, calls


def add_node(store, title, content=None, track="dynamic", **kw):
    return store.nodes.save(Node(title=title, content=content, track=track, **kw))


class EmbeddingBackfillTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")

    def test_embedding_text_falls_back_to_title(self):
        """空正文只用标题编码，不产生悬空换行。"""
        self.assertEqual(embedding_text(Node(title="v1", content=None)), "v1")
        self.assertEqual(embedding_text(Node(title="t", content="")), "t")
        self.assertEqual(embedding_text(Node(title="t", content="body")), "t\nbody")

    def test_empty_content_node_is_backfilled(self):
        """回归：content 为空的节点不再被永久跳过。"""
        n = add_node(self.store, "v1", None, track="dynamic")
        enc, calls = fake_encoders()
        r = backfill_embeddings(self.store, encoders=enc)
        self.assertEqual(r["gap_nodes"], 1)
        self.assertEqual(r["columns_written"], 2)
        saved = self.store.nodes.get(n.id)
        self.assertEqual(len(saved.embedding), 768)
        self.assertEqual(len(saved.embedding_4096), 4096)
        self.assertEqual(calls[("embedding", "v1")], 1)

    def test_all_tracks_are_covered(self):
        """全轨：static / dynamic / unrouted 都补齐。"""
        add_node(self.store, "s", "body", track="static")
        add_node(self.store, "d", "body", track="dynamic")
        add_node(self.store, "u", "body", track="unrouted")
        r = backfill_embeddings(self.store, encoders=fake_encoders()[0])
        self.assertEqual(r["scanned"], 3)
        self.assertEqual(r["gap_nodes"], 3)
        self.assertEqual(r["columns_written"], 6)
        for track in ("static", "dynamic", "unrouted"):
            for n in self.store.nodes.list_by_track(track):
                self.assertIsNotNone(n.embedding)
                self.assertIsNotNone(n.embedding_4096)

    def test_idempotent_second_run_writes_nothing(self):
        """幂等：第二遍零写入、零编码。"""
        add_node(self.store, "a", "body")
        enc, calls = fake_encoders()
        first = backfill_embeddings(self.store, encoders=enc)
        second = backfill_embeddings(self.store, encoders=enc)
        self.assertEqual(first["columns_written"], 2)
        self.assertEqual(second["gap_nodes"], 0)
        self.assertEqual(second["columns_written"], 0)
        self.assertEqual(sum(calls.values()), 2)  # 只有第一遍编了 2 次

    def test_only_missing_columns_are_written(self):
        """已有 768 的节点只补 4096，不重算已有列。"""
        n = add_node(self.store, "partial", "body", embedding=[0.2] * 768)
        enc, calls = fake_encoders()
        r = backfill_embeddings(self.store, encoders=enc)
        self.assertEqual(r["columns_written"], 1)
        saved = self.store.nodes.get(n.id)
        self.assertEqual(saved.embedding[0], 0.2)
        self.assertEqual(len(saved.embedding_4096), 4096)
        self.assertNotIn(("embedding", "partial\nbody"), calls)

    def test_duplicate_text_encoded_once(self):
        """同 title+content 的重复节点：每个列只编一次，向量一致。"""
        nodes = [add_node(self.store, "AINMM", "same body") for _ in range(3)]
        enc, calls = fake_encoders()
        r = backfill_embeddings(self.store, encoders=enc)
        self.assertEqual(r["unique_texts"], 1)
        self.assertEqual(r["columns_written"], 6)
        self.assertEqual(calls[("embedding", "AINMM\nsame body")], 1)
        vecs = {tuple(self.store.nodes.get(n.id).embedding) for n in nodes}
        self.assertEqual(len(vecs), 1)

    def test_dry_run_does_not_write(self):
        n = add_node(self.store, "dry", "body")
        enc, calls = fake_encoders()
        r = backfill_embeddings(self.store, encoders=enc, dry_run=True)
        self.assertTrue(r["dry_run"])
        self.assertEqual(r["gap_columns"], 2)
        self.assertEqual(r["columns_written"], 0)
        self.assertEqual(calls, {})
        self.assertIsNone(self.store.nodes.get(n.id).embedding)

    def test_encode_failure_writes_nothing(self):
        """先算后写：任一编码失败 → 零写入，不留半成品。"""
        n1 = add_node(self.store, "ok", "body")
        n2 = add_node(self.store, "bad", "body")
        enc, _ = fake_encoders()

        def failing(texts):
            if texts and texts[0].startswith("bad"):
                raise RuntimeError("ollama down")
            return [[0.1] * 768 for _ in texts]

        enc = {"embedding": failing,
               "embedding_4096": lambda texts: [[0.1] * 4096 for _ in texts]}
        with self.assertRaises(RuntimeError):
            backfill_embeddings(self.store, encoders=enc)
        for nid in (n1.id, n2.id):
            saved = self.store.nodes.get(nid)
            self.assertIsNone(saved.embedding)
            self.assertIsNone(saved.embedding_4096)

    def test_archived_nodes_are_skipped(self):
        """已归档节点移出召回，不该再为它花算力补向量。"""
        n = add_node(self.store, "archived", "body")
        self.store.nodes.archive(n.id, datetime.now(timezone.utc))
        r = backfill_embeddings(self.store, encoders=fake_encoders()[0])
        self.assertEqual(r["scanned"], 1)
        self.assertEqual(r["archived_skipped"], 1)
        self.assertEqual(r["gap_nodes"], 0)
        self.assertEqual(r["columns_written"], 0)
        self.assertIsNone(self.store.nodes.get(n.id).embedding)

    def test_tracks_and_columns_can_be_narrowed(self):
        """脚本侧仍可只回填 dynamic+4096（R18 原语义）。"""
        add_node(self.store, "s", "body", track="static")
        add_node(self.store, "d", "body", track="dynamic")
        r = backfill_embeddings(
            self.store, encoders=fake_encoders()[0],
            tracks=("dynamic",), columns=("embedding_4096",),
        )
        self.assertEqual(r["gap_nodes"], 1)
        self.assertEqual(r["columns_written"], 1)
        self.assertIsNone(self.store.nodes.list_by_track("static")[0].embedding)


if __name__ == "__main__":
    unittest.main()

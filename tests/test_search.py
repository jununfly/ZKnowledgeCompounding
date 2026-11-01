"""ZKC · 检索编排层（P5.1 切片C）测试。

encoder 全程 fake：验证双路合成、去重、降级语义与召回数量口径。
"""
from __future__ import annotations

import unittest
from datetime import datetime

from zkc import search as S
from zkc.encoder import EncoderError
from zkc.repository.memory import MemoryStorage
from zkc.repository.models import Node

DIM = 768


def _vec(*vals):
    return list(vals) + [0.0] * (DIM - len(vals))


def _store():
    st = MemoryStorage()
    base = datetime(2026, 11, 1)
    st.nodes.save(Node(track="dynamic", title="Rust 重写计划",
                       decay_score=0.2, embedding=_vec(1.0, 0.0), created_at=base))
    st.nodes.save(Node(track="dynamic", title="brain 引擎笔记",
                       decay_score=0.7, embedding=_vec(0.95, 0.05), created_at=base))
    st.nodes.save(Node(track="dynamic", title="无关条目",
                       decay_score=0.1, embedding=_vec(0.0, 1.0), created_at=base))
    st.nodes.save(Node(track="static", title="rust 静态事实",
                       decay_score=0.0, created_at=base))
    return st


def _enc_close_to(v):
    """fake encoder：query 编码为与 v 同向的 768 维向量。"""
    def _e(texts):
        return [_vec(*v) for _ in texts]
    _e.model_name = "fake"
    return _e


class SearchOrchestrationTest(unittest.TestCase):
    def test_structured_only_without_encoder(self):
        r = S.search(_store(), q="rust", track="dynamic")
        self.assertEqual(r["structured_count"], 1)
        self.assertEqual(r["embedding_count"], 0)
        self.assertFalse(r["degraded"])
        self.assertEqual(r["hits"][0].source, S.STRUCTURED)
        self.assertIsNone(r["hits"][0].sim)

    def test_dual_path_merges_and_dedups(self):
        # 结构化按 q="rust" 命中 2 条（跨轨）；embedding 近 [1,0] 召回 3 条，
        # 其中 "Rust 重写计划" 已被结构化命中 → 去重，候选追加 2 条
        r = S.search(_store(), q="rust", encoder=_enc_close_to((1.0, 0.0)), k=5)
        self.assertEqual(r["structured_count"], 2)
        self.assertEqual(r["embedding_count"], 2)
        self.assertEqual(r["hits"][0].source, S.STRUCTURED)
        emb_titles = {h.node.title for h in r["hits"] if h.source == S.EMBEDDING}
        self.assertEqual(emb_titles, {"brain 引擎笔记", "无关条目"})
        ids = [h.node.id for h in r["hits"]]
        self.assertEqual(len(ids), len(set(ids)), "双路结果必须去重")

    def test_encoder_failure_degrades_not_raises(self):
        def _boom(texts):
            raise EncoderError("conn refused")

        r = S.search(_store(), q="rust", encoder=_boom)
        self.assertEqual(r["structured_count"], 2)
        self.assertEqual(r["embedding_count"], 0)
        self.assertTrue(r["degraded"])
        self.assertIn("conn refused", r["degrade_reason"])

    def test_no_q_skips_embedding_path(self):
        # 有 encoder 但无 q：不调 encoder（不浪费编码延迟）
        called = []

        def _spy(texts):
            called.append(texts)
            return [_vec(1.0) for _ in texts]

        r = S.search(_store(), encoder=_spy)
        self.assertEqual(called, [])
        self.assertEqual(r["embedding_count"], 0)

    def test_embedding_only_when_structured_empty(self):
        # q 只被 embedding 召回（结构化零命中，q 不在标题里）
        r = S.search(_store(), q="完全不同的说法", encoder=_enc_close_to((1.0, 0.0)), k=2)
        self.assertEqual(r["structured_count"], 0)
        self.assertEqual(r["embedding_count"], 2)
        self.assertEqual(r["hits"][0].source, S.EMBEDDING)

    def test_respects_track_and_decay_filters(self):
        r = S.search(_store(), track="dynamic", decay_min=0.5, order="decay_desc")
        self.assertEqual([h.node.decay_score for h in r["hits"]], [0.7])


if __name__ == "__main__":
    unittest.main()

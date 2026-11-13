"""ZKC · P5.1 检索/复利产物浏览 UI 测试（切片D）。

服务函数用 MemoryStorage 直测；HTTP 层用 TestClient 验证 /browse 页与两个 API，
encoder 注入 fake（不依赖真实 Ollama）。
"""
from __future__ import annotations

import unittest
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from zkc.repository.memory import MemoryStorage
from zkc.repository.models import Claim, ModelingArtifact, Node
from zkc.web.browse import artifacts_payload, register_browse_routes, search_payload

DIM = 768
DIM4096 = 4096  # R18 加列（双列共存）：/browse 候选召回默认走 embedding_4096


def _vec(*vals):
    return list(vals) + [0.0] * (DIM - len(vals))


def _vec4096(*vals):
    return list(vals) + [0.0] * (DIM4096 - len(vals))


def _store():
    st = MemoryStorage()
    base = datetime(2026, 11, 1)
    n1 = st.nodes.save(Node(track="dynamic", title="Rust 重写计划",
                            content="brain engine trait 迁移",
                            decay_score=0.2, embedding=_vec(1.0, 0.0),
                            embedding_4096=_vec4096(1.0, 0.0),
                            created_at=base))
    n2 = st.nodes.save(Node(track="dynamic", title="brain 引擎笔记",
                            decay_score=0.7, embedding=_vec(0.95, 0.05),
                            embedding_4096=_vec4096(0.95, 0.05),
                            created_at=base))
    c = st.claims.save(Claim(statement="Rust trait 优先迁移纯函数",
                             evidence_refs=[n1.id],
                             faithfulness_status="pending_human",
                             created_at=base))
    a = st.artifacts.save(ModelingArtifact(title="迁移方法论 v1",
                                           kind="methodology",
                                           evidence_refs=[n1.id, n2.id],
                                           created_at=base))
    return st, n1, n2, c, a


def _enc(texts):
    out = []
    for _ in texts:
        out.append(_vec4096(0.95, 0.05))
    return out


class ServicePayloadTest(unittest.TestCase):
    def test_search_payload_shape(self):
        st, *_ = _store()
        p = search_payload(st, q="rust", encoder=None)
        self.assertEqual(p["structured_count"], 1)
        h = p["hits"][0]
        self.assertEqual(h["title"], "Rust 重写计划")
        self.assertEqual(h["track"], "dynamic")
        self.assertIn("source", h) and self.assertIn("sim", h)
        self.assertIn("brain", h["snippet"])

    def test_search_payload_embedding_candidate(self):
        st, _n1, n2, *_ = _store()
        p = search_payload(st, q="rust", encoder=_enc, k=5)
        self.assertEqual(p["embedding_count"], 1)
        cand = p["hits"][-1]
        self.assertEqual(cand["id"], str(n2.id))
        self.assertEqual(cand["source"], "embedding")
        self.assertAlmostEqual(cand["sim"], 1.0, delta=1e-6)

    def test_search_payload_768_column_opt_in(self):
        # 双列共存：column="embedding" 可切回 nomic 768 列，
        # 同一 fixture 下 768 列召回结果独立成立（n1 被结构化去重，n2 追加）
        st, _n1, n2, *_ = _store()
        p = search_payload(st, q="rust", encoder=_enc, k=5, column="embedding")
        self.assertEqual(p["embedding_count"], 1)
        self.assertEqual(p["hits"][-1]["id"], str(n2.id))

    def test_search_payload_4096_column_independent(self):
        # 双列独立：4096 列与 768 列各走各的，不静默回退
        st, _n1, n2, *_ = _store()
        st.nodes.set_embedding_column(n2.id, "embedding_4096", _vec4096(0.0, 1.0))
        p = search_payload(st, q="rust", encoder=_enc, k=5)
        self.assertEqual(p["embedding_count"], 1)  # n2 已与查询正交，仅 n1 召回

    def test_artifacts_payload(self):
        st, n1, n2, c, a = _store()
        p = artifacts_payload(st)
        self.assertEqual(len(p["claims"]), 1)
        cj = p["claims"][0]
        self.assertEqual(cj["statement"], c.statement)
        self.assertEqual(cj["citation_count"], 0)
        self.assertEqual(cj["evidence"], [{"id": str(n1.id), "title": "Rust 重写计划"}])
        self.assertEqual(cj["faithfulness_status"], "pending_human")
        aj = p["artifacts"][0]
        self.assertEqual([e["title"] for e in aj["evidence"]],
                         ["Rust 重写计划", "brain 引擎笔记"])
        self.assertEqual(aj["kind"], "methodology")

    def test_artifacts_payload_deleted_evidence(self):
        st, n1, _n2, _c, _a = _store()
        st.nodes._rows.pop(n1.id)  # 模拟来源被删
        p = artifacts_payload(st)
        self.assertEqual(p["claims"][0]["evidence"][0]["title"], "(已删除)")


class BrowseHttpTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        self.store, *_ = _store()
        register_browse_routes(app, self.store, encoder=_enc)
        self.client = TestClient(app)

    def test_page_served(self):
        r = self.client.get("/browse")
        self.assertEqual(r.status_code, 200)
        self.assertIn("复利产物", r.text)
        self.assertIn("/browse/api", r.text)

    def test_search_api(self):
        r = self.client.get("/browse/api", params={"q": "rust"})
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(j["structured_count"], 1)

    def test_search_api_with_filters(self):
        r = self.client.get("/browse/api",
                            params={"track": "dynamic", "decay_min": 0.5})
        j = r.json()
        self.assertEqual([h["title"] for h in j["hits"]], ["brain 引擎笔记"])

    def test_artifacts_api(self):
        r = self.client.get("/browse/artifacts/api")
        self.assertEqual(r.status_code, 200)
        j = r.json()
        self.assertEqual(len(j["claims"]), 1)
        self.assertEqual(len(j["artifacts"]), 1)


if __name__ == "__main__":
    unittest.main()

"""ZKC · 1-5-5-1 忠实度闸门后续切片测试：F_cap 日队列 + 审查卡片 UI + adjudicate 包装。

三层验证（与 test_web_review 同构）：
- 纯函数层（zkc.faithfulness.daily_faithfulness_queue）：R11 独立预算语义——
  强制项（forced_* / human_only）永无上限；F_CAP_RATIO 只封顶抽检+审计侧。
- web 纯函数层（zkc.web.review.faithfulness_queue_view / adjudicate_claim）：
  审查动作走独立预算，绝不写 attention_observation（复审容量口径不被污染）。
- HTTP 层（TestClient）：GET /review/api/faithfulness + POST .../adjudicate 装配。
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from zkc import tuning
from zkc.faithfulness import daily_faithfulness_queue, gate_new_claims
from zkc.repository import get_storage
from zkc.repository.models import Claim, Node

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _seed_sources(store, n: int = 2) -> list:
    ids = []
    for i in range(n):
        node = store.nodes.save(Node(title=f"S{i}", content=f"来源内容 {i}：关键事实甲与关键事实乙。",
                                    track="dynamic"))
        ids.append(node.id)
    return ids


def _seed_gated(store, n: int = 3) -> list[Claim]:
    """走真实 gate（judge_fn=None → human_only 全人工）造 n 条 pending_human claims。"""
    src = _seed_sources(store)
    claims = []
    for i in range(n):
        claims.append(Claim(statement=f"claim {i}：由来源蒸馏的断言。", evidence_refs=src))
    gate_new_claims(store, claims, lambda c: [
        {"id": str(u), "title": "", "content": store.nodes.get(u).content}
        for u in c.evidence_refs], judge_fn=None)
    return [store.claims.get(c.id) for c in claims]


def _seed_manual(store, route: str, n: int = 1) -> list:
    """直接以指定 route/status 落库 pending_human claims（构造 judge 模式的队列形态）。"""
    src = _seed_sources(store, 1)
    out = []
    for i in range(n):
        c = Claim(statement=f"m-{route}-{i}", evidence_refs=src,
                  faithfulness_status="pending_human", faithfulness_route=route,
                  judge_raw={"flags": [], "mode": "judge"})
        store.claims.save(c)
        out.append(c.id)
    return out


class DailyQueuePureTest(unittest.TestCase):
    """F_cap 联动核心：R11 语义——强制项全保留，封顶只作用于抽检+审计侧。"""

    def setUp(self):
        self.store = get_storage("memory")

    def test_human_only_never_capped(self):
        # judge 不可用模式：全部 human_only = 强制侧，cap 再小也全展示
        _seed_gated(self.store, 5)
        q = daily_faithfulness_queue(self.store)
        self.assertEqual(q["forced_total"], 5)
        self.assertEqual(q["capped_total"], 0)
        self.assertEqual(len(q["items"]), 5)
        self.assertEqual(q["capped_withheld"], 0)

    def test_capped_side_limited_by_f_cap_ratio(self):
        # judge 模式形态：5 条抽检/审计侧 pending → cap = int(0.2*5) = 1，其余留痕不展示
        _seed_manual(self.store, "periodic_audit", 3)
        _seed_manual(self.store, "sampled_unsupported", 2)
        q = daily_faithfulness_queue(self.store)
        self.assertEqual(q["forced_total"], 0)
        self.assertEqual(q["capped_total"], 5)
        self.assertEqual(q["cap"], 1)
        self.assertEqual(q["capped_shown"], 1)
        self.assertEqual(q["capped_withheld"], 4)
        self.assertEqual(len(q["items"]), 1)

    def test_forced_never_withheld_even_with_cap_zero(self):
        # 2 条强制 + 4 条封顶侧 → cap = int(0.2*6)=1；强制 2 条全在，封顶侧只出 1 条
        _seed_gated(self.store, 2)                          # human_only（强制侧）
        _seed_manual(self.store, "periodic_audit", 2)
        _seed_manual(self.store, "sampled_unsupported", 2)
        q = daily_faithfulness_queue(self.store)
        self.assertEqual(q["forced_total"], 2)
        self.assertEqual(q["cap"], 1)
        self.assertEqual(q["capped_shown"], 1)
        self.assertEqual(q["capped_withheld"], 3)
        routes = [it["faithfulness_route"] for it in q["items"]]
        # 强制项在前且全部在场
        self.assertEqual(routes[:2], ["human_only", "human_only"])
        self.assertEqual(len(routes), 3)

    def test_threshold_carries_source_label(self):
        # 1-2-7 铁律：UI 展示阈值必须带来源标签
        _seed_gated(self.store, 1)
        q = daily_faithfulness_queue(self.store)
        self.assertEqual(q["f_cap_ratio"], float(tuning.get("F_CAP_RATIO")))
        self.assertEqual(q["f_cap_source"], tuning.param("F_CAP_RATIO").source)

    def test_empty_queue_graceful(self):
        q = daily_faithfulness_queue(self.store)
        self.assertEqual(q["total_pending"], 0)
        self.assertEqual(q["items"], [])


class AdjudicateWrapperTest(unittest.TestCase):
    """web 纯函数层：adjudicate_claim 包装 + R11 独立预算（不写复审埋点）。"""

    def setUp(self):
        self.store = get_storage("memory")
        self.claims = _seed_gated(self.store, 2)

    def test_view_shape_and_calibration_zero(self):
        from zkc.web.review import faithfulness_queue_view
        v = faithfulness_queue_view(self.store, NOW)
        self.assertEqual(v["queue"]["total_pending"], 2)
        self.assertEqual(v["calibration"]["size"], 0)
        self.assertIsNone(v["calibration"]["judge_correct_rate"])

    def test_adjudicate_claim_updates_status(self):
        from zkc.web.review import adjudicate_claim
        res = adjudicate_claim(self.store, self.claims[0].id, "confirm", now=NOW)
        self.assertEqual(res["faithfulness_status"], "human_confirmed")
        self.assertEqual(res["queue"]["total_pending"], 1)

    def test_adjudicate_invalid_verdict_raises(self):
        from zkc.web.review import adjudicate_claim
        with self.assertRaises(ValueError):
            adjudicate_claim(self.store, self.claims[0].id, "maybe", now=NOW)

    def test_adjudicate_never_writes_attention_observation(self):
        # R11 独立预算：忠实度人审不占复审容量口径，attention_observation 不被污染
        from zkc.web.review import adjudicate_claim
        adjudicate_claim(self.store, self.claims[0].id, "confirm", now=NOW)
        self.assertIsNone(self.store.attention.get(NOW.date()))


class FaithfulnessHttpTest(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("httpx/TestClient 未安装")
        from zkc.web.app import create_app

        self.store = get_storage("memory")
        self.claims = _seed_gated(self.store, 2)
        self.app = create_app(
            store=self.store, decision_router=object(), lexical_router=object())
        self.client = TestClient(self.app)

    def test_faithfulness_api_shape(self):
        r = self.client.get("/review/api/faithfulness")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["queue"]["total_pending"], 2)
        self.assertIn("calibration", body)
        self.assertIn("f_cap_source", body["queue"])

    def test_adjudicate_api_confirms(self):
        r = self.client.post(
            "/review/api/faithfulness/adjudicate",
            data={"claim_id": str(self.claims[0].id), "verdict": "confirm"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["faithfulness_status"], "human_confirmed")
        # 队列随之收缩
        self.assertEqual(
            self.client.get("/review/api/faithfulness").json()["queue"]["total_pending"], 1)

    def test_review_page_carries_faithfulness_panel(self):
        r = self.client.get("/review")
        self.assertEqual(r.status_code, 200)
        self.assertIn("忠实度人审", r.text)
        self.assertIn("/review/api/faithfulness", r.text)


if __name__ == "__main__":
    unittest.main()

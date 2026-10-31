"""ZKC · P4.4 标注率闸门 端到端验证（1-4-4）。

闸门逻辑在 1-4-1 落地（zkc.scheduling.labeling_rate_from + adapt_interval 的 gate 分支），
1-4-2 的 UI 负责持续喂入标注数据。本文件验证「闸门在真实多日观测下按口径开关」——
这是 1-4-4 作为闭环验收的核心，而非只测纯函数。

口径（架构 §6.5 / 工作记忆）：
- 滚动 7 天 labeled_completed / completed ≥ 70% → 闸门开放，L3 可改写 interval；
- 窗口内完成复审 < 10 次 → 不判定（warm-up 放行，避免冻死 L3）；
- 率 < 70% → 闸门关闭，未标注（decay-only）复审禁止写 interval_adjustment；
- 人工显式 verdict（outcome 非空）不受闸门限制。
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from zkc import scheduling as S
from zkc.decay import refresh_decay
from zkc.repository import get_storage
from zkc.repository.models import AttentionObservation, Node

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=10)


def _seed_due(store):
    node = store.nodes.save(
        Node(title="gate-probe", content="随手记灵感", track="dynamic"))
    S.assign_baselines(store)
    store.nodes.mark_reviewed(node.id, PAST)
    refresh_decay(store.nodes, NOW)
    return node.id


def _obs(store, days: int, completed: int, labeled: int, base: date | None = None):
    """写 days 天观测（base 起往回推），每天 completed / labeled 给定值。"""
    base = base or date.today()
    for k in range(days):
        store.attention.record_observation(AttentionObservation(
            day=base - timedelta(days=k),
            pushed=0, completed=completed, queue_remaining=0,
            labeled_completed=labeled))


class LabelingGateTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")
        self.nid = _seed_due(self.store)

    def test_gate_open_with_sufficient_label_rate(self):
        # 7 天 × (completed=2, labeled=2) → 率 100% → 闸门开放 → L3 改写
        _obs(self.store, days=7, completed=2, labeled=2)
        r = S.adapt_interval(self.store, self.nid, decay_at_review=0.95, outcome=None)
        self.assertTrue(r["applied"])
        self.assertNotIn("label gate closed", r["reason"])

    def test_gate_closed_when_label_rate_low(self):
        # 7 天 × (completed=2, labeled=0) → 率 0% < 70% → 闸门关闭 → 未标注复审被拒
        _obs(self.store, days=7, completed=2, labeled=0)
        r = S.adapt_interval(self.store, self.nid, decay_at_review=0.95, outcome=None)
        self.assertFalse(r["applied"])
        self.assertIn("label gate closed", r["reason"])

    def test_gate_open_with_insufficient_samples(self):
        # 3 天 × completed=2 = 6 次 < 10 样本 → 不判定、warm-up 放行（闸门开放）
        _obs(self.store, days=3, completed=2, labeled=0)
        gate = S.labeling_rate_from(self.store.attention.list_recent(30))
        self.assertEqual(gate["gate"], "open")
        self.assertIsNone(gate["rate"])
        r = S.adapt_interval(self.store, self.nid, decay_at_review=0.95, outcome=None)
        self.assertTrue(r["applied"])     # 样本不足时放行，不冻死 L3

    def test_explicit_outcome_bypasses_gate(self):
        # 即便标注率 0%（闸门关闭），人工显式 verdict 仍改写
        _obs(self.store, days=7, completed=2, labeled=0)
        before = self.store.nodes.get(self.nid).review_interval
        r = S.adapt_interval(self.store, self.nid, decay_at_review=0.5, outcome="too_late")
        self.assertTrue(r["applied"])
        after = self.store.nodes.get(self.nid).review_interval
        self.assertNotEqual(before, after)

    def test_unlabeled_review_never_writes_interval(self):
        # 走 UI 的 browse 路径：仅复位时钟 + 计数，绝不写 interval_adjustment
        from zkc.web.review import decide_review
        before = self.store.nodes.get(self.nid).review_interval
        decide_review(self.store, self.nid, "browse", NOW)
        after = self.store.nodes.get(self.nid).review_interval
        self.assertEqual(before, after)                       # interval 未变
        self.assertEqual(self.store.nodes.get(self.nid).decay_score, 0.0)  # 时钟复位
        self.assertEqual(self.store.attention.get(NOW.date()).labeled_completed, 0)  # 未标注


if __name__ == "__main__":
    unittest.main()

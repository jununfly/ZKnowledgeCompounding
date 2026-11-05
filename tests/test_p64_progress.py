"""ZKC · PRD §9 P6.4 观察期达成读数（只读）单测。

与 E1(1-1) 判据独立：① 累计 labeled_completed ≥20（不要求日历连续）；
② 滚动 7 天样本达标（completed ≥10）且 rate ≥0.7。

回归重点：`labeling_rate_from` 在「样本不足 warm-up 放行」时同样返回
gate="open"（合格时也是 open，closed 反而表示 <70% 停机），所以 gate
字符串不能当判据——必须看 rate 是否非 None 且达到阈值。
"""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta

from zkc.calibration import build_p64_report, format_p64_human
from zkc.cli import dispatch, parse_args
from zkc.repository import get_storage
from zkc.repository.models import AttentionObservation
from zkc.task_queue import LABEL_JUDGMENT_THRESHOLD

BASE = date(2026, 11, 5)


def _obs(store, offset: int, completed: int, labeled: int) -> None:
    store.attention.record_observation(AttentionObservation(
        day=BASE - timedelta(days=offset),
        pushed=0, completed=completed, queue_remaining=0,
        labeled_completed=labeled))


class P64ProgressTest(unittest.TestCase):
    def setUp(self):
        self.store = get_storage("memory")

    def _report(self):
        return build_p64_report("memory", storage=self.store)

    def test_empty_observations_both_criteria_unmet(self):
        r = self._report()
        c1 = r["criteria"]["c1_cumulative_labeled"]
        c2 = r["criteria"]["c2_rolling_labeling_rate"]
        self.assertEqual(c1["total_labeled"], 0)
        self.assertEqual(c1["threshold"], LABEL_JUDGMENT_THRESHOLD)
        self.assertEqual(c1["remaining"], LABEL_JUDGMENT_THRESHOLD)
        self.assertFalse(c1["met"])
        self.assertIsNone(c2["rate"])
        self.assertFalse(c2["met"])
        self.assertFalse(r["all_exit_criteria_met"])

    def test_all_criteria_met(self):
        for k in range(7):
            _obs(self.store, k, 3, 3)  # 累计 21，7d rate=1.0
        r = self._report()
        self.assertEqual(r["criteria"]["c1_cumulative_labeled"]["total_labeled"], 21)
        self.assertTrue(r["criteria"]["c1_cumulative_labeled"]["met"])
        self.assertEqual(r["criteria"]["c2_rolling_labeling_rate"]["rate"], 1.0)
        self.assertTrue(r["criteria"]["c2_rolling_labeling_rate"]["met"])
        self.assertTrue(r["all_exit_criteria_met"])

    def test_gate_open_from_warmup_is_not_a_met_criterion(self):
        """核心回归：样本不足时 gate="open" 是 warm-up 放行，不是达标。"""
        _obs(self.store, 30, 20, 20)      # 旧数据凑够累计 20
        for k in range(3):
            _obs(self.store, k, 2, 2)     # 7d 内仅 6 次 < 10
        r = self._report()
        c1 = r["criteria"]["c1_cumulative_labeled"]
        c2 = r["criteria"]["c2_rolling_labeling_rate"]
        self.assertTrue(c1["met"])
        self.assertIsNone(c2["rate"])
        self.assertEqual(c2["gate"], "open")
        self.assertFalse(c2["met"])
        self.assertFalse(r["all_exit_criteria_met"])

    def test_low_labeling_rate_unmet(self):
        _obs(self.store, 30, 20, 20)      # 累计达标
        for k in range(7):
            _obs(self.store, k, 3, 0)     # 7d rate=0.0
        r = self._report()
        c2 = r["criteria"]["c2_rolling_labeling_rate"]
        self.assertEqual(c2["rate"], 0.0)
        self.assertEqual(c2["gate"], "closed")
        self.assertFalse(c2["met"])
        self.assertFalse(r["all_exit_criteria_met"])

    def test_report_is_read_only(self):
        _obs(self.store, 0, 3, 3)
        before = len(self.store.attention.list_recent(366))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self._report()
            format_p64_human(self._report())
        after = len(self.store.attention.list_recent(366))
        self.assertEqual(before, after)
        self.assertIn("P6.4", buf.getvalue())

    def test_cli_p64_json_wiring(self):
        args = parse_args(["p64", "--json"])
        self.assertEqual(args.command, "p64")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dispatch(args, store=self.store)
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertIn("all_exit_criteria_met", payload)
        self.assertEqual(payload["criteria"]["c1_cumulative_labeled"]["threshold"],
                         LABEL_JUDGMENT_THRESHOLD)

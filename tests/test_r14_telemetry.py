"""R14 真实数据侧落库聚合 — telemetry 模块（TDD）。

只验证落库/读回/聚合的 plumbing 与 run_id 去重、容错、字段校验；判据本身由
tests/test_r14_judgment.py 覆盖（本模块直接委托 judge_r14，不重写）。真实 run
数据由 zj 经 dogfood 产生，本测试一律用临时文件、绝不伪造真实触发率。
"""
from __future__ import annotations

import unittest
from pathlib import Path

from zkc.r14_telemetry import aggregate, load_runs, record_run


def _run(fired: bool, main: float = 100.0, completion: float | None = None) -> dict:
    return {
        "completion_fired": fired,
        "main_latency_ms": main,
        # 仅触发补全的 run 有补全延迟；未触发的 run 该字段为 None（同 cross_source.combine）
        "completion_latency_ms": completion if fired else None,
    }


class TestR14Telemetry(unittest.TestCase):
    def test_record_then_load_roundtrip(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        rec = record_run(_run(True, 120.0, 200.0), path=p, run_id="r1")
        self.assertNotIn("skipped", rec)
        runs = load_runs(p)
        self.assertEqual(len(runs), 1)
        self.assertTrue(runs[0]["completion_fired"])
        self.assertEqual(runs[0]["main_latency_ms"], 120.0)
        self.assertEqual(runs[0]["completion_latency_ms"], 200.0)

    def test_run_id_dedup_skips_duplicate(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        record_run(_run(True, 100.0, 200.0), path=p, run_id="dup")
        skip = record_run(_run(True, 100.0, 200.0), path=p, run_id="dup")
        self.assertTrue(skip.get("skipped"))
        self.assertEqual(len(load_runs(p)), 1)

    def test_distinct_run_ids_accumulate(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        for i in range(3):
            record_run(_run(False, 100.0 + i), path=p, run_id=f"r{i}")
        self.assertEqual(len(load_runs(p)), 3)

    def test_record_missing_field_raises(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        bad = {"completion_fired": True, "main_latency_ms": 100.0}  # 缺 completion_latency_ms
        with self.assertRaises(ValueError):
            record_run(bad, path=p, run_id="x")

    def test_record_non_dict_raises(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        with self.assertRaises(ValueError):
            record_run("not-a-dict", path=p)  # type: ignore[arg-type]

    def test_load_runs_tolerates_garbage_and_incomplete(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        p.write_text(
            "this is not json\n"
            + json_line(_run(True, 100.0, 200.0), "ok")
            + "\n"
            + '{"run_id": "bad", "report": {"completion_fired": true}}\n'  # 缺字段
            + "\n",  # 空行
            encoding="utf-8",
        )
        runs = load_runs(p)
        self.assertEqual(len(runs), 1)
        self.assertTrue(runs[0]["completion_fired"])

    def test_load_runs_missing_file_returns_empty(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("nope.jsonl")
        self.assertEqual(load_runs(p), [])

    def test_aggregate_empty_is_insufficient_data(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        v = aggregate(p)
        self.assertFalse(v.should_close_completion)
        self.assertEqual(v.reason, "insufficient_data")
        self.assertEqual(v.total, 0)

    def test_aggregate_delegates_to_judge_r14(self) -> None:
        # 6/10 触发 + 补全延迟 200 > 主生成 100*1.5=150 → 关补全（与 judge_r14 口径一致）
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        for i in range(6):
            record_run(_run(True, 100.0, 200.0), path=p, run_id=f"f{i}")
        for i in range(4):
            record_run(_run(False, 100.0), path=p, run_id=f"n{i}")
        v = aggregate(p)
        self.assertEqual(v.total, 10)
        self.assertEqual(v.fired, 6)
        self.assertAlmostEqual(v.trigger_rate, 0.6)
        self.assertTrue(v.should_close_completion)
        self.assertEqual(v.reason, "trigger_rate_and_latency_exceed_budget")

    def test_aggregate_respects_min_runs(self) -> None:
        p = Path(self.enterContext(_tmp())).joinpath("t.jsonl")
        # 2 条真实 run 均触发补全且延迟超标：min_runs=2 时数据足以关补全
        record_run(_run(True, 100.0, 300.0), path=p, run_id="a")
        record_run(_run(True, 100.0, 300.0), path=p, run_id="b")
        v = aggregate(p, min_runs=2)
        self.assertTrue(v.should_close_completion)
        v2 = aggregate(p, min_runs=10)
        self.assertFalse(v2.should_close_completion)
        self.assertEqual(v2.reason, "insufficient_data")


def json_line(report: dict, run_id: str) -> str:
    import json
    return json.dumps({"run_id": run_id, "recorded_at": 0.0, "report": report},
                      ensure_ascii=False)


def _tmp():
    import tempfile
    import contextlib

    d = tempfile.mkdtemp(prefix="r14tel_")
    return contextlib.nullcontext(d)


if __name__ == "__main__":
    unittest.main()

"""Risk A1 TDD · 每日驱动 direct 模式（不依赖 HTTP 服务也能跑真值收口 + 仪表）。

背景：原 daily_e1_driver 的收口走 POST /review/api/observe/auto，要求 review 服务常驻，
否则收口失败（exit 2）——这是「驱动依赖服务常驻」风险的根因（A1）。真值收口本质是
record_daily_observation_auto(store) 这一纯函数，本应可直接对存储层跑，无需 HTTP 服务。

测试断言：direct 模式下，构造一份内存 store（含 1 个今日创建节点 + 1 个到期节点），
不启任何 HTTP 服务，调用 run(cfg, store) 后 observe_ok=True 且 observe 含真实 pushed/
queue_remaining，meter 报告含 criteria —— 证明服务宕机不再是阻塞点。

Seam：daily_e1_driver.load_config / run（公开）。不测 urllib 内部、只测端到端行为契约。
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 正常 import（注册进 sys.modules，dataclass 才能解析注解）；脚本目录加入路径即可。
sys.path.insert(0, str(ROOT / "scripts"))
import daily_e1_driver as driver  # noqa: E402

from zkc.repository import get_storage  # noqa: E402
from zkc.repository.models import Node  # noqa: E402


class DriverDirectTest(unittest.TestCase):
    def _cfg(self, tmp_log: Path) -> object:
        return driver.load_config(env={
            "ZKC_MODE": "direct",
            "ZKC_STORAGE": "memory",
            "ZKC_LOG": str(tmp_log),
        })

    def test_direct_mode_runs_without_http_server(self) -> None:
        """direct 模式：不启服务也能完成真值收口 + 仪表，且读数是真实真值。"""
        with tempfile.TemporaryDirectory() as td:
            store = get_storage("memory")
            now = datetime.now(timezone.utc)
            n = Node(
                track="dynamic", title="a", decay_score=0.9,
                review_interval=timedelta(days=1),
                last_reviewed_at=now - timedelta(days=10),
                created_at=now,
            )
            store.nodes.save(n)

            cfg = self._cfg(Path(td) / "e1.log")
            observe, meter, observe_ok, meter_ok = driver.run(cfg, store=store)

            self.assertTrue(observe_ok, "direct 收口应成功（无需 HTTP 服务）")
            self.assertEqual(observe["pushed"], 1, "pushed=今日创建节点数(真值)")
            self.assertEqual(observe["queue_remaining"], 1, "queue_remaining=当前到期数(真值)")
            self.assertTrue(meter_ok, "direct 仪表应成功")
            self.assertIn("criteria", meter)
            self.assertIn("c1_cumulative_active_days", meter["criteria"])
            self.assertIn("c3_budget_convergence", meter["criteria"])

    def test_direct_mode_observe_and_meter_share_store(self) -> None:
        """收口写入与仪表读取必须命中同一 store（内存后端若各自新建会读到空）。"""
        with tempfile.TemporaryDirectory() as td:
            store = get_storage("memory")
            now = datetime.now(timezone.utc)
            n = Node(
                track="dynamic", title="b", decay_score=0.9,
                review_interval=timedelta(days=1),
                last_reviewed_at=now - timedelta(days=10),
                created_at=now,
            )
            store.nodes.save(n)

            cfg = self._cfg(Path(td) / "e1.log")
            observe, meter, observe_ok, meter_ok = driver.run(cfg, store=store)
            # 若 observe 与 meter 命中不同 store，meter 看不到刚写的 queue_remaining
            # 此处只验证 shared store 下 observe 真值正确落到同一存储、meter 正常产出。
            self.assertTrue(observe_ok)
            self.assertEqual(observe["queue_remaining"], 1)
            self.assertTrue(meter_ok)


if __name__ == "__main__":
    unittest.main()

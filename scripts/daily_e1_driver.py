"""ZKC · 每日 E1 驱动（fork 1 + fork 2 自动化外壳）。

只自动化**两件机械事**，绝不替你做认知判断（锚 A 的复审标注 still_valid/changed/stale
必须你本人在 /review UI 里点——那是不可自动化的外生锚）：

  1) 真值收口（fork 2）：POST {BASE}/review/api/observe/auto
     服务端算 pushed=今日创建节点数、queue_remaining=当前到期数，写 attention_observation。
     收口断签会让 E1-① 活跃日串归零，且 queue_remaining 是「饱和日」唯一输入（喂 E1-③
     与 can_calibrate），所以不能漏、也不能手工乱填。
  2) 跑 E1 进度仪表（fork 1）：scripts/e1_calibration_progress.py --json
     读 calibration_readiness / 标注率闸门 / 多窗口预算轨迹，写每日日志 + 控制台摘要。

运行方式（由调度器每日触发，非交互）：
    python scripts/daily_e1_driver.py            # 默认 direct：不依赖 HTTP 服务
    python scripts/daily_e1_driver.py --http     # 强制走 HTTP 收口（需 review 服务常驻）
环境变量：
    ZKC_MODE      direct（默认）| http           （direct 直接对存储层跑，无需服务）
    ZKC_BASE      默认 http://127.0.0.1:8000     （仅 --http 模式下的 review 服务地址）
    ZKC_STORAGE   pg | memory，默认 pg           （读数来源，direct 与收口共用同一 store）
    ZKC_LOG       JSONL 日志路径，默认 <项目根>/logs/e1_daily.log
退出码：
    0  两步都成功（无论 E1 三条判据是否满足，只报告）
    2  真值收口重试后仍失败（--http 模式且服务不可达）——调度器可据此告警
    3  仪表失败

注意：本脚本只读 + 只写 attention_observation 收口，不碰任何业务表、不伪造复审标注。
direct 模式下收口 = record_daily_observation_auto(store) 纯函数，对存储层直接跑，
故 review 服务宕机不再阻塞每日收口（Risk A1 解决）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("ZKC_BASE", "http://127.0.0.1:8000").rstrip("/")
STORAGE = os.environ.get("ZKC_STORAGE", "pg")
LOG_PATH = Path(os.environ.get("ZKC_LOG", ROOT / "logs" / "e1_daily.log"))
OBSERVE_URL = f"{BASE}/review/api/observe/auto"
METER_SCRIPT = ROOT / "scripts" / "e1_calibration_progress.py"
RETRY = 3
BACKOFF_S = 30


@dataclass
class Config:
    base: str
    storage: str
    log_path: Path
    mode: str  # "direct" | "http"
    retry: int = RETRY
    backoff_s: float = float(BACKOFF_S)


def load_config(env=None) -> Config:
    """从 env 构造运行配置；默认 mode=direct（不依赖 HTTP 服务）。"""
    env = env if env is not None else os.environ
    mode = env.get("ZKC_MODE", "direct")
    return Config(
        base=env.get("ZKC_BASE", "http://127.0.0.1:8000").rstrip("/"),
        storage=env.get("ZKC_STORAGE", "pg"),
        log_path=Path(env.get("ZKC_LOG", ROOT / "logs" / "e1_daily.log")),
        mode=mode,
    )


def _post_observe_auto(base: str) -> dict:
    """调真值收口端点（--http 模式），带重试。失败抛 urllib 异常。"""
    data = urllib.parse.urlencode({}).encode()
    req = urllib.request.Request(
        f"{base}/review/api/observe/auto", data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def do_observe_http(cfg: Config) -> dict:
    last_err = None
    for attempt in range(1, cfg.retry + 1):
        try:
            return _post_observe_auto(cfg.base)
        except Exception as e:  # noqa: BLE001 — 网络层异常统一重试
            last_err = e
            if attempt < cfg.retry:
                time.sleep(cfg.backoff_s)
    raise RuntimeError(f"observe/auto 重试 {cfg.retry} 次仍失败: {last_err}")


def do_observe_direct(store) -> dict:
    """真值收口 = record_daily_observation_auto(store) 纯函数，对存储层直接跑。

    无需 HTTP 服务常驻（Risk A1 解决）：review 服务宕机不再阻塞每日收口。
    """
    from zkc.web.review import record_daily_observation_auto
    return record_daily_observation_auto(store)


def do_observe(cfg: Config, store=None) -> dict:
    if cfg.mode == "http":
        return do_observe_http(cfg)
    return do_observe_direct(store)


def _import_meter():
    spec = importlib.util.spec_from_file_location(
        "e1_calibration_progress", str(METER_SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def do_meter(cfg: Config, store=None) -> dict:
    """仪表只读存储层（本就无需 HTTP 服务）；in-process 调用复用同一 store，
    使内存后端下收口写入与仪表读取命中同一存储、读数一致。"""
    meter = _import_meter()
    return meter.build_report(cfg.storage, storage=store)


def run(cfg: Config, store=None):
    """核心执行：真值收口 + 仪表。返回 (observe, meter, observe_ok, meter_ok)。

    不直接写日志/退出码，便于测试注入；main() 负责 CLI 外壳。
    若未注入 store，按 cfg.storage 自建（direct 与 meter 共用同一实例）。
    """
    if store is None:
        from zkc.repository import get_storage
        store = get_storage(cfg.storage)

    observe, observe_ok = _safe(lambda: do_observe(cfg, store))
    meter, meter_ok = _safe(lambda: do_meter(cfg, store))
    return observe, meter, observe_ok, meter_ok


def _safe(fn):
    try:
        return fn(), True
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}, False


def _fmt_criteria(r: dict) -> str:
    c1 = r["criteria"]["c1_cumulative_active_days"]
    c2 = r["criteria"]["c2_labeling_rate_gate"]
    c3 = r["criteria"]["c3_budget_convergence"]
    mark = lambda m: "✓" if m else "✗"
    return (
        f"[1]活跃日 {mark(c1['met'])}(累计{c1['cumulative_active']}/{c1['required']},"
        f"最新日={c1['latest_ok']}) "
        f"[2]标注率 {mark(c2['met'])}({c2['rate']}) "
        f"[3]预算收敛 {mark(c3['met'])}(cv={c3['cv']})"
    )


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="ZKC 每日 E1 驱动（direct 默认，不依赖 HTTP 服务）")
    ap.add_argument("--http", action="store_true",
                    help="强制走 HTTP 收口（需 review 服务常驻）")
    args = ap.parse_args()

    env = dict(os.environ)
    if args.http:
        env["ZKC_MODE"] = "http"
    cfg = load_config(env=env)

    observe, meter, observe_ok, meter_ok = run(cfg)

    ts = datetime.now(timezone.utc).isoformat()
    print(f"=== ZKC 每日 E1 驱动 @ {ts} (mode={cfg.mode}) ===")
    if observe_ok:
        print(f"  收口(auto): pushed={observe.get('pushed')} "
              f"queue_remaining={observe.get('queue_remaining')} "
              f"completed={observe.get('completed')} labeled={observe.get('labeled_completed')}")
    else:
        print(f"  ⚠ 收口失败: {observe.get('error')}")
    if meter_ok:
        print(f"  仪表: {_fmt_criteria(meter)}")
        print(f"  >>> E1 全满足: {'YES ✅' if meter['all_exit_criteria_met'] else 'NO ⏳'}")
    else:
        print(f"  ⚠ 仪表失败: {meter.get('error')}")

    # JSONL 日志（追加）
    cfg.log_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.log_path.open("a", encoding="utf-8").write(json.dumps(
        dict(as_of=ts, mode=cfg.mode, observe=observe, meter=meter,
             observe_ok=observe_ok, meter_ok=meter_ok),
        ensure_ascii=False, default=str) + "\n")

    if not observe_ok:
        return 2
    if not meter_ok:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

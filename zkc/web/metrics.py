"""ZKC · 复利度量面板 UI（P5.2，MVP 必选的「复利健康度」总览）。

把 zkc.metrics.metrics_report 暴露成：
  GET /metrics      → SSR 卡片页（连接密度/复用率/方法论产出/衰减可控/复利系数）
  GET /metrics/api   → JSON（供管道 / 周报消费）

阈值/权重/目标全部走 zkc.tuning；页面展示复利系数时附带各分量口径说明，
并指出衰减可控成立前提（注意力预算 n/(0.6×interval)，节点 1-8-6）——预算不满足时该值
预期偏低属供给问题而非指标问题。
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from zkc import metrics as M
from zkc import scheduling as S
from zkc.repository.protocols import Storage

METRICS_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZKC 复利度量面板</title>
<style>
  :root { color-scheme: light; }
  body { font-family: system-ui, -apple-system, "PingFang SC", sans-serif; max-width: 880px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fafafa; }
  h1 { font-size: 1.4rem; }
  p.hint { color: #666; font-size: .9rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .8rem; margin-top: 1rem; }
  .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: .9rem; }
  .card .k { font-size: .72rem; color: #888; text-transform: uppercase; letter-spacing: .03em; font-weight: 600; }
  .card .v { font-size: 1.7rem; font-weight: 700; margin: .3rem 0; }
  .card .d { font-size: .78rem; color: #666; }
  .hero { border-color: #6366f1; background: #eef2ff; }
  .hero .v { color: #4338ca; }
  a { color: #4338ca; }
</style>
</head>
<body>
<h1>ZKC · 复利度量面板</h1>
<p class="hint">五个度量合成「复利健康度」。衰减可控成立前提：注意力预算满足 n/(0.6×interval)（否则该值预期偏低属供给问题）。</p>
<div class="grid" id="grid"><div class="card"><div class="k">加载中</div></div></div>
<p style="margin-top:1rem;"><a href="/review">← 返回每日复审队列</a></p>
<script>
  async function load() {
    const r = await fetch('/metrics/api'); const j = await r.json();
    const cards = [
      ['复利系数', j.compounding_factor, 'connection×w + reuse×w + method×w + decay×w', 'hero'],
      ['连接密度', j.connection_density, '被反向连接/derived_from 触达的动态节点占比'],
      ['复用率', j.reuse_rate, '被后续条目引用(citation)的 claim 占比'],
      ['方法论产出', j.methodology_output, '由结合算子产出的建模/方法论条目数'],
      ['衰减可控', j.decay_controllability, '到期动态节点被蒸馏/结合引用或归档的比例'],
    ];
    document.getElementById('grid').innerHTML = cards.map(([k,v,d,cls]) => `
      <div class="card ${cls||''}">
        <div class="k">${k}</div>
        <div class="v">${k === '方法论产出' ? v : (typeof v === 'number' ? (Math.round(v*1000)/10) + '%' : v)}</div>
        <div class="d">${d}</div>
      </div>`).join('');
  }
  load();
  setInterval(load, 30000);
</script>
</body>
</html>
"""


def register_metrics_routes(app, store: Storage) -> None:
    router = APIRouter()

    @router.get("/metrics", response_class=HTMLResponse)
    def metrics_page() -> HTMLResponse:
        return HTMLResponse(METRICS_HTML)

    @router.get("/metrics/api")
    def metrics_api() -> dict:
        report = M.metrics_report(store)
        # 附带口径说明与依赖状态，便于消费方核对（而非只看一个数）
        report["notes"] = {
            "compounding_factor": "connection_density·w + reuse_rate·w + method_norm·w + decay_controllability·w（权重/目标见 zkc.tuning，默认等权）",
            "decay_controllability_precondition": "需满足注意力预算 n/(0.6×interval)，否则预期偏低",
            "attention_budget_demand": _budget_demand(store),
        }
        return report

    app.include_router(router)


def _budget_demand(store: Storage) -> float | None:
    try:
        return round(S.daily_demand(store.load_schedulable()), 4)
    except Exception:
        return None

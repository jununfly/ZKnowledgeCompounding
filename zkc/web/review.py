"""ZKC · 每日复审队列 UI（P4.2，MVP 必选）。

承载两个自指闭环的唯一外生锚（架构 §6.5.1 / PRD 目标 5）：

  锚 A · 复审结果标注（still_valid / changed / stale / browse）
       → 驱动 L3 interval 反馈（zkc.scheduling.adapt_interval）
       → 必须携带标注，否则 L3 是装饰（衰减-only 复审是永久 no-op，spike-09 F1）

  锚 B · 每日收口埋点（pushed / completed / queue_remaining / labeled_completed）
       → 驱动 budget 估计（zkc.scheduling.estimate_budget / update_budget）
       → 容量只能观测，budget 估计器在 confidence='none' 时永远静止

同一界面同时修好两个「不携带信息」的闭环：一次交互既标注复审结果（锚 A），
又累加今日观测计数（锚 B）。无此界面，两个闭环全废。

复用 capture 同款 FastAPI 骨架（create_app 调用 register_review_routes）。
纯函数层（review_queue_view / decide_review / record_daily_observation）无 HTTP 依赖，
可脱离 web 栈单测（内存 fake / PG 同构）。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from zkc import scheduling as S
from zkc.decay import refresh_decay
from zkc.repository.models import AttentionObservation
from zkc.repository.protocols import Storage

# 复审标注 → L3 判定语义（AIMD 因子）。still_valid=节奏恰当(on_time, ×1)；
# changed/stale 都表示信息比预期腐化更快(too_late, ×0.7 缩短)；browse=仅浏览不标注。
OUTCOME_VERDICT = {
    "still_valid": "on_time",
    "changed": "too_late",
    "stale": "too_late",
}


# ---------------------------------------------------------------- 序列化助手

def _node_to_dict(n) -> dict:
    iv = n.review_interval
    return dict(
        id=str(n.id),
        title=n.title,
        track=n.track,
        decay_score=round(n.decay_score, 3) if n.decay_score is not None else None,
        review_interval_days=(iv.total_seconds() / 86400.0) if iv is not None else None,
        interval_source=n.interval_source,
        last_reviewed_at=(n.last_reviewed_at.isoformat() if n.last_reviewed_at else None),
    )


def _obs_to_dict(o: Optional[AttentionObservation]) -> Optional[dict]:
    if o is None:
        return None
    return dict(day=o.day.isoformat() if isinstance(o.day, datetime) else o.day.isoformat(),
                pushed=o.pushed, completed=o.completed,
                queue_remaining=o.queue_remaining, labeled_completed=o.labeled_completed)


# ---------------------------------------------------------------- 纯函数编排层

def review_queue_view(store: Storage, now: Optional[datetime] = None) -> dict:
    """取当前复审队列 + 两个闭环的状态快照（供页面渲染与 API 返回）。"""
    now = now or datetime.now(timezone.utc)
    refresh_decay(store.nodes, now)                      # 应用层触发器：先重算衰减
    due = store.nodes.list_due_for_review(now)
    today = now.date()
    gate = S.labeling_rate_from(store.attention.list_recent(30))
    budget = S.estimate_budget(store)
    return dict(
        as_of=now.isoformat(),
        items=[_node_to_dict(n) for n in due],
        due_count=len(due),
        today_observation=_obs_to_dict(store.attention.get(today)),
        gate=gate,
        budget=budget,
    )


def decide_review(
    store: Storage,
    node_id,
    outcome: str,
    now: Optional[datetime] = None,
) -> dict:
    """处理一次复审标注（锚 A + 锚 B 累加）。

    outcome ∈ {still_valid, changed, stale} 触发 L3 + 标注计数；
    outcome == 'browse' 仅复位衰减时钟 + completed++（不标注，不触发 L3），
    用于让标注率闸门有意义（completed > labeled 时率可 < 100%，L3 停机）。
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(node_id, str):
        node_id = UUID(node_id)
    node = store.nodes.get(node_id)
    if node is None:
        raise ValueError(f"node {node_id} not found")

    result = dict(node_id=str(node_id), outcome=outcome)
    if outcome == "browse":
        # 仅浏览未标注：复位时钟 + completed++（不标注），不触发 L3
        store.nodes.mark_reviewed(node_id, now)
        result.update(verdict=None, applied=False, new_interval_days=None,
                      reason="browsed without label: clock reset, no L3")
    elif outcome in OUTCOME_VERDICT:
        verdict = OUTCOME_VERDICT[outcome]
        res = S.adapt_interval(store, node_id, node.decay_score, outcome=verdict)
        store.nodes.mark_reviewed(node_id, now)
        result.update(
            verdict=verdict,
            applied=res.get("applied"),
            new_interval_days=res.get("new_days"),
            reason=res.get("reason"),
        )
    else:
        raise ValueError(f"unknown outcome: {outcome}")

    # 累加今日观测：completed++ 与 labeled_completed++（仅标注动作）
    today = now.date()
    existing = store.attention.get(today)
    labeled = outcome != "browse"
    obs = AttentionObservation(
        day=today,
        pushed=existing.pushed if existing else 0,
        completed=(existing.completed if existing else 0) + 1,
        queue_remaining=existing.queue_remaining if existing else 0,
        labeled_completed=(existing.labeled_completed if existing else 0) + (1 if labeled else 0),
    )
    store.attention.record_observation(obs)

    result["gate"] = S.labeling_rate_from(store.attention.list_recent(30))
    result["today_observation"] = _obs_to_dict(store.attention.get(today))
    return result


def record_daily_observation(
    store: Storage,
    pushed: int,
    queue_remaining: int,
    now: Optional[datetime] = None,
) -> dict:
    """每日收口（锚 B）：写入 pushed / queue_remaining，保留当日已累加的 completed/labeled。"""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    existing = store.attention.get(today)
    obs = AttentionObservation(
        day=today,
        pushed=pushed,
        completed=existing.completed if existing else 0,
        queue_remaining=queue_remaining,
        labeled_completed=existing.labeled_completed if existing else 0,
    )
    store.attention.record_observation(obs)
    return _obs_to_dict(store.attention.get(today))


# ---------------------------------------------------------------- SSR 页面

REVIEW_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZKC 每日复审队列</title>
<style>
  :root { color-scheme: light; }
  body { font-family: system-ui, -apple-system, "PingFang SC", sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fafafa; }
  h1 { font-size: 1.4rem; margin-bottom: .2rem; }
  p.hint { color: #666; font-size: .9rem; margin-top: 0; }
  .status { display: flex; gap: .8rem; flex-wrap: wrap; margin: 1rem 0; }
  .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: .7rem .9rem; font-size: .85rem; }
  .card b { display: block; font-size: .7rem; color: #888; margin-bottom: .25rem; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; }
  .ok { color: #15803d; } .warn { color: #b45309; } .bad { color: #b91c1c; }
  .item { background: #fff; border: 1px solid #e5e7eb; border-left: 4px solid #d97706; border-radius: 8px; padding: .8rem .9rem; margin-bottom: .6rem; }
  .item .title { font-weight: 600; }
  .item .meta { color: #666; font-size: .8rem; margin: .25rem 0 .5rem; }
  .item button { margin-right: .4rem; padding: .35rem .8rem; font: inherit; cursor: pointer; border: 1px solid #cbd5e1; background: #f8fafc; border-radius: 6px; }
  .item button.valid { border-color: #16a34a; color: #15803d; }
  .item button.changed { border-color: #d97706; color: #b45309; }
  .item button.stale { border-color: #dc2626; color: #b91c1c; }
  .item button.browse { border-color: #94a3b8; color: #475569; }
  .empty { color: #888; font-style: italic; padding: 1rem; text-align: center; }
  form.close { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: .9rem; margin-top: 1.2rem; }
  form.close label { font-size: .85rem; margin-right: .3rem; }
  form.close input { width: 5rem; padding: .3rem; margin-right: 1rem; }
  form.close button { padding: .4rem 1rem; font: inherit; cursor: pointer; }
  .flash { margin-top: .6rem; font-size: .85rem; }
</style>
</head>
<body>
<h1>ZKC · 每日复审队列</h1>
<p class="hint">动态轨条目腐化到阈值即入队。每处理一条请标注结果（驱动 L3 复审节奏）并自动累加今日计数（驱动注意力预算估计）。</p>

<div class="status">
  <div class="card"><b>到期条目</b><span id="dueCount">…</span></div>
  <div class="card"><b>标注率闸门</b><span id="gate">…</span></div>
  <div class="card"><b>预算估计</b><span id="budget">…</span></div>
  <div class="card"><b>今日观测</b><span id="obs">…</span></div>
</div>

<div id="list"><div class="empty">加载中…</div></div>

<form class="close" id="closeForm">
  <b style="font-size:.8rem;color:#888;">每日收口</b><br>
  <label>今日推送(pushed)</label><input id="pushed" type="number" min="0" value="0">
  <label>收口剩余(queue_remaining)</label><input id="qr" type="number" min="0" value="0">
  <button type="submit">记录收口</button>
  <span class="flash" id="closeFlash"></span>
</form>

<script>
  const $ = (id) => document.getElementById(id);
  async function load() {
    const r = await fetch('/review/api/queue');
    const j = await r.json();
    $('dueCount').innerHTML = j.due_count;
    const g = j.gate;
    $('gate').innerHTML = g.gate === 'open'
      ? `<span class="ok">开放</span> ${g.rate ? (g.rate*100).toFixed(0)+'%' : '(warm-up)'}`
      : `<span class="bad">关闭</span> ${(g.rate*100).toFixed(0)}%`;
    const b = j.budget;
    $('budget').innerHTML = b.estimate == null
      ? `<span class="warn">none</span>` : `${b.estimate}/天 <span class="ok">${b.confidence}</span>`;
    const o = j.today_observation;
    $('obs').innerHTML = o ? `完成 ${o.completed} / 标注 ${o.labeled_completed} / 剩余 ${o.queue_remaining}` : '无';
    const list = $('list');
    if (!j.items.length) { list.innerHTML = '<div class="empty">队列为空 ✓</div>'; return; }
    list.innerHTML = j.items.map(it => `
      <div class="item" id="it-${it.id}">
        <div class="title">${escapeHtml(it.title)}</div>
        <div class="meta">decay ${(it.decay_score*100).toFixed(0)}% · 节奏 ${it.review_interval_days ? it.review_interval_days.toFixed(1)+'d' : '—'} · ${it.interval_source}</div>
        <button class="valid"  onclick="decide('${it.id}','still_valid')">仍有效</button>
        <button class="changed" onclick="decide('${it.id}','changed')">已变</button>
        <button class="stale"   onclick="decide('${it.id}','stale')">已腐</button>
        <button class="browse"  onclick="decide('${it.id}','browse')">仅浏览</button>
      </div>`).join('');
  }
  async function decide(id, outcome) {
    const r = await fetch('/review/api/decide', {
      method: 'POST', headers: {'Content-Type':'application/x-www-form-urlencoded'},
      body: 'node_id=' + encodeURIComponent(id) + '&outcome=' + outcome });
    const j = await r.json();
    const el = $('it-' + id);
    if (el) { el.style.opacity = .5; el.querySelector('.title').insertAdjacentHTML('beforeend',
      ` <span style="font-size:.75rem;color:#16a34a;">✓ ${j.verdict || '浏览'}</span>`); }
    await load();
  }
  $('closeForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const r = await fetch('/review/api/observe', {
      method: 'POST', headers: {'Content-Type':'application/x-www-form-urlencoded'},
      body: 'pushed=' + $('pushed').value + '&queue_remaining=' + $('qr').value });
    const j = await r.json();
    $('closeFlash').innerHTML = `<span class="ok">已记录：推送 ${j.pushed} / 剩余 ${j.queue_remaining}</span>`;
    await load();
  });
  function escapeHtml(s){return (s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  load();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- 路由装配

def register_review_routes(app, store: Storage) -> None:
    """把复审队列路由挂到已有 FastAPI app（create_app 调用）。store 注入以便脱离 PG 单测。"""
    router = APIRouter()

    @router.get("/review", response_class=HTMLResponse)
    def review_page() -> HTMLResponse:
        return HTMLResponse(REVIEW_HTML)

    @router.get("/review/api/queue")
    def queue_api() -> dict:
        return review_queue_view(store)

    @router.post("/review/api/decide")
    def decide_api(node_id: str = Form(...), outcome: str = Form(...)) -> dict:
        return decide_review(store, node_id, outcome)

    @router.post("/review/api/observe")
    def observe_api(pushed: int = Form(0), queue_remaining: int = Form(0)) -> dict:
        return record_daily_observation(store, pushed, queue_remaining)

    app.include_router(router)

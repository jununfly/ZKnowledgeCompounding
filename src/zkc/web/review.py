"""ZKC · 每日复审队列 UI（P4.2，MVP 必选）——**web/presentation 层**。

领域逻辑（纯编排函数 / REVIEW_REASON / 序列化助手）已迁至 `zkc.review`（无 fastapi 依赖，
见 finding 26：解耦 cli/mcp 与 web 栈）。本模块只保留 FastAPI 路由装配 `register_review_routes`
与 SSR 页面 `REVIEW_HTML`，并从 `zkc.review` re-export 领域公开名以兼容既有调用方与测试。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from zkc.repository.protocols import Storage
from zkc.review import (  # noqa: F401  (re-export for back-compat: callers/tests import these from here)
    REVIEW_REASON,
    _node_to_dict,
    _obs_to_dict,
    _iv_days,
    _proposal_to_dict,
    review_queue_view,
    classify_queue_view,
    classify_resolve_action,
    decide_review,
    record_daily_observation,
    record_daily_observation_auto,
    process_expired_view,
    higher_dim_proposals_view,
    approve_higher_dim,
    dismiss_higher_dim,
    faithfulness_queue_view,
    adjudicate_claim,
)


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
  .tasks { margin: 1.4rem 0 1.6rem; }
  .tasks h2 { font-size: 1.1rem; margin: 0 0 .3rem; }
  .tasks .hint { color: #666; font-size: .85rem; margin: 0 0 .8rem; }
  .task-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: .7rem; }
  .tcard { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: .8rem .9rem; box-shadow: 0 1px 2px rgba(0,0,0,.04); position: relative; }
  .tcard .tag { display: inline-block; font-size: .7rem; padding: .12rem .55rem; border-radius: 999px; font-weight: 600; margin-bottom: .45rem; }
  .tag.periodic { background: #eff6ff; color: #2563eb; }   /* 蓝 */
  .tag.alert    { background: #fff7ed; color: #ea580c; }   /* 橙 */
  .tag.once     { background: #f5f3ff; color: #7c3aed; }   /* 紫 */
  .tcard .ttl { font-weight: 600; font-size: .95rem; line-height: 1.3; }
  .tcard .det { color: #64748b; font-size: .8rem; margin: .35rem 0 .6rem; line-height: 1.4; }
  .tcard .foot { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
  .tcard .status { font-size: .78rem; display: flex; align-items: center; gap: .35rem; color: #64748b; }
  .dot { width: .55rem; height: .55rem; border-radius: 50%; display: inline-block; }
  .dot.open { background: #2563eb; }       /* 待办=蓝点 */
  .dot.done { background: #16a34a; }        /* 完成=绿点 */
  .tcard button.done-btn { padding: .3rem .8rem; font: inherit; cursor: pointer; border: 1px solid #16a34a; color: #15803d; background: #f0fdf4; border-radius: 6px; }
  .tcard.is-done { opacity: .62; }
  .tcard.is-done .done-btn { display: none; }
  .tasks .summary { font-size: .82rem; color: #888; margin-top: .6rem; }
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

<div class="tasks" id="taskPanel">
  <h2>今日任务队列</h2>
  <p class="hint">zj 待办以卡片呈现（过渡清单已迁移为规则自动生成的任务队列）。勾选完成即记录，不遗漏。</p>
  <div class="task-cards" id="taskCards"><div class="empty">加载中…</div></div>
  <div class="summary" id="taskSummary"></div>
</div>

<div id="classifyPanel">
  <h2 style="font-size:1.1rem;margin-top:1.6rem;">人工定轨（捕获弃权队列）</h2>
  <p class="hint">捕获时路由引擎弃权（LLM 判 vague/低置信、或离线不可判）的条目在此等待人工定轨。点静态/动态即落轨并闭环（P2.3）。</p>
  <div id="classifyList"><div class="empty">加载中…</div></div>
</div>

<div id="list"><div class="empty">加载中…</div></div>

<div id="tombPanel">
  <h2 style="font-size:1.1rem;margin-top:1.6rem;">墓碑区（软删除 · 可恢复）</h2>
  <p class="hint">墓碑节点对全部功能不可见，7 天后按月扫描真删；真删前可在此恢复（仅 zj 本人，人环）。</p>
  <div id="tombList"><div class="empty">加载中…</div></div>
</div>

<form class="close" id="closeForm">
  <b style="font-size:.8rem;color:#888;">每日收口</b><br>
  <label>今日推送(pushed)</label><input id="pushed" type="number" min="0" value="0">
  <label>收口剩余(queue_remaining)</label><input id="qr" type="number" min="0" value="0">
  <button type="submit">记录收口</button>
  <span class="flash" id="closeFlash"></span>
</form>

<div id="hdPanel">
  <h2 style="font-size:1.1rem;margin-top:1.6rem;">更高维聚合提议</h2>
  <p class="hint">系统基于「当日待复审节点」提议可聚合的更高维 context（稀缺注意力：系统提议、人确认）。阈值未校准时为实验性提议，须人审；真实校准需吃同一批外生锚埋点（见下方状态）。</p>
  <div class="status">
    <div class="card"><b>校准就绪</b><span id="hdCalib">…</span></div>
    <div class="card"><b>可操作提议</b><span id="hdCount">…</span></div>
    <div class="card"><b>每日额度</b><span id="hdBudget">…</span></div>
  </div>
  <div id="hdList"><div class="empty">加载中…</div></div>
</div>

<div id="faithPanel">
  <h2 style="font-size:1.1rem;margin-top:1.6rem;">忠实度人审（蒸馏 claim）</h2>
  <p class="hint">LLM 蒸馏/结合产出的断言须人审其忠实性（judge 不可用时全部进队，绝不静默放行）。强制项（矛盾/空分解/全人工模式）永无上限；抽检与审计侧按 F_cap 比例封顶、留痕轮转。裁决走独立预算，不占上方复审计数。</p>
  <div class="status">
    <div class="card"><b>待人审</b><span id="fTotal">…</span></div>
    <div class="card"><b>强制 / 封顶</b><span id="fSplit">…</span></div>
    <div class="card"><b>今日封顶额</b><span id="fCap">…</span></div>
    <div class="card"><b>校准语料</b><span id="fCorpus">…</span></div>
  </div>
  <div id="fList"><div class="empty">加载中…</div></div>
</div>

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
        <button class="stale"   onclick="tombMark('${it.id}')">删除(墓碑)</button>
      </div>`).join('');
  }
  async function decide(id, outcome) {
    let body = 'node_id=' + encodeURIComponent(id) + '&outcome=' + outcome;
    if (outcome === 'changed') {
      // 内容载荷必填，且只能由人逐条给出
      const c = prompt('内容更新载荷（changed 必填，请逐条给出）：');
      if (c === null) return;                       // 取消
      body += '&content=' + encodeURIComponent(c);
    } else if (outcome === 'stale') {
      const b = prompt('stale 分支：cover（覆盖，需内容）/ purge（清除退出回路）', 'cover');
      if (b !== 'cover' && b !== 'purge') return;   // 取消 / 非法
      body += '&stale_branch=' + encodeURIComponent(b);
      if (b === 'cover') {
        const c = prompt('覆盖内容载荷（必填）：');
        if (c === null) return;
        body += '&content=' + encodeURIComponent(c);
      }
    }
    const r = await fetch('/review/api/decide', {
      method: 'POST', headers: {'Content-Type':'application/x-www-form-urlencoded'},
      body });
    if (!r.ok) { alert('复审标注被拒：' + (await r.json()).detail); await load(); return; }
    const j = await r.json();
    const el = $('it-' + id);
    if (el) { el.style.opacity = .5; el.querySelector('.title').insertAdjacentHTML('beforeend',
      ` <span style="font-size:.75rem;color:#16a34a;">✓ ${j.verdict || '浏览'}</span>`); }
    await load();
  }
  async function tombMark(id) {
    if (!confirm('置墓碑：该节点将对所有功能不可见，7 天后按月扫描真删。确认？')) return;
    const op = prompt('人环确认：输入操作者标识（zj 本人）：');
    if (op === null) return;
    const r = await fetch('/review/api/tombstone/mark', {
      method: 'POST', headers: {'Content-Type':'application/x-www-form-urlencoded'},
      body: 'node_id=' + encodeURIComponent(id) + '&operator=' + encodeURIComponent(op) });
    if (!r.ok) { alert('墓碑操作被拒：' + (await r.json()).detail); return; }
    await load(); await loadTombstones();
  }
  async function tombRestore(id) {
    if (!confirm('恢复该墓碑节点（is_delete=0）？')) return;
    const op = prompt('人环确认：输入操作者标识（zj 本人）：');
    if (op === null) return;
    const r = await fetch('/review/api/tombstone/restore', {
      method: 'POST', headers: {'Content-Type':'application/x-www-form-urlencoded'},
      body: 'node_id=' + encodeURIComponent(id) + '&operator=' + encodeURIComponent(op) });
    if (!r.ok) { alert('恢复操作被拒：' + (await r.json()).detail); return; }
    await load(); await loadTombstones();
  }
  async function loadTombstones() {
    const r = await fetch('/review/api/tombstones');
    const j = await r.json();
    const box = $('tombList');
    if (!j.items.length) { box.innerHTML = '<div class="empty">无墓碑节点</div>'; return; }
    box.innerHTML = j.items.map(n => `
      <div class="item">
        <div class="title">${escapeHtml(n.title)}</div>
        <div class="meta">墓碑于 ${n.tombstoned_at} · 7 天后可真删</div>
        <button class="valid" onclick="tombRestore('${n.id}')">恢复</button>
      </div>`).join('');
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
  function catLabel(c){return ({periodic:'周期', alert:'预警', once:'一次性'})[c] || c;}

  async function loadTasks() {
    const j = await (await fetch('/review/api/tasks')).json();
    const cards = $('taskCards');
    if (!j.items.length) { cards.innerHTML = '<div class="empty">今日无任务 ✓</div>'; }
    else {
      cards.innerHTML = j.items.map(it => `
        <div class="tcard ${it.status==='done'?'is-done':''}" id="tk-${it.id}">
          <span class="tag ${it.category}">${catLabel(it.category)}</span>
          <div class="ttl">${escapeHtml(it.title)}</div>
          <div class="det">${escapeHtml(it.detail || '')}</div>
          <div class="foot">
            <span class="status"><span class="dot ${it.status}"></span>${it.status==='done'?'已完成':'待办'}</span>
            <button class="done-btn" onclick="completeTask('${it.id}')">完成</button>
          </div>
        </div>`).join('');
    }
    $('taskSummary').innerHTML = `开放 ${j.open_count} · 完成 ${j.done_count}`;
  }
  async function completeTask(id) {
    await fetch('/review/api/tasks/complete', {
      method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'task_id=' + encodeURIComponent(id) });
    await loadTasks();
  }
  load();
  loadTombstones();
  loadTasks();

  async function loadClassify() {
    const j = await (await fetch('/review/api/classify')).json();
    const list = $('classifyList');
    if (!j.items.length) { list.innerHTML = '<div class="empty">无待定轨条目 ✓</div>'; return; }
    list.innerHTML = j.items.map(it => `
      <div class="item" id="cl-${it.id}">
        <div class="title">${escapeHtml(it.title)}</div>
        <div class="meta">${it.preview ? escapeHtml(it.preview.slice(0, 80)) : ''}</div>
        <button class="valid"  onclick="resolveClassify('${it.id}','static')">静态轨</button>
        <button class="changed" onclick="resolveClassify('${it.id}','dynamic')">动态轨</button>
      </div>`).join('');
  }
  async function resolveClassify(id, track) {
    const r = await fetch('/review/api/classify/resolve', {
      method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'item_id=' + encodeURIComponent(id) + '&track=' + track });
    const j = await r.json();
    const el = $('cl-' + id);
    if (el) { el.style.opacity = .5; el.querySelector('.title').insertAdjacentHTML('beforeend',
      ` <span style="font-size:.75rem;color:#16a34a;">✓ 已定 ${j.track}</span>`); }
    setTimeout(loadClassify, 800);
  }
  loadClassify();

  async function loadHd() {
    const j = await (await fetch('/review/api/higher-dim')).json();
    const cal = j.calibration;
    $('hdCalib').innerHTML = cal.ready
      ? `<span class="ok">就绪</span>` : `<span class="warn">未就绪</span> ${cal.days_with_observation}/${cal.calib_min_days}天 · ${cal.saturated_days}/${cal.calib_min_saturated_days}饱和`;
    $('hdCount').innerHTML = j.actionable.length + ' / 候选 ' + j.seeds_total;
    const b = j.budget_status;
    $('hdBudget').innerHTML = `${b.used}/${b.cap}` + (b.truncated ? '（已封顶）' : '');
    const list = $('hdList');
    if (!j.actionable.length) { list.innerHTML = '<div class="empty">暂无可操作的聚合提议 ✓</div>'; return; }
    list.innerHTML = j.actionable.map(p => `
      <div class="item" id="hd-${p.seed_node_id}">
        <div class="title">${escapeHtml(p.suggested_title)}</div>
        <div class="meta">${p.neighbor_ids.length} 个近邻 · 相似度 ${p.similarities.map(s=>(s*100).toFixed(0)+'%').join('/')} · ${p.calibrated ? '已校准' : '未校准'}</div>
        <button class="valid" onclick="hdApprove('${p.seed_node_id}')">创建</button>
        <button class="browse" onclick="hdDismiss('${p.seed_node_id}')">忽略</button>
      </div>`).join('');
  }
  async function hdApprove(seed) {
    const r = await fetch('/review/api/higher-dim/approve', {
      method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'seed_node_id=' + encodeURIComponent(seed) });
    const j = await r.json();
    const el = $('hd-' + seed);
    if (el) el.style.opacity = .5;
    await loadHd();
  }
  async function hdDismiss(seed) {
    await fetch('/review/api/higher-dim/dismiss', {
      method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'seed_node_id=' + encodeURIComponent(seed) });
    await loadHd();
  }
  loadHd();

  async function loadF() {
    const j = await (await fetch('/review/api/faithfulness')).json();
    const q = j.queue;
    $('fTotal').innerHTML = q.total_pending;
    $('fSplit').innerHTML = `${q.forced_total} / ${q.capped_total}` +
      (q.capped_withheld ? ` <span class="warn">(留痕 ${q.capped_withheld})</span>` : '');
    $('fCap').innerHTML = `${q.capped_shown}/${q.cap} <span style="font-size:.75rem;color:#888;">${(q.f_cap_ratio*100).toFixed(0)}% · ${q.f_cap_source}</span>`;
    const cal = j.calibration;
    $('fCorpus').innerHTML = cal.size
      ? `${cal.size} 条 · 判对 ${(cal.judge_correct_rate*100).toFixed(0)}%`
      : '0 条（judge 上线后自然生长）';
    const list = $('fList');
    if (!q.items.length) { list.innerHTML = '<div class="empty">没有待人审的断言 ✓</div>'; return; }
    list.innerHTML = q.items.map(c => `
      <div class="item" id="fc-${c.id}">
        <div class="title">${escapeHtml(c.statement)}</div>
        <div class="meta">路由 ${c.faithfulness_route || '—'}${c.judge_reason ? ' · ' + escapeHtml(c.judge_reason) : ''}${c.human_verdict ? ' · 判定 ' + c.human_verdict : ''}</div>
        <button class="valid"  onclick="fAdjudicate('${c.id}','confirm')">忠实</button>
        <button class="stale"  onclick="fAdjudicate('${c.id}','reject')">不忠实</button>
      </div>`).join('');
  }
  async function fAdjudicate(id, verdict) {
    const r = await fetch('/review/api/faithfulness/adjudicate', {
      method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'claim_id=' + encodeURIComponent(id) + '&verdict=' + verdict });
    const j = await r.json();
    const el = $('fc-' + id);
    if (el) { el.style.opacity = .5; el.querySelector('.title').insertAdjacentHTML('beforeend',
      ` <span style="font-size:.75rem;color:#16a34a;">✓ ${j.verdict}</span>`); }
    await loadF();
  }
  loadF();
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
    def decide_api(
        node_id: str = Form(...),
        outcome: str = Form(...),
        content: Optional[str] = Form(None),
        stale_branch: Optional[str] = Form(None),
    ) -> dict:
        try:
            return decide_review(
                store, node_id, outcome,
                content=content, stale_branch=stale_branch)
        except ValueError as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/review/api/tombstone/mark")
    def tombstone_mark_api(
        node_id: str = Form(...),
        operator: str = Form(...),
        reason: Optional[str] = Form(None),
    ) -> dict:
        """墓碑标记（人环 Q7）：operator 必填即 zj 本人授权；二次确认在 UI 层。"""
        from zkc.tombstone import mark_tombstone
        try:
            return mark_tombstone(store, node_id, operator=operator, reason=reason)
        except (ValueError, KeyError) as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/review/api/tombstone/restore")
    def tombstone_restore_api(
        node_id: str = Form(...),
        operator: str = Form(...),
        reason: Optional[str] = Form(None),
    ) -> dict:
        """墓碑恢复（人环 Q7）：operator 必填即 zj 本人授权。"""
        from zkc.tombstone import restore_node
        try:
            return restore_node(store, node_id, operator=operator, reason=reason)
        except (ValueError, KeyError) as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/review/api/tombstones")
    def tombstones_api() -> dict:
        """墓碑列表（供 UI 恢复区）：列已墓碑且未真删的节点。"""
        from datetime import datetime, timezone
        nodes = store.nodes.list_tombstones_before(datetime.now(timezone.utc))
        return {
            "count": len(nodes),
            "items": [{"id": str(n.id), "title": n.title,
                       "tombstoned_at": n.deleted_at} for n in nodes],
        }

    @router.post("/review/api/observe")
    def observe_api(pushed: int = Form(0), queue_remaining: int = Form(0)) -> dict:
        return record_daily_observation(store, pushed, queue_remaining)

    @router.post("/review/api/observe/auto")
    def observe_auto_api() -> dict:
        """每日收口真值自动版（fork 2）：服务端算 pushed/queue_remaining，供 launchd/TaskScheduler 调用。"""
        return record_daily_observation_auto(store)

    @router.get("/review/api/classify")
    def classify_api() -> dict:
        """人工定轨队列：捕获弃权条目（P2.3 消费端上 UI）。"""
        return classify_queue_view(store)

    @router.post("/review/api/classify/resolve")
    def classify_resolve_api(item_id: str = Form(...), track: str = Form(...)) -> dict:
        return classify_resolve_action(store, item_id, track)

    @router.post("/review/api/process-expired")
    def process_expired_api(attention_pressure: float = Form(0.0)) -> dict:
        """到期分流流水线钩子：refresh_decay 后路由全部到期动态节点（可接每日 cron）。"""
        return process_expired_view(store, attention_pressure=attention_pressure)

    @router.get("/review/api/higher-dim")
    def higher_dim_api() -> dict:
        return higher_dim_proposals_view(store)

    @router.post("/review/api/higher-dim/approve")
    def higher_dim_approve_api(seed_node_id: str = Form(...)) -> dict:
        return approve_higher_dim(store, seed_node_id)

    @router.post("/review/api/higher-dim/dismiss")
    def higher_dim_dismiss_api(seed_node_id: str = Form(...)) -> dict:
        return dismiss_higher_dim(store, seed_node_id)

    @router.get("/review/api/faithfulness")
    def faithfulness_api() -> dict:
        """忠实度人审查看：F_cap 日队列 + 校准语料概览（忠实度闸门）。"""
        return faithfulness_queue_view(store)

    @router.post("/review/api/faithfulness/adjudicate")
    def faithfulness_adjudicate_api(claim_id: str = Form(...), verdict: str = Form(...)) -> dict:
        """审查卡片操作：confirm/reject/edit（独立预算，不写复审埋点）。"""
        return adjudicate_claim(store, claim_id, verdict)

    app.include_router(router)

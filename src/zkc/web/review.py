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
from zkc import expiry as EX
from zkc import faithfulness as F
from zkc.context import ContextAssembler, HigherDimProposal
from zkc.decay import refresh_decay
from zkc.ingest import list_pending_classify, resolve_classify
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


def classify_queue_view(store: Storage) -> dict:
    """捕获弃权的人工定轨队列视图（P2.3 消费端上 UI，2026-11-02 补齐）。

    路由引擎弃权（vague/低置信/离线不可判）的条目在此等待人工定轨；
    resolve 后节点落轨 + review_queue 条目标记 resolved。
    """
    items = []
    for it in list_pending_classify(store=store):
        node = store.nodes.get(it.node_id)
        # preview 服务端截断：全文可能上百 KB，API 不该整包下发
        preview = (node.content[:120] if node and node.content else None) or None
        items.append(dict(
            id=str(it.id),
            title=node.title if node else "(节点缺失)",
            preview=preview,
            created_at=(it.created_at.isoformat() if it.created_at else None),
        ))
    return dict(items=items, count=len(items))


def classify_resolve_action(store: Storage, item_id: str, track: str) -> dict:
    """人工定轨动作：track ∈ {static, dynamic}，非法即拒（resolve_classify 内校验）。"""
    node = resolve_classify(UUID(item_id), track, store=store)
    return dict(ok=True, node_id=str(node.id), track=track)


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


def record_daily_observation_auto(store: Storage, now: Optional[datetime] = None) -> dict:
    """每日收口（锚 B）的真值自动版：服务端计算 pushed / queue_remaining，避免手工填表造假。

    - pushed        = 今日（本地零点起）创建的节点数（ingest 吞吐真值源）
    - queue_remaining = 当前仍未复审的到期条目数（list_due_for_review(now) 长度）
    二者均为系统可观测真值；pushed 当前不被任何 E1 判据消费（纯遥测），queue_remaining
    是「饱和日」定义的唯一输入（estimate_budget_from / calibration_readiness 都靠它）。
    保留当日已累加的 completed/labeled，只覆盖 pushed/queue_remaining。
    """
    now = now or datetime.now(timezone.utc)
    start_of_today = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
    pushed = store.nodes.count_nodes_created_since(start_of_today)
    queue_remaining = len(store.nodes.list_due_for_review(now))
    return record_daily_observation(store, pushed, queue_remaining, now=now)


# ---------------------------------------------------------------- 到期分流流水线（残余 1 收口）

def process_expired_view(store: Storage, attention_pressure: float = 0.0,
                        now: Optional[datetime] = None) -> dict:
    """把 spike-08 到期分流路由接入 review/decay 流水线。

    纯函数层（无 HTTP 依赖）：refresh_decay 后路由全部到期动态节点——已捕获节点立即归档
    （单程票终局），有连接/上下文未捕获节点入队蒸馏，孤儿入队交人审。返回路由计数。

    既可被每日 cron 调用，也可经下方 POST 端点手动触发。
    """
    return EX.process_expired_dynamic_nodes(store, attention_pressure=attention_pressure, now=now)


# ---------------------------------------------------------------- 更高维聚合提议（P1 收尾·接入复审流）

def _proposal_to_dict(p: HigherDimProposal) -> dict:
    return dict(
        seed_node_id=str(p.seed_node_id),
        neighbor_ids=[str(n) for n in p.neighbor_ids],
        similarities=[round(s, 4) for s in p.similarities],
        suggested_title=p.suggested_title,
        would_create=p.would_create,
        reason=p.reason,
        existing_context_id=(str(p.existing_context_id)
                             if p.existing_context_id is not None else None),
        calibrated=p.calibrated,
    )


def higher_dim_proposals_view(store: Storage, now: Optional[datetime] = None,
                              k: int = 5, llm=None) -> dict:
    """把 propose_higher_dim_daily 接入复审流：种子 = 当日待复审节点（已在该人类注意力里，
    与复审同会话，自然攒出校准埋点批）。返回可序列化提议 + 预算状态 + 校准就绪度。

    纯函数层（无 HTTP 依赖），可脱离 web 栈单测（内存 fake / PG 同构）。
    """
    now = now or datetime.now(timezone.utc)
    refresh_decay(store.nodes, now)
    day = now.date()
    excluded = store.attention.dismissed_seed_ids(day)
    # 候选 = 当日待复审节点，排除已被人工忽略的种子（dismiss 真生效）
    seeds = [n.id for n in store.nodes.list_due_for_review(now)
             if n.id not in excluded]
    asm = ContextAssembler(store)
    proposals, budget_status = asm.propose_higher_dim_daily(
        seeds, day, k=k, llm=llm, excluded=excluded)
    return dict(
        as_of=now.isoformat(),
        day=str(day),
        seeds_total=len(seeds),
        proposals=[_proposal_to_dict(p) for p in proposals],
        actionable=[_proposal_to_dict(p) for p in proposals if p.would_create],
        budget_status=budget_status,
        calibration=S.calibration_readiness(store),
    )


def approve_higher_dim(store: Storage, seed_node_id, k: int = 5,
                       llm=None, now: Optional[datetime] = None) -> dict:
    """人工确认：从种子重新派生提议（重过门槛/校准/去重），通过则落库为 higher_dim context。

    与「系统提议」同源：人类确认创建也消耗当日 higher_dim 注意力预算，故落 proposal_log。
    纯函数层，可脱离 web 栈单测。
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(seed_node_id, str):
        seed_node_id = UUID(seed_node_id)
    asm = ContextAssembler(store)
    prop = asm.propose_higher_dim(seed_node_id, k=k, llm=llm)
    if not prop.would_create:
        return dict(seed_node_id=str(seed_node_id), created=False,
                    reason=prop.reason, context_id=None)
    cid, tid = asm.create_higher_dim(prop)
    store.attention.record_proposal(now.date(), "higher_dim", seed_node_id)
    return dict(seed_node_id=str(seed_node_id), created=True,
                context_id=str(cid), transform_id=str(tid),
                suggested_title=prop.suggested_title, reason="人工确认创建")


def dismiss_higher_dim(store: Storage, seed_node_id,
                       now: Optional[datetime] = None) -> dict:
    """人工忽略：落 proposal_log(kind='higher_dim_dismissed', seed_id)，当日 sweep 跳过该种子。

    纯函数层，可脱离 web 栈单测。
    """
    now = now or datetime.now(timezone.utc)
    if isinstance(seed_node_id, str):
        seed_node_id = UUID(seed_node_id)
    store.attention.record_proposal(now.date(), "higher_dim_dismissed", seed_node_id)
    return dict(seed_node_id=str(seed_node_id), dismissed=True,
                day=str(now.date()))


# ---------------------------------------------------------------- 忠实度人审卡片（忠实度闸门）

def faithfulness_queue_view(store: Storage, now: Optional[datetime] = None) -> dict:
    """忠实度人审查看视图：F_cap 日队列 + 校准语料概览（纯函数，无 HTTP 依赖）。

    R11 独立预算：本视图与 adjudicate_claim 均不写 attention_observation——
    蒸馏人审不占复审容量口径，R10 的标注率语义不被 claim 人审污染。
    校准语料在 judge 上线前恒空（human_only 的 judge_raw 无 atomic_facts，
    无对照价值），属预期而非缺陷。
    """
    now = now or datetime.now(timezone.utc)
    corpus = F.calibration_corpus(store)
    correct = sum(1 for c in corpus if c["judge_correct"])
    return dict(
        as_of=now.isoformat(),
        queue=F.daily_faithfulness_queue(store),
        calibration=dict(
            size=len(corpus),
            judge_correct=correct,
            judge_correct_rate=(correct / len(corpus)) if corpus else None,
        ),
    )


def adjudicate_claim(
    store: Storage,
    claim_id,
    verdict: str,
    now: Optional[datetime] = None,
) -> dict:
    """审查卡片操作入口：包装 faithfulness.adjudicate（confirm/reject/edit）。

    返回裁决结果 + 刷新后的队列计数。同样不写 attention_observation（R11）。
    """
    res = F.adjudicate(store, claim_id, verdict, now=now)
    res["queue"] = F.daily_faithfulness_queue(store)
    return res


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
    def decide_api(node_id: str = Form(...), outcome: str = Form(...)) -> dict:
        return decide_review(store, node_id, outcome)

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

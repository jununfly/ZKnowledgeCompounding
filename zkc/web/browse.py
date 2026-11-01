"""ZKC · 复利产出检索/浏览 UI（P5.1，T6.1 生产落地）。

两个 tab（decide 已落盘 1-6-1）：
  检索 tab —— 双路：结构化（track/decay 区间/q 子串，R18 主路）
             + embedding 候选召回（nomic 768d，仅候选+人确认，encoder 不可用自动降级）；
  产物 tab —— 复利产出浏览：meta_claim / modeling_artifact 列表 + evidence 反查
             + citation 引用计数（D3/T6.2）。

服务函数（search_payload / artifacts_payload）纯数据、无 HTTP 依赖，便于单测；
SSR 页只负责渲染 JSON。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from zkc import search as S
from zkc.encoder import make_encoder_4096

# R18 加列路径（1-8-4-1）：候选召回默认走 4096 列（qwen3-embedding，
# 1-8-4 实测中文召回合格）；nomic 768 列保留，可用 column="embedding" 切回。
RETRIEVAL_COLUMN = "embedding_4096"

BROWSE_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZKC 检索与复利产物</title>
<style>
  :root { color-scheme: light; }
  body { font-family: system-ui, -apple-system, "PingFang SC", sans-serif; max-width: 880px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fafafa; }
  h1 { font-size: 1.4rem; }
  .tabs { display: flex; gap: .5rem; margin: 1rem 0; }
  .tabs button { padding: .4rem 1rem; font: inherit; cursor: pointer; border: 1px solid #d4d4d8; background: #fff; border-radius: 6px; }
  .tabs button.on { background: #4338ca; color: #fff; border-color: #4338ca; }
  form.inline { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-bottom: 1rem; }
  form.inline input, form.inline select { padding: .35rem .5rem; font: inherit; border: 1px solid #d4d4d8; border-radius: 6px; }
  form.inline input.q { flex: 1; min-width: 200px; }
  .hit { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: .7rem .9rem; margin-bottom: .5rem; }
  .hit .t { font-weight: 600; }
  .hit .meta { font-size: .75rem; color: #888; margin-top: .15rem; }
  .badge { display: inline-block; font-size: .68rem; padding: .05rem .45rem; border-radius: 999px; margin-left: .4rem; vertical-align: middle; }
  .b-structured { background: #eef2ff; color: #4338ca; }
  .b-embedding { background: #fef3c7; color: #b45309; }
  .b-dynamic { background: #ecfdf5; color: #047857; }
  .b-static { background: #f4f4f5; color: #52525b; }
  .b-unrouted { background: #fff7ed; color: #c2410c; }
  .degraded { color: #b45309; font-size: .8rem; margin: .4rem 0; }
  .claim .st { font-size: .7rem; color: #0369a1; margin-left: .4rem; }
  .ev { font-size: .75rem; color: #666; margin-top: .2rem; }
  p.hint { color: #666; font-size: .9rem; }
  a { color: #4338ca; }
</style>
</head>
<body>
<h1>ZKC · 检索与复利产物</h1>
<p class="hint">检索：结构化过滤为主（R18），文本经 4096d 语义模型候选召回（仅候选+人确认；768d nomic 列保留备用）。产物：蒸馏 claim / 结合 artifact 及其来源反查。</p>
<div class="tabs">
  <button id="tab-s" class="on" onclick="show('s')">检索</button>
  <button id="tab-p" onclick="show('p')">复利产物</button>
</div>

<div id="pane-s">
  <form class="inline" onsubmit="doSearch(event)">
    <input class="q" id="q" placeholder="关键词（可选；输入后同时触发候选召回）">
    <select id="track">
      <option value="">全部轨道</option>
      <option value="dynamic">动态</option>
      <option value="static">静态</option>
      <option value="unrouted">未定轨</option>
    </select>
    <input id="dmin" type="number" min="0" max="1" step="0.05" style="width:90px" placeholder="decay≥">
    <input id="dmax" type="number" min="0" max="1" step="0.05" style="width:90px" placeholder="decay≤">
    <label style="font-size:.8rem"><input type="checkbox" id="arch"> 含归档</label>
    <button type="submit">检索</button>
  </form>
  <div id="degraded" class="degraded"></div>
  <div id="hits"></div>
</div>

<div id="pane-p" style="display:none">
  <h3 style="margin:.4rem 0">元认知 claim（蒸馏产物）</h3>
  <div id="claims"></div>
  <h3 style="margin:1rem 0 .4rem">建模/方法论 artifact（结合产物）</h3>
  <div id="arts"></div>
</div>

<p style="margin-top:1.5rem;">
  <a href="/review">每日复审队列</a> · <a href="/metrics">复利度量面板</a> · <a href="/">快捕获</a>
</p>

<script>
function show(t) {
  document.getElementById('pane-s').style.display = t==='s' ? '' : 'none';
  document.getElementById('pane-p').style.display = t==='p' ? '' : 'none';
  document.getElementById('tab-s').className = t==='s' ? 'on' : '';
  document.getElementById('tab-p').className = t==='p' ? 'on' : '';
  if (t==='p') loadProducts();
}
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function badge(track) { return `<span class="badge b-${esc(track)}">${esc(track)}</span>`; }

async function doSearch(e) {
  e.preventDefault();
  const p = new URLSearchParams();
  const q = document.getElementById('q').value.trim();
  if (q) p.set('q', q);
  const tr = document.getElementById('track').value;
  if (tr) p.set('track', tr);
  const dmin = document.getElementById('dmin').value;
  if (dmin !== '') p.set('decay_min', dmin);
  const dmax = document.getElementById('dmax').value;
  if (dmax !== '') p.set('decay_max', dmax);
  if (document.getElementById('arch').checked) p.set('include_archived', 'true');
  const r = await fetch('/browse/api?' + p.toString());
  const j = await r.json();
  document.getElementById('degraded').textContent = j.degraded
    ? '⚠ 候选召回降级（encoder 不可用），仅结构化结果：' + j.degrade_reason : '';
  const html = j.hits.map(h => `
    <div class="hit">
      <div class="t">${esc(h.title)} ${badge(h.track)}
        ${h.source === 'embedding' ? `<span class="badge b-embedding">候选 ${Math.round(h.sim*1000)/10}%</span>` : ''}
      </div>
      <div class="meta">decay ${h.decay}${h.archived ? ' · 已归档' : ''} · ${esc(h.snippet || '')}</div>
    </div>`).join('');
  document.getElementById('hits').innerHTML =
    html || '<div class="hit">无命中。试着放宽过滤，或只留关键词触发候选召回。</div>';
}

async function loadProducts() {
  const r = await fetch('/browse/artifacts/api');
  const j = await r.json();
  document.getElementById('claims').innerHTML = j.claims.map(c => `
    <div class="hit claim">
      <div class="t">${esc(c.statement)}<span class="st">忠实度:${esc(c.faithfulness_status || '未判')} · 引用:${c.citation_count}</span></div>
      <div class="ev">来源: ${c.evidence.map(e => esc(e.title)).join(' / ') || '（无来源记录）'}</div>
    </div>`).join('') || '<div class="hit">暂无 claim（先在复审流里蒸馏）</div>';
  document.getElementById('arts').innerHTML = j.artifacts.map(a => `
    <div class="hit">
      <div class="t">${esc(a.title)} <span class="st" style="font-size:.7rem;color:#0369a1;margin-left:.4rem">${esc(a.kind)}</span></div>
      <div class="ev">来源: ${a.evidence.map(e => esc(e.title)).join(' / ') || '（无来源记录）'}</div>
    </div>`).join('') || '<div class="hit">暂无 artifact（先运行结合算子）</div>';
}
</script>
</body>
</html>
"""


def search_payload(
    store,
    *,
    q: Optional[str] = None,
    track: Optional[str] = None,
    decay_min: Optional[float] = None,
    decay_max: Optional[float] = None,
    include_archived: bool = False,
    limit: int = 50,
    encoder=None,
    k: int = 10,
    column: str = RETRIEVAL_COLUMN,
) -> dict:
    """检索 → JSON 友好 payload（SSR 页与测试共用）。"""
    r = S.search(
        store, q=q, track=track, decay_min=decay_min, decay_max=decay_max,
        include_archived=include_archived, limit=limit, encoder=encoder, k=k,
        column=column,
    )
    hits = []
    for h in r["hits"]:
        snippet = (h.node.content or "")[:80]
        hits.append({
            "id": str(h.node.id),
            "title": h.node.title,
            "track": h.node.track,
            "decay": round(h.node.decay_score or 0.0, 3),
            "archived": h.node.archived_at is not None,
            "snippet": snippet,
            "source": h.source,
            "sim": (round(h.sim, 4) if h.sim is not None else None),
        })
    return {
        "hits": hits,
        "structured_count": r["structured_count"],
        "embedding_count": r["embedding_count"],
        "degraded": r["degraded"],
        "degrade_reason": r["degrade_reason"],
    }


def artifacts_payload(store, *, limit: int = 100) -> dict:
    """复利产物浏览 payload：claims/artifacts + evidence 反查 + citation 计数。"""
    cits = store.citation_counts()

    def _evidence(refs):
        out = []
        for rid in refs:
            n = store.nodes.get(rid)
            out.append({"id": str(rid), "title": n.title if n else "(已删除)"})
        return out

    claims = [{
        "id": str(c.id),
        "statement": c.statement,
        "level": c.level,
        "faithfulness_status": c.faithfulness_status,
        "citation_count": cits.get(c.id, 0),
        "evidence": _evidence(c.evidence_refs),
    } for c in store.claims.list_all(limit=limit)]
    artifacts = [{
        "id": str(a.id),
        "title": a.title,
        "kind": a.kind,
        "evidence": _evidence(a.evidence_refs),
    } for a in store.artifacts.list_all(limit=limit)]
    return {"claims": claims, "artifacts": artifacts}


def register_browse_routes(app, store, encoder=None) -> None:
    """挂载 /browse。encoder 缺省用 4096 编码器（qwen3，q 非空时才触发调用）。"""
    router = APIRouter()
    enc = encoder if encoder is not None else make_encoder_4096()

    @router.get("/browse", response_class=HTMLResponse)
    def browse_page() -> HTMLResponse:
        return HTMLResponse(BROWSE_HTML)

    @router.get("/browse/api")
    def browse_api(
        q: Optional[str] = None,
        track: Optional[str] = None,
        decay_min: Optional[float] = None,
        decay_max: Optional[float] = None,
        include_archived: bool = False,
        limit: int = 50,
    ) -> dict:
        return search_payload(
            store, q=q, track=track, decay_min=decay_min, decay_max=decay_max,
            include_archived=include_archived, limit=limit, encoder=enc,
        )

    @router.get("/browse/artifacts/api")
    def artifacts_api() -> dict:
        return artifacts_payload(store)

    app.include_router(router)

"""ZKC · 本地 web 捕获层（P2.1，遵循 ADR-0001：FastAPI + SSR，localhost:8000）。

本模块是 P2.1 的落地：极简捕获页 + POST /capture，直接复用已存在的
`zkc.ingest.ingest_with_routing`（P2.2/P2.3 已落地）。

离线优先由路由引擎的 health() 自动降级保证；另提供 ZKC_LLM_ENABLED 开关做显式离线。
P4.2 每日复审队列 UI 将复用同一 FastAPI 骨架（create_app 返回 app 可继续挂路由）。

依赖：fastapi / uvicorn（运行）；httpx（仅 TestClient 测试，可选）。
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from zkc import routing
from zkc.ingest import ingest_with_routing
from zkc.routing import (
    DEFAULT_LEXICAL_CORPUS_PATH,
    DecisionRouter,
    LexicalRouter,
    OllamaClient,
)
from zkc.repository import get_storage

CAPTURE_HTML = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZKC 快捕获</title>
<style>
  body { font-family: system-ui, -apple-system, "PingFang SC", sans-serif; max-width: 680px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
  h1 { font-size: 1.4rem; }
  p.hint { color: #666; font-size: .9rem; }
  textarea { width: 100%; height: 160px; font: inherit; padding: .6rem; box-sizing: border-box; }
  button { margin-top: .6rem; padding: .5rem 1.2rem; font: inherit; cursor: pointer; }
  pre { background: #f4f4f5; padding: 1rem; white-space: pre-wrap; word-break: break-all; border-radius: 6px; }
  .vague { color: #b45309; }
</style>
</head>
<body>
<h1>ZKC · 快捕获</h1>
<p class="hint">粘贴一条想法 / 项目笔记。第一行作为标题，其余作为正文。系统自动分流（静态 / 动态）或转人工定轨。</p>
<form id="f">
  <textarea id="note" name="note" placeholder="例如：&#10;明天要开会讨论需求&#10;准备 Q3 路线图材料"></textarea>
  <br>
  <button type="submit">捕获</button>
</form>
<h3>结果</h3>
<pre id="out">（提交后显示分流结果）</pre>
<script>
  const f = document.getElementById('f');
  const out = document.getElementById('out');
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const note = document.getElementById('note').value;
    try {
      const r = await fetch('/capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'note=' + encodeURIComponent(note),
      });
      const j = await r.json();
      if (j.vague) out.classList.add('vague'); else out.classList.remove('vague');
      out.textContent = JSON.stringify(j, null, 2);
    } catch (err) {
      out.textContent = '提交失败：' + err;
    }
  });
</script>
</body>
</html>
"""


def build_routers(
    lexical_corpus_path: Optional[str] = None,
) -> tuple[DecisionRouter, Optional[LexicalRouter]]:
    """构造双信号路由引擎（真实环境）。

    词法语料存在则 fit 进 LexicalRouter；不存在则返回 None（路由引擎退化为 LLM 单信号提交，
    由 ROUTING_REQUIRE_DUAL_SIGNAL 的「无词法交叉验证」分支兜底）。
    """
    client = OllamaClient()
    dr = DecisionRouter(client)
    lr: Optional[LexicalRouter] = None
    path = lexical_corpus_path or os.environ.get("ZKC_LEXICAL_CORPUS", DEFAULT_LEXICAL_CORPUS_PATH)
    if path:
        examples = routing.load_lexical_corpus(path)
        if examples:
            lr = LexicalRouter()
            lr.fit(examples)
    return dr, lr


def capture_note(
    note: str,
    *,
    store,
    decision_router: DecisionRouter,
    lexical_router: Optional[LexicalRouter] = None,
    llm_available: bool = True,
) -> dict:
    """捕获一条笔记：拆分标题/正文 → 调 ingest_with_routing → 返回分流结果摘要。

    纯函数（无 HTTP 依赖），便于脱离 web 栈单测。标题取首行，正文取余下内容。
    """
    note = (note or "").strip()
    if not note:
        raise ValueError("note 不能为空")
    parts = note.split("\n", 1)
    title = parts[0].strip() or note[:40]
    content = parts[1].strip() if len(parts) > 1 else None
    node, res = ingest_with_routing(
        title=title,
        content=content,
        text_for_routing=note,
        decision_router=decision_router,
        lexical_router=lexical_router,
        llm_available=llm_available,
        store=store,
    )
    return {
        "node_id": str(node.id),
        "track": res.track,
        "confidence": res.confidence,
        "vague": res.track == routing.VAGUE,
        "source": res.source,
        "aborted": res.aborted,
        "llm_track": res.llm_track,
        "lexical_track": res.lexical_track,
    }


def create_app(
    *,
    store=None,
    decision_router: Optional[DecisionRouter] = None,
    lexical_router: Optional[LexicalRouter] = None,
    llm_available: Optional[bool] = None,
    lexical_corpus_path: Optional[str] = None,
) -> FastAPI:
    """构造 FastAPI app。

    测试可注入 decision_router / lexical_router / store 以脱离 Ollama / PG。
    未注入时走 build_routers()（真实环境：Ollama + 可选词法语料）。
    """
    if decision_router is None or lexical_router is None:
        built_dr, built_lr = build_routers(lexical_corpus_path)
        decision_router = decision_router or built_dr
        lexical_router = lexical_router or built_lr

    llm_on = llm_available if llm_available is not None else (
        os.environ.get("ZKC_LLM_ENABLED", "1") != "0"
    )

    app = FastAPI(title="ZKC 快捕获")

    @app.get("/", response_class=HTMLResponse)
    def capture_page() -> HTMLResponse:
        return HTMLResponse(CAPTURE_HTML)

    @app.post("/capture")
    def capture(note: str = Form(...)) -> dict:
        store_ = store or get_storage()
        return capture_note(
            note,
            store=store_,
            decision_router=decision_router,
            lexical_router=lexical_router,
            llm_available=llm_on,
        )

    return app

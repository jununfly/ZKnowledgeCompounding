"""LangGraph distillation loop with human-in-the-loop interrupt/resume.

Pipeline: extract (Instructor+Ollama) -> review (interrupt) -> persist (PG).
Checkpointer: PostgresSaver on the SAME database as the domain schema.
"""
import json
from typing import Any, TypedDict

import instructor
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from openai import OpenAI
from pydantic import ValidationError

import store as store_module
from models import ClaimDraft
from store import connect, persist_distill

OLLAMA_BASE = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen2.5-coder:1.5b"

_client = instructor.from_openai(
    OpenAI(base_url=OLLAMA_BASE, api_key="ollama"),
    mode=instructor.Mode.JSON,
)


class DistillState(TypedDict):
    source_ids: list[str]
    sources: list[dict]          # [{id,title,content}]
    draft: dict | None           # ClaimDraft.model_dump() after extract
    review: dict | None          # human payload after resume {approved, edits?}
    claim_id: str | None
    transform_id: str | None
    error: str | None


def _extract_prompt(sources: list[dict]) -> str:
    joined = "\n\n".join(f"[{s['title']}]\n{s['content']}" for s in sources)
    return (
        "从以下条目中蒸馏出一条元认知 claim（原理/模式/反模式/权衡），"
        "必须超越原文形成更高一层的认知，不要复述内容。\n\n" + joined
    )


def extract(state: DistillState) -> dict:
    """Instructor + Ollama: text -> validated ClaimDraft (auto retry on invalid)."""
    try:
        draft = _client.chat.completions.create(
            model=OLLAMA_MODEL,
            response_model=ClaimDraft,
            messages=[{"role": "user", "content": _extract_prompt(state["sources"])}],
            temperature=0.2,
        )
        return {"draft": json.loads(draft.model_dump_json()), "error": None}
    except (ValidationError, Exception) as e:  # noqa: BLE001 - spike: surface to state
        return {"error": f"extract failed: {e}"}


def review(state: DistillState) -> dict:
    """Human-in-the-loop: pause until a reviewer resumes with a decision payload."""
    human = interrupt({"draft": state["draft"]})
    return {"review": human if isinstance(human, dict) else {"approved": bool(human)}}


def persist(state: DistillState) -> dict:
    """Approved claim lands in PG with produced_by provenance (constraint 2)."""
    if not (state.get("review") or {}).get("approved"):
        return {"error": "rejected by reviewer"}
    final = dict(state["draft"] or {})
    edits = state["review"].get("edits") or {}
    final.update(edits)
    with connect() as conn, conn.cursor() as cur:
        t_id, c_id = persist_distill(cur, state["source_ids"], final)
    return {"claim_id": c_id, "transform_id": t_id}


def build_graph():
    g = StateGraph(DistillState)
    g.add_node("extract", extract)
    g.add_node("review", review)
    g.add_node("persist", persist)
    g.add_edge(START, "extract")
    g.add_edge("extract", "review")
    g.add_edge("review", "persist")
    g.add_edge("persist", END)
    return g.compile(checkpointer=None)  # checkpointer injected in run()


def distill_graph():
    """Context manager: graph with a PostgresSaver on the same DB (setup idempotent).

    The checkpoint connection lives as long as the context — resume must happen
    inside the block (that's exactly what proves PG-resident checkpoints).
    """
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        with PostgresSaver.from_conn_string(store_module.DSN) as cp:
            cp.setup()
            g = StateGraph(DistillState)
            g.add_node("extract", extract)
            g.add_node("review", review)
            g.add_node("persist", persist)
            g.add_edge(START, "extract")
            g.add_edge("extract", "review")
            g.add_edge("review", "persist")
            g.add_edge("persist", END)
            yield g.compile(checkpointer=cp)

    return _ctx()


def start_distill(graph, thread_id: str, sources: list[dict]) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(
        {
            "source_ids": [s["id"] for s in sources],
            "sources": sources,
            "draft": None, "review": None, "claim_id": None,
            "transform_id": None, "error": None,
        },
        cfg,
    )


def resume_distill(graph, thread_id: str, decision: dict) -> dict[str, Any]:
    cfg = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(Command(resume=decision), cfg)

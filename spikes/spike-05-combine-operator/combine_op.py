"""Combine operator (T3.2): explicit program — RCS funnel + dual-layer merge.

PaperQA2's RCS pattern: per-source query-conditioned summary -> LLM re-rank ->
source cap -> single generation. LightRAG's dual layer: local (entity-level) +
global (cross-source relations). Output: Instructor-constrained, citation-bound
ModelingArtifact — never free text.

LLM functions are injectable so tests can run the funnel mechanics with stubs.
"""
import instructor
from openai import OpenAI
from pydantic import BaseModel as _PB
from pydantic import Field

from models import ModelingArtifact

OLLAMA_BASE = "http://localhost:11434/v1"
OLLAMA_MODEL = "qwen2.5-coder:1.5b"

_instructor_client = instructor.from_openai(
    OpenAI(base_url=OLLAMA_BASE, api_key="ollama"),
    mode=instructor.Mode.JSON,
)


class _SummaryOut(_PB):
    """单条来源、面向问题的要点总结。"""
    point: str = Field(description="一句与问题相关的要点，不超过 60 字")


class _ScoreOut(_PB):
    score: float = Field(ge=0.0, le=1.0)


def _summarize(source: dict, query: str) -> str:
    resp = _instructor_client.chat.completions.create(
        model=OLLAMA_MODEL,
        response_model=_SummaryOut,
        messages=[{"role": "user", "content": (
            f"针对问题「{query}」，只依据下面这条来源，给出一句与该问题相关的要点总结"
            f"（不要复述全文，不超过 60 字）。\n\n[{source['title']}]\n{source['content']}"
        )}],
        temperature=0.2,
    )
    return resp.point


def _score(summary: str, query: str) -> float:
    resp = _instructor_client.chat.completions.create(
        model=OLLAMA_MODEL,
        response_model=_ScoreOut,
        messages=[{"role": "user", "content": (
            f"问题：「{query}」。以下总结对该问题的支撑度打分 0~1（只输出分数对象）。\n\n{summary}"
        )}],
        temperature=0.0,
    )
    return resp.score


def _generate(prompt: str) -> ModelingArtifact:
    return _instructor_client.chat.completions.create(
        model=OLLAMA_MODEL,
        response_model=ModelingArtifact,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )


# ---------------------------------------------------------------- citation enforcement
def enforce_citations(artifact: dict, source_ids: set[str]) -> dict:
    """Drop hallucinated citations, then claims left with zero evidence.

    Returns the repaired artifact. Raises ValueError if no claim survives —
    a modeling product without valid citations must not exist.
    """
    kept_claims = []
    dropped = 0
    for claim in artifact.get("claims", []):
        valid = [e for e in claim.get("evidence_ids", []) if e in source_ids]
        if not valid:
            dropped += 1
            continue
        claim = dict(claim, evidence_ids=valid)
        kept_claims.append(claim)
    if not kept_claims:
        raise ValueError(
            f"artifact rejected: all {dropped + len(artifact.get('claims', [])) - dropped}"
            f"~0 claims lost their citations (hallucinated provenance)"
        )
    artifact = dict(artifact, claims=kept_claims,
                    evidence_refs=sorted({e for c in kept_claims for e in c["evidence_ids"]}))
    artifact["_dropped_claims"] = dropped
    return artifact


# ---------------------------------------------------------------- the operator
class CombineOperator:
    """RCS funnel + dual-layer merge -> cited structured artifact."""

    def __init__(self, summarize=None, score=None, generate=None, max_sources: int = 4):
        self._summarize = summarize or _summarize
        self._score = score or _score
        self._generate = generate or _generate
        self.max_sources = max_sources

    def _funnel(self, query: str, sources: list[dict]) -> tuple[list[dict], list[dict]]:
        """Per-source query-conditioned summary -> score -> cap. Returns (kept, dropped)."""
        scored = []
        for src in sources:
            summary = self._summarize(src, query)
            s = self._score(summary, query)
            scored.append({"source": src, "summary": summary, "score": s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: self.max_sources], scored[self.max_sources:]

    def _build_prompt(self, query: str, kept: list[dict]) -> str:
        local = "\n".join(
            f"- [{k['source']['id'][:8]}] {k['source']['title']}（支撑度 {k['score']:.2f}）：{k['summary']}"
            for k in kept
        )
        ids = ", ".join(k["source"]["id"] for k in kept)
        return (
            f"问题：「{query}」\n\n"
            f"以下是经漏斗筛选的来源要点（local 层），请把它们结合成一个**更高一层的建模产物**"
            f"（方法论/心智模型/权衡图），不要摘要堆砌：\n{local}\n\n"
            f"要求：\n"
            f"1. 每条断言必须引用支撑它的来源 id，只能从这些 id 中选：{ids}\n"
            f"2. global 层写跨来源的关系/模式，而非任何单条来源的复述\n"
            f"3. kind=methodology 时给出可执行步骤\n"
            f"4. 使用证据 id（完整 id）标注 evidence_ids"
        )

    def combine(self, query: str, sources: list[dict]) -> dict:
        """Returns {artifact, report}. Raises ValueError if citations collapse."""
        kept, dropped = self._funnel(query, sources)
        source_ids = {s["id"] for s in sources}
        kept_ids = [k["source"]["id"] for k in kept]

        raw = self._generate(self._build_prompt(query, kept))
        artifact = enforce_citations(raw.model_dump(by_alias=True), source_ids)

        return {
            "artifact": artifact,
            "report": {
                "query": query,
                "kept": [{"id": k["source"]["id"], "title": k["source"]["title"],
                          "summary": k["summary"], "score": k["score"]} for k in kept],
                "dropped": [{"id": k["source"]["id"], "title": k["source"]["title"],
                             "score": k["score"]} for k in dropped],
                "kept_ids": kept_ids,
                "quality": {
                    "local_empty": not artifact.get("local"),
                    "global_empty": not artifact.get("global_insights"),
                    "dropped_claims": artifact.get("_dropped_claims", 0),
                },
            },
        }

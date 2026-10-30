"""Spike 11: cross-source assertion enforcement operator.

Addresses the open item from spike 10: the combine operator's cross-source
synthesis fails NOT because of model size, but because the prompt only *softly*
asks for a "global layer" — small models emit one-claim-per-source and never
actually synthesize across sources. This operator enforces >= min_cross_source
cross-source claims at the OPERATOR layer, not by hoping the model complies:

  1. PROMPT LAYER: the main generation prompt HARD-requires >= min_cross_source
     cross-source claims (each citing >= 2 distinct source ids), and asks for the
     specific relationship between them (reinforce / conflict / complement /
     common pattern).
  2. OPERATOR LOOP: after the main generation, count cross-source claims. If the
     floor is not met, fire ONE bounded cross-source completion call that asks the
     model to emit exactly the missing cross-source claims against the kept
     sources, then merge them in (and re-run citation enforcement). No infinite
     loop — a single completion, then accept whatever survived enforcement.

The artifact schema is UNCHANGED (spike 05 ModelingArtifact). The enforcement is
purely operator/prompt level, which is the whole point: it is fixable without a
bigger model.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPIKES = _HERE.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Reuse the AUTHORITATIVE schema + citation enforcement from spike 05 (no copy drift).
# Register `models` BEFORE loading combine_op.py — it does `from models import ...`.
artifact_models = _load("s11_s05_models", _SPIKES / "spike-05-combine-operator" / "models.py")
sys.modules.setdefault("models", artifact_models)
combine_mod = _load("s11_s05_op", _SPIKES / "spike-05-combine-operator" / "combine_op.py")

ModelingArtifact = artifact_models.ModelingArtifact
enforce_citations = combine_mod.enforce_citations


# ------------------------------------------------------------------ the operator
class CrossSourceCombineOperator:
    """RCS funnel + dual-layer merge + HARD cross-source enforcement.

    Injection contract (so tests run with stubs):
      summarize(src, query) -> str
      score(summary, query) -> float
      generate(prompt)      -> ModelingArtifact (or attr-equivalent)
      complete(query, kept, existing_claims, need) -> obj|dict with .claims / ["claims"]
    """

    def __init__(self, summarize, score, generate, complete=None,
                 max_sources: int = 4, min_cross_source: int = 2,
                 complete_on_shortfall: bool = True):
        self._summarize = summarize
        self._score = score
        self._generate = generate
        self._complete = complete
        self.max_sources = max_sources
        self.min_cross_source = min_cross_source
        self.complete_on_shortfall = complete_on_shortfall

    # ---- funnel (identical mechanics to spike 05) ----
    def _funnel(self, query: str, sources: list[dict]) -> tuple[list[dict], list[dict]]:
        scored = []
        for src in sources:
            summary = self._summarize(src, query)
            s = self._score(summary, query)
            scored.append({"source": src, "summary": summary, "score": s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: self.max_sources], scored[self.max_sources:]

    # ---- prompts ----
    def _build_prompt(self, query: str, kept: list[dict], min_cs: int) -> str:
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
            f"3. 【硬约束】claims 中必须至少包含 {min_cs} 条**跨源综合断言**——"
            f"每条 evidence_ids 含「>=2 个不同来源 id」，并明确说明这些来源之间是"
            f"相互印证 / 冲突 / 互补 / 还是共同指向某个更高维模式\n"
            f"4. kind=methodology 时给出可执行步骤\n"
            f"5. 使用证据 id（完整 id）标注 evidence_ids"
        )

    def _build_complete_prompt(self, query: str, kept: list[dict],
                               existing: list[dict], need: int, ids: str) -> str:
        local = "\n".join(
            f"- [{k['source']['id'][:8]}] {k['source']['title']}：{k['summary']}" for k in kept
        )
        exist_txt = "\n".join(
            f"- {c.get('statement', '')}（引 {c.get('evidence_ids', [])}）" for c in existing
        ) or "（无）"
        return (
            f"问题：「{query}」\n\n来源要点：\n{local}\n\n"
            f"已有断言（不要重复，仅用于避免重叠）：\n{exist_txt}\n\n"
            f"请补充至少 {need} 条【跨源综合断言】：\n"
            f"- 每条必须引用 >=2 个不同来源 id，只能从 {ids} 中选；\n"
            f"- 说明这些来源之间的关系（相互印证 / 冲突 / 互补 / 共同指向某模式）；\n"
            f"- 字段：statement / level / confidence / evidence_ids（完整 id）。"
        )

    # ---- default completion uses the same generate injection ----
    def _default_complete(self, query, kept, existing_claims, need):
        ids = ", ".join(k["source"]["id"] for k in kept)
        prompt = self._build_complete_prompt(query, kept, existing_claims, need, ids)
        return self._generate(prompt)

    @staticmethod
    def _normalize_claims(extra) -> list[dict]:
        raw = extra.get("claims", []) if isinstance(extra, dict) else getattr(extra, "claims", [])
        out = []
        for c in raw:
            cc = c if isinstance(c, dict) else c.model_dump(by_alias=True)
            if len(cc.get("evidence_ids", [])) >= 2:   # only keep genuine cross-source
                out.append(cc)
        return out

    # ---- entry point ----
    def combine(self, query: str, sources: list[dict]) -> dict:
        kept, dropped = self._funnel(query, sources)
        source_ids = {s["id"] for s in sources}
        kept_ids = [k["source"]["id"] for k in kept]

        raw = self._generate(self._build_prompt(query, kept, self.min_cross_source))
        artifact = enforce_citations(raw.model_dump(by_alias=True), source_ids)

        n_cross = sum(1 for c in artifact["claims"] if len(c.get("evidence_ids", [])) >= 2)
        completion_fired = False
        # Use the explicitly injected completion hook if given; otherwise fall back to
        # the operator's own default (same generate injection). A single bounded call.
        hook = self._complete or (self._default_complete if self.complete_on_shortfall else None)
        if self.complete_on_shortfall and n_cross < self.min_cross_source and hook is not None:
            completion_fired = True
            need = self.min_cross_source - n_cross
            extra = hook(query, kept, artifact["claims"], need)
            normalized = self._normalize_claims(extra)
            if normalized:
                merged = dict(artifact, claims=artifact["claims"] + normalized)
                try:
                    artifact = enforce_citations(merged, source_ids)
                except ValueError:
                    # completion claims all collapsed under enforcement -> keep main
                    pass

        final_n_cross = sum(1 for c in artifact["claims"] if len(c.get("evidence_ids", [])) >= 2)
        return {
            "artifact": artifact,
            "report": {
                "query": query,
                "kept": [{"id": k["source"]["id"], "title": k["source"]["title"],
                          "summary": k["summary"], "score": k["score"]} for k in kept],
                "dropped": [{"id": k["source"]["id"], "title": k["source"]["title"],
                             "score": k["score"]} for k in dropped],
                "kept_ids": kept_ids,
                "completion_fired": completion_fired,
                "n_cross_source_final": final_n_cross,
                "min_cross_source": self.min_cross_source,
                "quality": {
                    "local_empty": not artifact.get("local"),
                    "global_empty": not (artifact.get("global") or artifact.get("global_insights")),
                    "dropped_claims": artifact.get("_dropped_claims", 0),
                },
            },
        }

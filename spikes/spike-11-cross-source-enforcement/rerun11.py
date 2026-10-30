"""Spike 11 re-run harness: the NEW cross-source-enforced operator, same corpus + rubric.

Everything except the OPERATOR layer is held constant vs spike 10:
  - identical frozen corpus (spike 10 corpus.py)
  - identical rubric (spike 10 quality_rubric.py)
  - identical client / policy / num_ctx
The ONLY change is CombineOperator -> CrossSourceCombineOperator
(prompt hard-constraint >=2 cross-source claims + one bounded completion loop).
This isolates "did the operator/prompt fix solve cross-source synthesis" from
"is it just a bigger model".
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import instructor
from openai import OpenAI

_HERE = Path(__file__).resolve().parent
_SPIKES = _HERE.parent

OLLAMA_BASE = "http://localhost:11434/v1"
ITER_MODEL = "qwen3.5:4b-mlx"
BASELINE_MODEL = "qwen2.5-coder:1.5b"
NUM_CTX = 8192
EXTRA_BODY = {"think": False, "options": {"num_ctx": NUM_CTX}}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


corpus = _load("s11_corpus", _SPIKES / "spike-10-model-quality" / "corpus.py")
rubric = _load("s11_rubric", _SPIKES / "spike-10-model-quality" / "quality_rubric.py")
# llm_client uses @dataclass at module top; importlib loading trips a dataclass
# module-resolution bug (sys.modules lookup returns None). Load it via sys.path.
_S10 = _SPIKES / "spike-10-model-quality"
if str(_S10) not in sys.path:
    sys.path.insert(0, str(_S10))
import llm_client as llm_client_mod  # noqa: E402  (loaded after sys.path patch)
resilient_create = llm_client_mod.resilient_create
op_mod = _load("s11_op", _HERE / "cross_source_op.py")

CrossSourceCombineOperator = op_mod.CrossSourceCombineOperator
ModelingArtifact = op_mod.ModelingArtifact


def make_client(mode: str = "json"):
    return instructor.from_openai(
        OpenAI(base_url=OLLAMA_BASE, api_key="ollama"),
        mode=instructor.Mode.JSON if mode == "json" else instructor.Mode.TOOLS,
    )


def run_combine11(client, model: str, query: str, sources: list[dict],
                  min_cross_source: int = 2) -> dict:
    def _gen(prompt: str):
        obj, _ = resilient_create(
            client, model, ModelingArtifact, prompt, temperature=0.2,
            max_attempts=3, extra_body=EXTRA_BODY,
        )
        return obj

    def _sum(src: dict, q: str):
        body = (f"针对问题「{q}」，只依据下面这条来源，给出一句与该问题相关的要点总结"
                f"（不要复述全文，不超过 60 字）。\n\n[{src['title']}]\n{src['content']}")
        out, _ = resilient_create(client, model, op_mod.combine_mod._SummaryOut, body,
                                  temperature=0.2, max_attempts=2, extra_body=EXTRA_BODY)
        return out.point

    def _score(summary: str, q: str):
        body = (f"问题：「{q}」。以下总结对该问题的支撑度打分 0~1（只输出分数对象）。"
                f"\n\n{summary}")
        out, _ = resilient_create(client, model, op_mod.combine_mod._ScoreOut, body,
                                  temperature=0.0, max_attempts=2, extra_body=EXTRA_BODY)
        return out.score

    op = CrossSourceCombineOperator(
        summarize=_sum, score=_score, generate=_gen,
        max_sources=4, min_cross_source=min_cross_source,
    )
    try:
        out = op.combine(query, sources)
    except ValueError as e:
        return {"error": str(e)}

    art = out["artifact"]
    scores = rubric.score_artifact(art, sources)
    return {
        "artifact": art,
        "report": out["report"],
        "scores": scores,
        "verdict": rubric.verdict(scores, "artifact"),
    }


if __name__ == "__main__":
    client = make_client("json")
    r = run_combine11(client, ITER_MODEL, corpus.QUERY, corpus.SOURCES)
    import json
    print(json.dumps(r["scores"], ensure_ascii=False, indent=2, default=str))
    print("verdict:", r["verdict"]["all_pass"], r["verdict"]["checks"])
    print("completion_fired:", r["report"]["completion_fired"],
          "n_cross_final:", r["report"]["n_cross_source_final"])

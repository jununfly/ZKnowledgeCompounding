"""Spike 10 re-run: same pipeline, three arms, rubric-scored.

ARMS (the whole point is attribution, not just "try the new model"):
  A  baseline  : 1.5B + Instructor's built-in retry  (reproduces spike 04/05)
  B  policy    : 1.5B + the fixed retry policy       (isolates the RETRY fix)
  C  model     : 9B   + the fixed retry policy       (isolates the MODEL change)

Without B, any improvement in C would be ambiguous: it could be the model, or it could
be the retry fix that C also benefits from. That is exactly the attribution mistake we
refused to make when choosing the model earlier.

Everything else is held constant: identical corpus, identical prompts, identical
schemas, identical rubric.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import instructor
from openai import OpenAI

from llm_client import resilient_create
from quality_rubric import score_artifact, score_claim, verdict

_HERE = Path(__file__).resolve().parent
_SPIKES = _HERE.parent
OLLAMA_BASE = "http://localhost:11434/v1"

BASELINE_MODEL = "qwen2.5-coder:1.5b"
TARGET_MODEL = "qwen3.5:9b-mlx"     # capability ceiling (too slow to iterate on 16 GB)
ITER_MODEL = "qwen3.5:4b-mlx"       # practical iteration carrier
# MEASURED on this 16 GB box: at num_ctx 16384 the mlx runner grew to ~12 GB resident
# and the machine swapped (20.2 GB of 21.5 GB swap used, 9% free) — inference crawled.
# 8192 keeps residency near the 9.4 GB baseline and is far more than this corpus needs.
NUM_CTX = 8192

# MUST be sent on every call. Ollama loads Qwen3.5 with its native 256K context by
# default, and on a 16 GB machine that alone pushes residency to ~15 GB (measured:
# 9.4 GB at num_ctx 16384 vs 15 GB at 256K). `think` is off by default on the MLX
# runner but is pinned explicitly rather than relied upon.
EXTRA_BODY = {"think": False, "options": {"num_ctx": NUM_CTX}}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


claim_models = _load("s04_models", _SPIKES / "spike-04-distill-loop" / "models.py")
artifact_models = _load("s05_models", _SPIKES / "spike-05-combine-operator" / "models.py")
# combine_op.py does `from models import ModelingArtifact`. Pre-register OUR loaded copy
# under that name so it resolves to the very same class object — otherwise two distinct
# copies of the schema would exist and the comparison would silently drift.
sys.modules.setdefault("models", artifact_models)
combine_mod = _load("s05_op", _SPIKES / "spike-05-combine-operator" / "combine_op.py")

ClaimDraft = claim_models.ClaimDraft
ModelingArtifact = artifact_models.ModelingArtifact
CombineOperator = combine_mod.CombineOperator


def make_client(mode: str = "json"):
    if mode == "tools":
        return instructor.from_openai(
            OpenAI(base_url=OLLAMA_BASE, api_key="ollama"),
            mode=instructor.Mode.TOOLS,
        )
    return instructor.from_openai(
        OpenAI(base_url=OLLAMA_BASE, api_key="ollama"),
        mode=instructor.Mode.JSON,
    )


# --- prompts copied verbatim from the original spikes so inputs are byte-identical ----
def distill_prompt(sources: list[dict]) -> str:
    joined = "\n\n".join(f"[{s['title']}]\n{s['content']}" for s in sources)
    return (
        "从以下条目中蒸馏出一条元认知 claim（原理/模式/反模式/权衡），"
        "必须超越原文形成更高一层的认知，不要复述内容。\n\n" + joined
    )


# --------------------------------------------------------------------------- arms
def run_distill(client, model: str, policy: str, sources: list[dict]) -> dict:
    prompt = distill_prompt(sources)
    if policy == "legacy":
        obj = client.chat.completions.create(
            model=model, response_model=ClaimDraft,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2, max_retries=3,      # Instructor's own (appending) retry
            extra_body=EXTRA_BODY,
        )
        rep = {"n_attempts": 1, "prompt_growth": None, "policy": "legacy"}
    else:
        obj, r = resilient_create(
            client, model, ClaimDraft, prompt, temperature=0.2, max_attempts=3,
            extra_body=EXTRA_BODY,
        )
        rep = {"n_attempts": r.n_attempts, "prompt_growth": r.prompt_growth,
               "policy": "resilient"}
    draft = json.loads(obj.model_dump_json())
    return {"draft": draft, "retry": rep,
            "scores": score_claim(draft, sources),
            "verdict": verdict(score_claim(draft, sources), "claim")}


def run_combine(client, model: str, policy: str, query: str, sources: list[dict]) -> dict:
    def _gen(prompt: str):
        if policy == "legacy":
            return client.chat.completions.create(
                model=model, response_model=ModelingArtifact,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_retries=3, extra_body=EXTRA_BODY,
            )
        obj, _ = resilient_create(
            client, model, ModelingArtifact, prompt, temperature=0.2, max_attempts=3,
            extra_body=EXTRA_BODY,
        )
        return obj

    # funnel steps also go through the same model/policy
    def _sum(src, q):
        body = (f"针对问题「{q}」，只依据下面这条来源，给出一句与该问题相关的要点总结"
                f"（不要复述全文，不超过 60 字）。\n\n[{src['title']}]\n{src['content']}")
        if policy != "legacy":
            out, _ = resilient_create(client, model, combine_mod._SummaryOut, body,
                                      temperature=0.2, max_attempts=2,
                                      extra_body=EXTRA_BODY)
        else:
            out = client.chat.completions.create(
                model=model, response_model=combine_mod._SummaryOut,
                messages=[{"role": "user", "content": body}],
                temperature=0.2, max_retries=3, extra_body=EXTRA_BODY)
        return out.point

    def _score(summary, q):
        body = (f"问题：「{q}」。以下总结对该问题的支撑度打分 0~1（只输出分数对象）。"
                f"\n\n{summary}")
        if policy != "legacy":
            out, _ = resilient_create(client, model, combine_mod._ScoreOut, body,
                                      temperature=0.0, max_attempts=2,
                                      extra_body=EXTRA_BODY)
        else:
            out = client.chat.completions.create(
                model=model, response_model=combine_mod._ScoreOut,
                messages=[{"role": "user", "content": body}],
                temperature=0.0, max_retries=3, extra_body=EXTRA_BODY)
        return out.score

    op = CombineOperator(summarize=_sum, score=_score, generate=_gen, max_sources=4)
    try:
        out = op.combine(query, sources)
    except ValueError as e:
        return {"error": str(e), "retry": {"policy": policy}}
    art = out["artifact"]
    scores = score_artifact(art, sources)
    return {"artifact": art, "report": out["report"], "scores": scores,
            "verdict": verdict(scores, "artifact"), "retry": {"policy": policy}}


ARMS = [
    ("A baseline  1.5B + legacy retry", BASELINE_MODEL, "legacy"),
    ("B policy    1.5B + fixed retry", BASELINE_MODEL, "resilient"),
    ("C model     9B   + fixed retry", TARGET_MODEL, "resilient"),
    ("D iteration 4B   + fixed retry", ITER_MODEL, "resilient"),
]


def run_all(sources, query, distill_sources, mode="json", arms=None) -> dict:
    client = make_client(mode)
    results = {}
    for label, model, policy in (arms or ARMS):
        try:
            d = run_distill(client, model, policy, distill_sources)
        except Exception as e:  # noqa: BLE001 - an arm failing is data, not a crash
            d = {"error": f"{type(e).__name__}: {e}"}
        try:
            c = run_combine(client, model, policy, query, sources)
        except Exception as e:  # noqa: BLE001
            c = {"error": f"{type(e).__name__}: {e}"}
        results[label] = {"model": model, "policy": policy, "distill": d, "combine": c}
        print(f"  [done] {label}", file=sys.stderr)
    return results
